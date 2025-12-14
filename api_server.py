#!/usr/bin/env python3
"""
Simple API server for CB Monitor web interface
Handles CSV exports and monitoring control
"""

import os
import sys
import json
import csv
import subprocess
import signal
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

DATA_DIR = Path(__file__).parent / "data"
LOGS_DIR = Path(__file__).parent / "logs"

# Global to track monitoring process
monitor_process = None

class APIHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        # Add CORS headers
        self.send_header('Access-Control-Allow-Origin', '*')

        # Only disable caching for data files (JSON, JSONL)
        # Allow caching for static assets (HTML, CSS, JS)
        if self.path.endswith('.json') or self.path.endswith('.jsonl'):
            self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
            self.send_header('Expires', '0')
        else:
            # Cache static assets for 1 hour
            self.send_header('Cache-Control', 'public, max-age=3600')

        super().end_headers()

    def do_GET(self):
        parsed_path = urlparse(self.path)
        path_parts = parsed_path.path.strip('/').split('/')

        # Handle API routes
        if path_parts[0] == 'api':
            if len(path_parts) >= 3 and path_parts[1] == 'export':
                session_id = path_parts[2]
                self.handle_csv_export(session_id)
                return
            elif len(path_parts) >= 3 and path_parts[1] == 'monitor':
                if path_parts[2] == 'status':
                    self.handle_monitor_status()
                    return

        # Serve static files
        super().do_GET()

    def do_POST(self):
        parsed_path = urlparse(self.path)
        path_parts = parsed_path.path.strip('/').split('/')

        # Handle API routes
        if path_parts[0] == 'api' and len(path_parts) >= 3 and path_parts[1] == 'monitor':
            if path_parts[2] == 'start':
                self.handle_monitor_start()
                return
            elif path_parts[2] == 'stop':
                self.handle_monitor_stop()
                return

        self.send_error(404, "Not found")

    def handle_csv_export(self, session_id):
        """Export session data to CSV"""
        log_file = LOGS_DIR / f"{session_id}.jsonl"

        if not log_file.exists():
            self.send_error(404, f"Session not found: {session_id}")
            return

        # Read data
        data_points = []
        with open(log_file, 'r') as f:
            for line in f:
                if line.strip():
                    data_points.append(json.loads(line))

        if not data_points:
            self.send_error(404, "No data in session")
            return

        # Generate CSV
        self.send_response(200)
        self.send_header('Content-Type', 'text/csv')
        self.send_header('Content-Disposition', f'attachment; filename="{session_id}.csv"')
        self.end_headers()

        # Create CSV writer
        import io
        output = io.StringIO()
        fieldnames = [
            'timestamp', 'latitude', 'longitude',
            'rssi', 'rsrp', 'rsrq', 'snr',
            'mcc', 'mnc', 'tac', 'ci', 'pci', 'earfcn'
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()

        for point in data_points:
            writer.writerow({
                'timestamp': point['timestamp'],
                'latitude': point['location']['latitude'] or '',
                'longitude': point['location']['longitude'] or '',
                'rssi': point['signal']['rssi'] if point['signal']['rssi'] is not None else '',
                'rsrp': point['signal']['rsrp'] if point['signal']['rsrp'] is not None else '',
                'rsrq': point['signal']['rsrq'] if point['signal']['rsrq'] is not None else '',
                'snr': point['signal']['snr'] if point['signal']['snr'] is not None else '',
                'mcc': point['lte']['mcc'],
                'mnc': point['lte']['mnc'],
                'tac': point['lte']['tac'],
                'ci': point['lte']['ci'],
                'pci': point['lte']['pci'],
                'earfcn': point['lte']['earfcn']
            })

        csv_content = output.getvalue()
        self.wfile.write(csv_content.encode('utf-8'))

    def handle_monitor_status(self):
        """Get monitoring status"""
        global monitor_process

        # Check if process is running - either tracked or any cb_monitor.py process
        is_running = False

        # First check if we're tracking a process
        if monitor_process is not None and monitor_process.poll() is None:
            is_running = True
        else:
            # Check if any cb_monitor.py process is running
            try:
                result = subprocess.run(['pgrep', '-f', 'cb_monitor.py monitor'],
                                      capture_output=True, text=True, timeout=2)
                if result.returncode == 0 and result.stdout.strip():
                    is_running = True
            except:
                pass

        # Get connected device info
        device_info = None
        if is_running or True:  # Always try to get device info
            try:
                result = subprocess.run(['/opt/homebrew/bin/adb', 'devices', '-l'],
                                      capture_output=True, text=True, timeout=2)
                if result.returncode == 0:
                    lines = result.stdout.strip().split('\n')
                    for line in lines[1:]:  # Skip header
                        if line.strip() and 'device' in line:
                            parts = line.split()
                            serial = parts[0]
                            # Extract model/device name
                            model = ''
                            for part in parts:
                                if part.startswith('model:'):
                                    model = part.split(':')[1]
                                    break
                            device_info = {
                                'serial': serial,
                                'model': model.replace('_', ' ') if model else serial
                            }
                            break
            except:
                pass

        response = {
            'running': is_running,
            'device': device_info
        }

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(response).encode('utf-8'))

    def handle_monitor_start(self):
        """Start monitoring"""
        global monitor_process

        if monitor_process is not None and monitor_process.poll() is None:
            self.send_response(400)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': 'Monitoring already running'}).encode('utf-8'))
            return

        # Start monitoring process
        try:
            monitor_process = subprocess.Popen(
                ['python3', 'cb_monitor.py', 'monitor'],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=Path(__file__).parent
            )

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'success': True, 'pid': monitor_process.pid}).encode('utf-8'))
            print(f"[MONITOR] Started monitoring (PID: {monitor_process.pid})")
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': str(e)}).encode('utf-8'))

    def handle_monitor_stop(self):
        """Stop monitoring"""
        global monitor_process

        # Try to stop the tracked process first
        if monitor_process is not None and monitor_process.poll() is None:
            try:
                monitor_process.send_signal(signal.SIGINT)
                monitor_process.wait(timeout=5)
                monitor_process = None
                print("[MONITOR] Stopped monitoring (tracked process)")
            except Exception as e:
                print(f"[MONITOR] Error stopping tracked process: {e}")

        # Also kill any other cb_monitor.py processes
        try:
            result = subprocess.run(['pkill', '-SIGINT', '-f', 'cb_monitor.py monitor'],
                                  capture_output=True, text=True, timeout=2)

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'success': True}).encode('utf-8'))
            print("[MONITOR] Stopped all monitoring processes")
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': str(e)}).encode('utf-8'))

def start_server(port=8888):
    """Start the API server"""
    os.chdir(Path(__file__).parent)

    server_address = ('', port)
    httpd = HTTPServer(server_address, APIHandler)

    print(f"\n🌐 CB Monitor Server started: http://localhost:{port}")
    print(f"   Main menu: http://localhost:{port}/index.html")
    print(f"   Dashboard: http://localhost:{port}/dashboard.html")
    print(f"   Heatmap: http://localhost:{port}/heatmap.html")
    print(f"\n   Press Ctrl+C to stop\n")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n⏹️  Server stopped")
        httpd.shutdown()

if __name__ == '__main__':
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8888
    start_server(port)
