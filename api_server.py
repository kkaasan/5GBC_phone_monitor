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
import shutil
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

DATA_DIR = Path(__file__).parent / "data"
LOGS_DIR = Path(__file__).parent / "logs"
CB_LOGS_DIR = Path(__file__).parent / "cb_logs"
CB_INDEX_FILE = DATA_DIR / "cb_index.json"
PHONE_LOG_DIR = "/sdcard/Android/data/ee.levira.cbmonitor/files/cb_monitor"
PHONE_CB_LOG_DIR = "/sdcard/Android/data/ee.levira.cbmonitor/files/cb_monitor/cb_logs"
ADB_CANDIDATES = [
    '/opt/homebrew/bin/adb',  # Apple Silicon default
    '/usr/local/bin/adb',     # Intel/macOS default
    'adb'                     # Fallback to PATH
]

def resolve_adb_path():
    """Return the first available ADB path from common locations"""
    for candidate in ADB_CANDIDATES:
        if candidate == 'adb':
            if shutil.which(candidate):
                return candidate
        elif os.path.exists(candidate):
            return candidate
    return None

def build_session_metadata(log_file, session_id):
    """Compute session metadata from a JSONL log"""
    if not log_file.exists():
        return None

    start_time = None
    end_time = None
    count = 0
    lats = []
    lons = []

    with open(log_file, "r") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                point = json.loads(line)
            except Exception:
                continue

            count += 1
            ts = point.get("timestamp")
            if ts:
                if not start_time:
                    start_time = ts
                end_time = ts

            loc = point.get("location") or {}
            lat = loc.get("latitude")
            lon = loc.get("longitude")
            try:
                if lat not in [None, ""]:
                    lats.append(float(lat))
                if lon not in [None, ""]:
                    lons.append(float(lon))
            except Exception:
                pass

    if count == 0 or not start_time or not end_time:
        return None

    return {
        "session_id": session_id,
        "start_time": start_time,
        "end_time": end_time,
        "count": count,
        "bounds": {
            "min_lat": min(lats) if lats else None,
            "max_lat": max(lats) if lats else None,
            "min_lon": min(lons) if lons else None,
            "max_lon": max(lons) if lons else None,
        },
    }

def update_data_index(session_metadata):
    """Add or update a session entry in data_index.json"""
    index = {"sessions": []}
    index_file = DATA_DIR / "data_index.json"
    if index_file.exists():
        try:
            with open(index_file, "r") as f:
                index = json.load(f)
        except Exception:
            index = {"sessions": []}

    existing = [s for s in index.get("sessions", []) if s.get("session_id") == session_metadata["session_id"]]
    if existing:
        index["sessions"].remove(existing[0])

    index.setdefault("sessions", []).append(session_metadata)
    index["sessions"].sort(key=lambda x: x.get("start_time", ""), reverse=True)

    with open(index_file, "w") as f:
        json.dump(index, f, indent=2)

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
            elif len(path_parts) >= 2 and path_parts[1] == 'cb':
                if len(path_parts) >= 3 and path_parts[2] == 'list':
                    self.handle_cb_list()
                    return
                elif len(path_parts) >= 4 and path_parts[2] == 'message':
                    msg_id = path_parts[3]
                    self.handle_cb_message(msg_id)
                    return

        # Serve static files
        super().do_GET()

    def do_POST(self):
        parsed_path = urlparse(self.path)
        path_parts = parsed_path.path.strip('/').split('/')

        # Handle API routes
        if path_parts[0] == 'api' and len(path_parts) >= 3:
            if path_parts[1] == 'monitor':
                if path_parts[2] == 'start':
                    self.handle_monitor_start()
                    return
                elif path_parts[2] == 'stop':
                    self.handle_monitor_stop()
                    return
            elif path_parts[1] == 'transmitters' and path_parts[2] == 'save':
                self.handle_transmitters_save()
                return
            elif path_parts[1] == 'sessions' and path_parts[2] == 'delete':
                self.handle_session_delete()
                return
            elif path_parts[1] == 'sessions' and path_parts[2] == 'export':
                self.handle_sessions_export()
                return
            elif path_parts[1] == 'sessions' and path_parts[2] == 'import_phone':
                self.handle_sessions_import_phone()
                return
            elif path_parts[1] == 'sessions' and path_parts[2] == 'import_local':
                self.handle_sessions_import_local()
                return
            elif path_parts[1] == 'cb' and path_parts[2] == 'import_phone':
                self.handle_cb_import_phone()
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

    def handle_transmitters_save(self):
        """Save transmitter configuration to file"""
        try:
            # Read POST data
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))

            # Save to file
            transmitters_file = DATA_DIR / "transmitters.json"
            with open(transmitters_file, 'w') as f:
                json.dump(data, f, indent=2)

            print(f"[TRANSMITTERS] Saved {len(data.get('transmitters', []))} transmitters to {transmitters_file}")

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'success': True}).encode('utf-8'))

        except Exception as e:
            print(f"[TRANSMITTERS ERROR] {e}")
            import traceback
            traceback.print_exc()

            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode('utf-8'))

    def handle_session_delete(self):
        """Delete a session: remove log file and drop from data_index.json"""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length) if content_length > 0 else b'{}'
            data = json.loads(body.decode('utf-8') or '{}')
            session_id = data.get('session_id')
        except Exception:
            session_id = None

        if not session_id:
            self.send_error(400, "Missing session_id")
            return

        log_file = LOGS_DIR / f"{session_id}.jsonl"
        removed_log = False
        if log_file.exists():
            try:
                log_file.unlink()
                removed_log = True
            except Exception:
                pass

        index_file = DATA_DIR / "data_index.json"
        removed_index = False
        if index_file.exists():
            try:
                with open(index_file, "r") as f:
                    index_data = json.load(f)
                sessions = index_data.get("sessions", [])
                new_sessions = [s for s in sessions if s.get("session_id") != session_id]
                if len(new_sessions) != len(sessions):
                    index_data["sessions"] = new_sessions
                    with open(index_file, "w") as f:
                        json.dump(index_data, f, indent=2)
                    removed_index = True
            except Exception:
                pass

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({
            "success": True,
            "session_id": session_id,
            "removed_log": removed_log,
            "removed_index": removed_index
        }).encode('utf-8'))

    def handle_sessions_export(self):
        """Export multiple sessions into a single CSV"""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length) if content_length > 0 else b'{}'
            data = json.loads(body.decode('utf-8') or '{}')
            session_ids = data.get('session_ids') or []
        except Exception:
            session_ids = []

        if not session_ids:
            self.send_error(400, "Missing session_ids")
            return

        combined = []
        for session_id in session_ids:
            log_file = LOGS_DIR / f"{session_id}.jsonl"
            if not log_file.exists():
                continue
            try:
                with open(log_file, 'r') as f:
                    for line in f:
                        if not line.strip():
                            continue
                        point = json.loads(line)
                        point["session_id"] = session_id
                        combined.append(point)
            except Exception:
                continue

        if not combined:
            self.send_error(404, "No data found for selected sessions")
            return

        # Sort by timestamp
        combined.sort(key=lambda p: p.get("timestamp", ""))

        # Generate CSV
        self.send_response(200)
        self.send_header('Content-Type', 'text/csv')
        self.send_header('Content-Disposition', 'attachment; filename="sessions_combined.csv"')
        self.end_headers()

        import io
        output = io.StringIO()
        fieldnames = [
            'session_id',
            'timestamp', 'latitude', 'longitude',
            'rssi', 'rsrp', 'rsrq', 'snr',
            'mcc', 'mnc', 'tac', 'ci', 'pci', 'earfcn'
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()

        for point in combined:
            writer.writerow({
                'session_id': point.get('session_id', ''),
                'timestamp': point.get('timestamp', ''),
                'latitude': point.get('location', {}).get('latitude') or '',
                'longitude': point.get('location', {}).get('longitude') or '',
                'rssi': (point.get('signal', {}) or {}).get('rssi') or '',
                'rsrp': (point.get('signal', {}) or {}).get('rsrp') or '',
                'rsrq': (point.get('signal', {}) or {}).get('rsrq') or '',
                'snr': (point.get('signal', {}) or {}).get('snr') or '',
                'mcc': (point.get('lte', {}) or {}).get('mcc') or '',
                'mnc': (point.get('lte', {}) or {}).get('mnc') or '',
                'tac': (point.get('lte', {}) or {}).get('tac') or '',
                'ci': (point.get('lte', {}) or {}).get('ci') or '',
                'pci': (point.get('lte', {}) or {}).get('pci') or '',
                'earfcn': (point.get('lte', {}) or {}).get('earfcn') or ''
            })

        self.wfile.write(output.getvalue().encode('utf-8'))

    def handle_cb_list(self):
        """Get list of all CB messages"""
        try:
            if CB_INDEX_FILE.exists():
                with open(CB_INDEX_FILE, 'r') as f:
                    index = json.load(f)
            else:
                index = {'messages': []}

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(index).encode('utf-8'))
        except Exception as e:
            print(f"[CB ERROR] {e}")
            self.send_error(500, str(e))

    def handle_cb_message(self, msg_id):
        """Get specific CB message details"""
        try:
            cb_file = CB_LOGS_DIR / f"{msg_id}.json"
            if cb_file.exists():
                with open(cb_file, 'r') as f:
                    message = json.load(f)

                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(message).encode('utf-8'))
            else:
                self.send_error(404, "Message not found")
        except Exception as e:
            print(f"[CB ERROR] {e}")
            self.send_error(500, str(e))

    def handle_sessions_import_phone(self):
        """Pull logs from phone storage and delete them on the device"""
        adb_path = resolve_adb_path()
        if not adb_path:
            self.send_error(500, "ADB not found on host")
            return

        # Verify device connection
        try:
            result = subprocess.run([adb_path, 'devices'], capture_output=True, text=True, timeout=5)
            if result.returncode != 0:
                raise RuntimeError(result.stderr.strip() or "ADB error")
            device_lines = [line for line in result.stdout.splitlines() if line.strip() and not line.startswith('List')]
            connected = [line for line in device_lines if 'device' in line.split()]
            if not connected:
                self.send_error(400, "No ADB device connected")
                return
        except Exception as e:
            self.send_error(500, f"ADB devices check failed: {e}")
            return

        # List log files on the device
        try:
            list_cmd = [adb_path, 'shell', 'ls', f"{PHONE_LOG_DIR}/*.jsonl"]
            list_result = subprocess.run(list_cmd, capture_output=True, text=True, timeout=10)
            if list_result.returncode != 0 or "No such file" in list_result.stderr:
                response = {"success": True, "imported": [], "skipped_existing": [], "failed": [], "message": "No logs found on device"}
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(response).encode('utf-8'))
                return

            remote_files = [line.strip() for line in list_result.stdout.splitlines() if line.strip() and not line.strip().startswith('ls:')]
        except Exception as e:
            self.send_error(500, f"Failed to list logs on device: {e}")
            return

        imported = []
        skipped_existing = []
        failed = []

        LOGS_DIR.mkdir(exist_ok=True)
        DATA_DIR.mkdir(exist_ok=True)

        for remote_file in remote_files:
            session_id = Path(remote_file).stem
            local_path = LOGS_DIR / f"{session_id}.jsonl"

            if local_path.exists():
                skipped_existing.append(session_id)
                # Remove from device to avoid re-import prompts
                subprocess.run([adb_path, 'shell', 'rm', remote_file], capture_output=True, text=True)
                continue

            try:
                pull_result = subprocess.run([adb_path, 'pull', remote_file, str(local_path)],
                                             capture_output=True, text=True, timeout=30)
                if pull_result.returncode != 0:
                    failed.append(session_id)
                    # Ensure partially pulled file does not remain
                    if local_path.exists():
                        local_path.unlink()
                    continue

                # Delete from device after successful pull
                subprocess.run([adb_path, 'shell', 'rm', remote_file], capture_output=True, text=True)

                metadata = build_session_metadata(local_path, session_id)
                if metadata:
                    update_data_index(metadata)
                    imported.append(session_id)
                else:
                    failed.append(session_id)
            except Exception:
                failed.append(session_id)
                if local_path.exists():
                    local_path.unlink()

        message = "Import complete"
        if not imported and not skipped_existing:
            message = "No new sessions imported"

        response = {
            "success": True,
            "imported": imported,
            "skipped_existing": skipped_existing,
            "failed": failed,
            "message": message
        }

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(response).encode('utf-8'))

    def handle_sessions_import_local(self):
        """Import log files from local uploads"""
        try:
            # Read request body
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8'))

            session_id = data.get('session_id')
            content = data.get('content')

            if not session_id or not content:
                self.send_response(400)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': False,
                    'error': 'Missing session_id or content'
                }).encode('utf-8'))
                return

            # Ensure directories exist
            LOGS_DIR.mkdir(exist_ok=True)
            DATA_DIR.mkdir(exist_ok=True)

            local_path = LOGS_DIR / f"{session_id}.jsonl"

            # Check if file already exists
            if local_path.exists():
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': True,
                    'skipped': True,
                    'message': 'File already exists'
                }).encode('utf-8'))
                return

            # Write the file
            local_path.write_text(content)

            # Build and update metadata
            metadata = build_session_metadata(local_path, session_id)
            if metadata:
                update_data_index(metadata)
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': True,
                    'skipped': False,
                    'message': 'File imported successfully'
                }).encode('utf-8'))
            else:
                # Failed to parse - delete the file
                local_path.unlink()
                self.send_response(400)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': False,
                    'error': 'Invalid file format - no valid data found'
                }).encode('utf-8'))

        except Exception as e:
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                'success': False,
                'error': str(e)
            }).encode('utf-8'))

    def handle_cb_import_phone(self):
        """Pull CB log files from phone storage and merge with existing logs"""
        adb_path = resolve_adb_path()
        if not adb_path:
            self.send_error(500, "ADB not found on host")
            return

        # Verify device connection
        try:
            result = subprocess.run([adb_path, 'devices'], capture_output=True, text=True, timeout=5)
            if result.returncode != 0:
                raise RuntimeError(result.stderr.strip() or "ADB error")
            device_lines = [line for line in result.stdout.splitlines() if line.strip() and not line.startswith('List')]
            connected = [line for line in device_lines if 'device' in line.split()]
            if not connected:
                self.send_error(400, "No ADB device connected")
                return
        except Exception as e:
            self.send_error(500, f"ADB devices check failed: {e}")
            return

        # List CB log files on the device
        try:
            list_cmd = [adb_path, 'shell', 'ls', f"{PHONE_CB_LOG_DIR}/*.json"]
            list_result = subprocess.run(list_cmd, capture_output=True, text=True, timeout=10)
            if list_result.returncode != 0 or "No such file" in list_result.stderr:
                response = {"success": True, "imported": [], "skipped_existing": [], "failed": [], "message": "No CB logs found on device"}
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(response).encode('utf-8'))
                return

            remote_files = [line.strip() for line in list_result.stdout.splitlines() if line.strip() and not line.strip().startswith('ls:')]
        except Exception as e:
            self.send_error(500, f"Failed to list CB logs on device: {e}")
            return

        imported = []
        skipped_existing = []
        failed = []

        CB_LOGS_DIR.mkdir(exist_ok=True)
        DATA_DIR.mkdir(exist_ok=True)

        for remote_file in remote_files:
            msg_id = Path(remote_file).stem
            local_path = CB_LOGS_DIR / f"{msg_id}.json"

            if local_path.exists():
                skipped_existing.append(msg_id)
                # Remove from device to avoid re-import prompts
                subprocess.run([adb_path, 'shell', 'rm', remote_file], capture_output=True, text=True)
                continue

            try:
                pull_result = subprocess.run([adb_path, 'pull', remote_file, str(local_path)],
                                             capture_output=True, text=True, timeout=30)
                if pull_result.returncode != 0:
                    failed.append(msg_id)
                    # Ensure partially pulled file does not remain
                    if local_path.exists():
                        local_path.unlink()
                    continue

                # Delete from device after successful pull
                subprocess.run([adb_path, 'shell', 'rm', remote_file], capture_output=True, text=True)

                # Update CB index
                try:
                    with open(local_path, 'r') as f:
                        cb_record = json.load(f)
                    update_cb_index_entry(msg_id, cb_record)
                    imported.append(msg_id)
                except Exception:
                    failed.append(msg_id)
            except Exception:
                failed.append(msg_id)
                if local_path.exists():
                    local_path.unlink()

        message = "Import complete"
        if not imported and not skipped_existing:
            message = "No new CB messages imported"

        response = {
            "success": True,
            "imported": imported,
            "skipped_existing": skipped_existing,
            "failed": failed,
            "message": message
        }

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(response).encode('utf-8'))

def update_cb_index_entry(msg_id, cb_record):
    """Update CB index with a single entry"""
    try:
        if CB_INDEX_FILE.exists():
            with open(CB_INDEX_FILE, 'r') as f:
                index = json.load(f)
        else:
            index = {'messages': []}

        # Extract heading from body
        body = cb_record.get('body', '')
        heading = body.split('\n')[0][:100] if body else 'CB Message'

        # Create index entry
        index_entry = {
            'id': msg_id,
            'timestamp': cb_record.get('timestamp'),
            'heading': heading,
            'priority': cb_record.get('priority'),
            'language': cb_record.get('language'),
            'serviceCategory': cb_record.get('serviceCategory')
        }

        # Check if already exists
        existing = [m for m in index.get('messages', []) if m.get('id') == msg_id]
        if not existing:
            index.setdefault('messages', []).insert(0, index_entry)

            with open(CB_INDEX_FILE, 'w') as f:
                json.dump(index, f, indent=2)

    except Exception as e:
        print(f"[CB ERROR] Error updating CB index: {e}")

def start_server(port=8888):
    """Start the API server"""
    os.chdir(Path(__file__).parent)

    server_address = ('', port)
    httpd = HTTPServer(server_address, APIHandler)

    print(f"\n🌐 CB Monitor Server started: http://localhost:{port}")
    print(f"   Main menu: http://localhost:{port}/index.html")
    print(f"   Dashboard: http://localhost:{port}/dashboard.html")
    print(f"   Heatmap: http://localhost:{port}/heatmap.html")
    print(f"   Settings: http://localhost:{port}/settings.html")
    print(f"   Sessions: http://localhost:{port}/sessions.html")
    print(f"\n   API endpoints: /api/monitor/*, /api/transmitters/*, /api/export/*, /api/cb/*")
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
