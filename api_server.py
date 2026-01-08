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
import math
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
        if path_parts[0] == 'api':
            # Routes with 2 parts
            if len(path_parts) == 2:
                if path_parts[1] == 'predict-coverage':
                    self.handle_predict_coverage()
                    return
            # Routes with 3+ parts
            elif len(path_parts) >= 3:
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
                elif path_parts[1] == 'cb' and path_parts[2] == 'import_local':
                    self.handle_cb_import_local()
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

    def handle_predict_coverage(self):
        """Generate signal coverage prediction using Log-Distance Path Loss model"""
        try:
            # Read POST data
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))

            transmitters = data.get('transmitters', [])
            measurements = data.get('measurements', [])
            bounds = data.get('bounds', {})
            zoom = data.get('zoom', 13)  # Default to zoom 13 if not provided

            # Generate prediction
            prediction_result = self.generate_coverage_prediction(transmitters, measurements, bounds, zoom)

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(prediction_result).encode('utf-8'))

        except Exception as e:
            print(f"[PREDICTION ERROR] {e}")
            import traceback
            traceback.print_exc()

            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode('utf-8'))

    def okumura_hata_path_loss(self, freq_mhz, hb, hm, d_km, environment='urban'):
        """
        Calculate path loss using Okumura-Hata model for broadcast (DVB-T2)

        Args:
            freq_mhz: Frequency in MHz (typically 470-862 MHz for DVB-T2)
            hb: Base station (transmitter) antenna height in meters (30-200m)
            hm: Mobile (receiver) antenna height in meters (1-10m)
            d_km: Distance in kilometers (1-20km)
            environment: 'urban', 'suburban', or 'rural'

        Returns:
            Path loss in dB
        """
        import math

        # Clamp values to valid ranges
        freq_mhz = max(150, min(1500, freq_mhz))
        hb = max(30, min(200, hb))
        hm = max(1, min(10, hm))
        d_km = max(0.1, min(100, d_km))

        # Mobile antenna height correction factor
        if freq_mhz < 300:
            # For smaller cities and rural areas
            a_hm = (1.1 * math.log10(freq_mhz) - 0.7) * hm - (1.56 * math.log10(freq_mhz) - 0.8)
        else:
            # For large cities (UHF)
            a_hm = 3.2 * (math.log10(11.75 * hm)) ** 2 - 4.97

        # Base Okumura-Hata formula (urban)
        path_loss_urban = (69.55 + 26.16 * math.log10(freq_mhz) - 13.82 * math.log10(hb) - a_hm +
                          (44.9 - 6.55 * math.log10(hb)) * math.log10(d_km))

        # Apply environment correction
        if environment == 'suburban':
            correction = 2 * (math.log10(freq_mhz / 28)) ** 2 + 5.4
            path_loss = path_loss_urban - correction
        elif environment == 'rural':
            correction = 4.78 * (math.log10(freq_mhz)) ** 2 - 18.33 * math.log10(freq_mhz) + 40.94
            path_loss = path_loss_urban - correction
        else:  # urban
            path_loss = path_loss_urban

        # For broadcast applications at long distances (>20 km), apply correction
        # Okumura-Hata tends to overestimate loss at long distances for high-power broadcast
        if d_km > 20:
            # Reduce path loss for longer distances to account for broadcast propagation
            # This is empirically derived for DVB-T2 broadcast networks
            long_distance_factor = 1.0 - 0.15 * math.log10(d_km / 20)  # Up to 15% reduction
            path_loss = path_loss * long_distance_factor

        return path_loss

    def calculate_theoretical_max_distance(self, tx_power, freq_mhz, tx_height, rx_height, environment, rsrp_threshold=-115):
        """
        Calculate theoretical maximum coverage distance for a given transmitter power and RSRP threshold.
        Uses binary search to find the distance where RSRP equals the threshold.

        Args:
            tx_power: Transmitter ERP in dBm
            freq_mhz: Frequency in MHz
            tx_height: Transmitter antenna height in meters
            rx_height: Receiver antenna height in meters
            environment: 'urban', 'suburban', or 'rural'
            rsrp_threshold: Minimum RSRP in dBm for coverage (default -115 dBm for edge of coverage)

        Returns:
            Maximum distance in kilometers
        """
        # Binary search for distance where RSRP = threshold
        # Assuming 0 dB antenna gain for theoretical calculation
        min_dist = 0.1
        max_dist = 200.0  # Maximum theoretical distance

        for _ in range(50):  # 50 iterations gives very precise result
            mid_dist = (min_dist + max_dist) / 2.0

            # Calculate path loss at this distance
            path_loss = self.okumura_hata_path_loss(freq_mhz, tx_height, rx_height, mid_dist, environment)

            # Calculate RSRP (assuming 0 dB antenna gain for theoretical max)
            rsrp = tx_power - path_loss

            if rsrp > rsrp_threshold:
                # Signal is still above threshold, try farther
                min_dist = mid_dist
            else:
                # Signal is below threshold, try closer
                max_dist = mid_dist

        return (min_dist + max_dist) / 2.0

    def generate_coverage_prediction(self, transmitters, measurements, bounds, zoom=13):
        """
        Generate coverage prediction using Okumura-Hata propagation model for DVB-T2

        This model is specifically designed for broadcast applications and accounts for:
        - Frequency-dependent propagation
        - Antenna heights (transmitter and receiver)
        - Environment type (urban/suburban/rural)
        - Diffraction and clutter losses

        More accurate than simple log-distance for real-world broadcast coverage.

        Args:
            transmitters: List of transmitter configurations
            measurements: List of measurement data points
            bounds: Map bounds for prediction area
            zoom: Map zoom level for adaptive grid resolution
        """
        import math
        import numpy as np
        from scipy.optimize import curve_fit

        import time
        prediction_start_time = time.time()

        print(f"[PREDICTION] Starting prediction with {len(transmitters)} transmitters, {len(measurements)} measurements at zoom {zoom}")

        # Debug: Print first measurement to see structure
        if measurements:
            print(f"[PREDICTION] Sample measurement: {measurements[0]}")

        # 5G Broadcast parameters
        # LTE Band 71 operating at 600-700 MHz range
        freq_mhz = 626  # 5G Broadcast in LTE Band 71 (measured frequency)
        rx_height = 1.5  # Receiver antenna height (1.5m handheld)

        # Step 1: Calibrate environment type from measurements
        # Group measurements by transmitter (PCI)
        tx_measurements = {}
        for m in measurements:
            pci = m.get('pci')
            if pci is not None and m.get('rsrp') is not None:
                if pci not in tx_measurements:
                    tx_measurements[pci] = []
                tx_measurements[pci].append(m)

        # Step 2: For each transmitter with measurements, fit the model
        tx_params = {}
        print(f"[PREDICTION] ====== TRANSMITTER CALIBRATION ======")
        print(f"[PREDICTION] Found {len(transmitters)} transmitters to calibrate")
        print(f"[PREDICTION] Measurement groups by PCI: {[(pci, len(meas)) for pci, meas in tx_measurements.items()]}")

        for tx in transmitters:
            tx_id = tx['id']
            tx_pci = tx.get('pci')
            tx_lat = tx['lat']
            tx_lon = tx['lon']
            tx_height = tx.get('height', 30)  # Default 30m antenna height

            # Get transmit power from configuration or calibrate from measurements
            # DVB-T2/5G Broadcast typically uses 60-70 dBm (much higher than cellular)
            tx_power_config = tx.get('txPower', None)

            print(f"[PREDICTION] Transmitter {tx_id} (PCI {tx_pci}): Configured ERP={tx_power_config}, Measurements={len(tx_measurements.get(tx_pci, []))}")

            if tx_pci in tx_measurements and len(tx_measurements[tx_pci]) >= 5:
                # We have enough measurements to calibrate environment type AND transmit power
                meas = tx_measurements[tx_pci]

                # Calibrate both transmit power AND environment jointly for best fit
                if tx_power_config is None:
                    # Test all environment types and derive best tx_power for each
                    best_environment = 'suburban'
                    best_tx_power = 65
                    best_error = float('inf')
                    best_correction = 0

                    # For DVB-T2 broadcast, only test urban/suburban (rural path loss is too low for high-power broadcast)
                    for env_type in ['urban', 'suburban']:
                        # Derive tx_power for this environment type
                        derived_powers = []
                        sample_details = []

                        for m in meas:
                            m_lat = m.get('lat')
                            m_lon = m.get('lon')
                            rsrp = m.get('rsrp')

                            if m_lat is None or m_lon is None or rsrp is None:
                                continue

                            dist_km = self.haversine_distance(tx_lat, tx_lon, m_lat, m_lon)
                            if dist_km < 0.1:
                                continue

                            # Calculate path loss for this environment
                            path_loss = self.okumura_hata_path_loss(freq_mhz, tx_height, rx_height, dist_km, env_type)

                            # Derive transmit power: TxPower = RSRP + PathLoss
                            # Note: Not accounting for antenna gain - assumes omnidirectional or averaged
                            derived_tx_power = rsrp + path_loss
                            derived_powers.append(derived_tx_power)

                            # Save details for first few samples
                            if len(sample_details) < 3:
                                sample_details.append({
                                    'dist_km': dist_km,
                                    'rsrp': rsrp,
                                    'path_loss': path_loss,
                                    'derived_power': derived_tx_power
                                })

                        if not derived_powers:
                            continue

                        # Use median tx_power for this environment
                        env_tx_power = np.median(derived_powers)

                        # Debug: Show calibration details for best environment (will update later)
                        if len(sample_details) > 0:
                            print(f"[CALIBRATION] PCI {tx_pci}, {env_type}: {len(derived_powers)} samples, median={env_tx_power:.1f}dBm, range={min(derived_powers):.1f}-{max(derived_powers):.1f}dBm")
                            for idx, s in enumerate(sample_details):
                                print(f"[CALIBRATION]   Sample {idx+1}: dist={s['dist_km']:.1f}km, RSRP={s['rsrp']:.0f}dBm, PathLoss={s['path_loss']:.1f}dB → Power={s['derived_power']:.1f}dBm")

                        # Now evaluate prediction error with this tx_power and environment
                        errors = []
                        corrections = []

                        for m in meas:
                            m_lat = m.get('lat')
                            m_lon = m.get('lon')
                            rsrp = m.get('rsrp')

                            if m_lat is None or m_lon is None or rsrp is None:
                                continue

                            dist_km = self.haversine_distance(tx_lat, tx_lon, m_lat, m_lon)
                            if dist_km < 0.1:
                                continue

                            # Predicted path loss
                            predicted_pl = self.okumura_hata_path_loss(freq_mhz, tx_height, rx_height, dist_km, env_type)

                            # Actual path loss
                            actual_pl = env_tx_power - rsrp

                            # Error
                            error = abs(predicted_pl - actual_pl)
                            errors.append(error)
                            corrections.append(actual_pl - predicted_pl)

                        if errors:
                            avg_error = np.mean(errors)
                            avg_correction = np.mean(corrections)

                            if avg_error < best_error:
                                best_error = avg_error
                                best_environment = env_type
                                best_tx_power = env_tx_power
                                best_correction = avg_correction

                    # Calibrated power represents isotropic radiated power
                    # Add typical antenna gain to get effective radiated power
                    # 5G Broadcast at 626 MHz uses high-power transmitters with sector antennas
                    TYPICAL_ANTENNA_GAIN = 17.0  # dB - typical for 5G broadcast sector antennas

                    tx_power_calibrated = best_tx_power
                    tx_power = tx_power_calibrated + TYPICAL_ANTENNA_GAIN

                    # Apply reasonable bounds for 5G Broadcast
                    MIN_TX_POWER = 55.0  # dBm - minimum for 5G Broadcast (similar to DVB-T2)
                    MAX_TX_POWER = 75.0  # dBm - maximum for broadcast
                    tx_power = np.clip(tx_power, MIN_TX_POWER, MAX_TX_POWER)

                    print(f"[PREDICTION] 5G Broadcast @ 626 MHz: Calibrated {tx_power_calibrated:.1f}dBm + Antenna {TYPICAL_ANTENNA_GAIN:.1f}dB = {tx_power:.1f}dBm ERP")

                    print(f"[PREDICTION] Transmitter {tx_id} (PCI {tx_pci}): Calibrated TxPower={tx_power:.1f}dBm (ERP), Environment={best_environment}, Error={best_error:.1f}dB from {len(meas)} measurements")
                else:
                    # Tx power is configured, just find best environment
                    tx_power = tx_power_config
                    best_environment = 'suburban'
                    best_error = float('inf')
                    best_correction = 0

                    # For DVB-T2 broadcast, only test urban/suburban
                    for env_type in ['urban', 'suburban']:
                        errors = []
                        corrections = []

                        for m in meas:
                            m_lat = m.get('lat')
                            m_lon = m.get('lon')
                            rsrp = m.get('rsrp')

                            if m_lat is None or m_lon is None or rsrp is None:
                                continue

                            dist_km = self.haversine_distance(tx_lat, tx_lon, m_lat, m_lon)
                            if dist_km < 0.1:
                                continue

                            # Calculate theoretical path loss using Okumura-Hata
                            predicted_pl = self.okumura_hata_path_loss(freq_mhz, tx_height, rx_height, dist_km, env_type)

                            # Actual path loss from measurement
                            actual_pl = tx_power - rsrp

                            # Error between predicted and actual
                            error = abs(predicted_pl - actual_pl)
                            errors.append(error)
                            corrections.append(actual_pl - predicted_pl)

                        if errors:
                            avg_error = np.mean(errors)
                            avg_correction = np.mean(corrections)

                            if avg_error < best_error:
                                best_error = avg_error
                                best_environment = env_type
                                best_correction = avg_correction

                    print(f"[PREDICTION] Transmitter {tx_id} (PCI {tx_pci}): Using configured TxPower={tx_power}dBm, Calibrated Environment={best_environment}, Error={best_error:.1f}dB")

                    # When using configured ERP, don't apply correction - trust the user's value
                    tx_params[tx_id] = {
                        'environment': best_environment,
                        'correction': 0.0,  # No correction for manually configured ERP
                        'tx_power': tx_power,
                        'height': tx_height,
                        'lat': tx_lat,
                        'lon': tx_lon,
                        'pci': tx_pci,
                        'manual_erp': True,  # Flag to use model predictions instead of interpolation
                        'antennaGains': tx.get('antennaGains', [0, 0, 0, 0, 0, 0, 0, 0])
                    }
                    continue  # Skip to next transmitter
                print(f"[PREDICTION] Transmitter {tx_id} (PCI {tx_pci}): Environment={best_environment}, TxPower={tx_power:.1f}dBm, Correction={best_correction:.2f}dB, Error={best_error:.2f}dB")

                # Save calibrated transmitter parameters
                tx_params[tx_id] = {
                    'environment': best_environment,
                    'correction': best_correction,
                    'tx_power': tx_power,
                    'height': tx_height,
                    'lat': tx_lat,
                    'lon': tx_lon,
                    'pci': tx_pci,
                    'antennaGains': tx.get('antennaGains', [0, 0, 0, 0, 0, 0, 0, 0])
                }
            else:
                # Not enough measurements, use default values
                if tx_power_config is None:
                    tx_power = 60  # Default for 5G Broadcast @ 626 MHz (typical: 55-70 dBm ERP)
                    print(f"[PREDICTION] Transmitter {tx_id} (PCI {tx_pci}): Insufficient measurements (<5), using default 5G Broadcast ERP={tx_power}dBm @ 626 MHz")
                else:
                    tx_power = tx_power_config
                    print(f"[PREDICTION] Transmitter {tx_id} (PCI {tx_pci}): Using configured ERP={tx_power}dBm")

                tx_params[tx_id] = {
                    'environment': 'suburban',  # Suburban as middle ground for broadcast
                    'correction': 0,
                    'tx_power': tx_power,
                    'height': tx_height,
                    'lat': tx_lat,
                    'lon': tx_lon,
                    'pci': tx.get('pci'),
                    'antennaGains': tx.get('antennaGains', [0, 0, 0, 0, 0, 0, 0, 0])
                }

        # Step 3: Generate prediction grid
        # Use current map view bounds with reasonable padding
        # This creates manageable grid cell sizes for accurate interpolation

        # Start with map view bounds
        view_south = bounds.get('_southWest', {}).get('lat', 59.42)
        view_west = bounds.get('_southWest', {}).get('lng', 24.72)
        view_north = bounds.get('_northEast', {}).get('lat', 59.45)
        view_east = bounds.get('_northEast', {}).get('lng', 24.76)

        # Add 20% padding to show coverage beyond current view
        lat_span = view_north - view_south
        lon_span = view_east - view_west
        lat_padding = lat_span * 0.2
        lon_padding = lon_span * 0.2

        south = view_south - lat_padding
        north = view_north + lat_padding
        west = view_west - lon_padding
        east = view_east + lon_padding

        print(f"[PREDICTION] Grid bounds based on map view with 20% padding")
        print(f"[PREDICTION] Coverage area: {south:.4f} to {north:.4f} lat, {west:.4f} to {east:.4f} lon")

        # Create adaptive grid based on zoom level for optimal performance and detail
        # Base grid size determines the smaller dimension
        # Higher resolution at all zoom levels for better detail
        if zoom <= 8:
            base_grid_size = 150  # Country view - higher resolution
        elif zoom <= 11:
            base_grid_size = 120  # Region view
        elif zoom <= 14:
            base_grid_size = 100  # City view
        else:
            base_grid_size = 100  # Street view

        # Calculate aspect ratio-adjusted grid for more square cells
        # At high latitudes, longitude degrees are shorter in physical distance
        center_lat = (north + south) / 2
        lat_range = north - south
        lon_range = east - west

        # Adjust longitude range for latitude (1° lon ≈ 1° lat × cos(lat))
        lon_range_adjusted = lon_range * math.cos(math.radians(center_lat))

        # Calculate grid dimensions to make cells roughly square
        aspect_ratio = lon_range_adjusted / lat_range

        if aspect_ratio > 1:
            # Map is wider than tall
            grid_size_lat = base_grid_size
            grid_size_lon = int(base_grid_size * aspect_ratio)
        else:
            # Map is taller than wide
            grid_size_lon = base_grid_size
            grid_size_lat = int(base_grid_size / aspect_ratio)

        lat_step = lat_range / grid_size_lat
        lon_step = lon_range / grid_size_lon

        print(f"[PREDICTION] Grid: {grid_size_lat}x{grid_size_lon} (aspect ratio: {aspect_ratio:.2f})")
        grid_size = max(grid_size_lat, grid_size_lon)  # For logging compatibility

        predicted_points = []

        # For planning-style visualization, use ONLY uniform grid (no individual measurement points)
        # Grid cells will use measured data via interpolation when available
        # This creates a smooth, continuous coverage map like planning software

        # Use large interpolation radius to capture coverage gradients
        # This ensures coverage extends from transmitter through measurement points
        max_interpolation_radius_km = 50.0  # Large radius to capture transmitter-to-measurement paths
        print(f"[PREDICTION] Interpolation radius: {max_interpolation_radius_km:.1f}km")

        # Calculate maximum coverage distance for each transmitter
        # For manual ERP: use theoretical model-based distance
        # For calibrated ERP: use measured distance + 5km
        max_coverage_distance_per_tx = {}
        print(f"[PREDICTION] TX params keys: {list(tx_params.keys())}")
        for tx_id, params in tx_params.items():
            if params.get('manual_erp', False):
                # Manual ERP configured - calculate theoretical max distance based on propagation model
                theoretical_max = self.calculate_theoretical_max_distance(
                    tx_power=params['tx_power'],
                    freq_mhz=freq_mhz,
                    tx_height=params['height'],
                    rx_height=rx_height,
                    environment=params['environment'],
                    rsrp_threshold=-115  # Edge of coverage
                )
                max_coverage_distance_per_tx[tx_id] = theoretical_max
                print(f"[PREDICTION] TX {tx_id} (PCI {params.get('pci')}): Manual ERP={params['tx_power']:.1f}dBm → Theoretical max distance={theoretical_max:.1f}km")
            else:
                # Calibrated ERP - use farthest measurement + 5km
                max_dist = 0
                for m in measurements:
                    m_lat = m.get('lat')
                    m_lon = m.get('lon')
                    if m_lat is not None and m_lon is not None:
                        # Check if this measurement is from this transmitter (by PCI)
                        if m.get('pci') == params.get('pci'):
                            dist_km = self.haversine_distance(params['lat'], params['lon'], m_lat, m_lon)
                            max_dist = max(max_dist, dist_km)
                # Add 5km buffer beyond farthest measurement
                max_coverage_distance_per_tx[tx_id] = max_dist + 5.0

                # Show antenna pattern info
                antenna_gains = params.get('antennaGains', [0, 0, 0, 0, 0, 0, 0, 0])
                has_pattern = any(g != 0 for g in antenna_gains)
                if has_pattern:
                    sectors = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
                    pattern_info = ', '.join([f"{sectors[i]}:{antenna_gains[i]:+.0f}dB" for i in range(8) if antenna_gains[i] != 0])
                    print(f"[PREDICTION] TX {tx_id} (PCI {params.get('pci')}): Farthest measurement at {max_dist:.1f}km → Coverage extends to {max_dist + 5.0:.1f}km (base)")
                    print(f"[PREDICTION] TX {tx_id}: Directional antenna pattern: {pattern_info}")
                else:
                    print(f"[PREDICTION] TX {tx_id} (PCI {params.get('pci')}): Farthest measurement at {max_dist:.1f}km → Coverage extends to {max_dist + 5.0:.1f}km (omnidirectional)")

        print(f"[PREDICTION] Coverage distances: {max_coverage_distance_per_tx}")

        # Track directional boundary effects for diagnostics
        directional_rejections = 0
        total_grid_cells = 0

        # Time the grid generation
        import time
        grid_start_time = time.time()

        # Build spatial index for fast measurement lookup (10-20x speedup)
        print("[PREDICTION] Building spatial index for measurements...")
        spatial_index = {}
        index_grid_size = 20  # 20x20 spatial grid
        index_lat_step = lat_range / index_grid_size
        index_lon_step = lon_range / index_grid_size

        for m in measurements:
            m_lat = m.get('lat')
            m_lon = m.get('lon')
            if m_lat is not None and m_lon is not None:
                # Calculate which spatial grid cell this measurement belongs to
                index_lat = int((m_lat - south) / index_lat_step)
                index_lon = int((m_lon - west) / index_lon_step)
                # Clamp to valid range
                index_lat = max(0, min(index_grid_size - 1, index_lat))
                index_lon = max(0, min(index_grid_size - 1, index_lon))

                key = f"{index_lat},{index_lon}"
                if key not in spatial_index:
                    spatial_index[key] = []
                spatial_index[key].append(m)

        print(f"[PREDICTION] Spatial index built: {len(spatial_index)} cells with measurements")

        # Now generate prediction grid for interpolation
        for i in range(grid_size_lat):
            for j in range(grid_size_lon):
                lat = south + i * lat_step
                lon = west + j * lon_step
                total_grid_cells += 1

                # Early exit: Check if cell is beyond all transmitter coverage areas
                # This avoids expensive processing for cells that are obviously outside coverage
                # Also cache distance and antenna gain calculations for this cell
                within_any_possible_coverage = False
                cell_tx_distances = {}  # Cache distances to avoid recalculation
                cell_antenna_gains = {}  # Cache antenna gains to avoid recalculation

                for tx_id, params in tx_params.items():
                    dist_to_tx = self.haversine_distance(params['lat'], params['lon'], lat, lon)
                    cell_tx_distances[tx_id] = dist_to_tx

                    # Pre-calculate antenna gain for this cell (expensive atan2 calculation)
                    antenna_gain = self.calculate_antenna_gain(
                        params['lat'], params['lon'], lat, lon,
                        params.get('antennaGains', [0, 0, 0, 0, 0, 0, 0, 0])
                    )
                    cell_antenna_gains[tx_id] = antenna_gain

                    max_possible_distance = max_coverage_distance_per_tx.get(tx_id, 0) + 5.0  # Include gray zone
                    if dist_to_tx <= max_possible_distance:
                        within_any_possible_coverage = True
                        # Don't break - continue to cache all distances and gains

                if not within_any_possible_coverage:
                    # Cell is beyond all coverage areas - mark as no coverage and skip processing
                    predicted_points.append({
                        'lat': lat,
                        'lon': lon,
                        'rsrp': -200.0,
                        'rsrq': -50.0,
                        'source': 'no_coverage'
                    })
                    continue

                # Try to interpolate from nearby measurements first
                nearby_measurements = []
                nearby_no_signal_measurements = []

                # Use spatial index to get candidate measurements (much faster!)
                # Check this cell and surrounding cells in spatial index
                index_lat = int((lat - south) / index_lat_step)
                index_lon = int((lon - west) / index_lon_step)
                index_lat = max(0, min(index_grid_size - 1, index_lat))
                index_lon = max(0, min(index_grid_size - 1, index_lon))

                # Search radius: check 3x3 grid around current cell (covers ~50km at Estonia scale)
                candidate_measurements = []
                for di in range(-1, 2):
                    for dj in range(-1, 2):
                        check_lat = index_lat + di
                        check_lon = index_lon + dj
                        if 0 <= check_lat < index_grid_size and 0 <= check_lon < index_grid_size:
                            key = f"{check_lat},{check_lon}"
                            if key in spatial_index:
                                candidate_measurements.extend(spatial_index[key])

                # Now only iterate through candidate measurements (much smaller set!)
                for m in candidate_measurements:
                    m_lat = m.get('lat')
                    m_lon = m.get('lon')
                    m_rsrp = m.get('rsrp')
                    m_rsrq = m.get('rsrq')

                    if m_lat is not None and m_lon is not None:
                        dist_km = self.haversine_distance(m_lat, m_lon, lat, lon)

                        if dist_km < max_interpolation_radius_km:
                            if m_rsrp is None or m_rsrp < -140:
                                # Measurement point with no signal detected
                                nearby_no_signal_measurements.append({
                                    'lat': m_lat,
                                    'lon': m_lon,
                                    'dist_km': dist_km
                                })
                            elif m_rsrp is not None:
                                # Measurement point with valid signal
                                nearby_measurements.append({
                                    'lat': m_lat,
                                    'lon': m_lon,
                                    'rsrp': m_rsrp,
                                    'rsrq': m_rsrq if m_rsrq is not None else m_rsrp - 10,
                                    'dist_km': dist_km
                                })

                # If there are nearby "no signal" measurements, check if they're closer than any signal measurements
                if nearby_no_signal_measurements:
                    min_no_signal_dist = min(m['dist_km'] for m in nearby_no_signal_measurements)
                    # If no-signal measurement is within 2km, mark this cell as no coverage
                    if min_no_signal_dist < 2.0:
                        if not nearby_measurements or min_no_signal_dist < min(m['dist_km'] for m in nearby_measurements):
                            # Closer to no-signal measurement than any signal measurement
                            predicted_points.append({
                                'lat': lat,
                                'lon': lon,
                                'rsrp': -140.0,
                                'rsrq': -30.0,
                                'source': 'outside'
                            })
                            continue

                # If we have nearby measurements, check if cell is within measured coverage area first
                # CRITICAL: Don't interpolate beyond farthest measurement point
                if len(nearby_measurements) >= 1:
                    # Find distance to nearest transmitter and check coverage boundary
                    min_dist_to_tx = float('inf')
                    nearest_tx_params = None
                    nearest_tx_id = None
                    within_coverage_boundary = False

                    for tx_id, params in tx_params.items():
                        # Use cached distance instead of recalculating
                        dist_to_tx = cell_tx_distances[tx_id]
                        if dist_to_tx < min_dist_to_tx:
                            min_dist_to_tx = dist_to_tx
                            nearest_tx_params = params
                            nearest_tx_id = tx_id

                        # Check if within coverage boundary (farthest measurement + 5km)
                        # Apply directional antenna gain to boundary check
                        max_coverage_dist = max_coverage_distance_per_tx.get(tx_id, 0)

                        # Use cached antenna gain instead of recalculating
                        antenna_gain = cell_antenna_gains[tx_id]

                        # Adjust coverage distance based on antenna gain
                        if antenna_gain != 0:
                            distance_factor = 10 ** (antenna_gain / 35.0)
                            adjusted_coverage_dist = max_coverage_dist * distance_factor
                        else:
                            adjusted_coverage_dist = max_coverage_dist

                        if dist_to_tx <= adjusted_coverage_dist:
                            within_coverage_boundary = True

                    # ONLY interpolate if within coverage boundary
                    if not within_coverage_boundary:
                        # Beyond farthest measurement - mark as gray or no coverage
                        directional_rejections += 1
                        # Debug: First cell that gets rejected
                        if i == 0 and j == 0:
                            print(f"[PREDICTION] DEBUG: Cell ({lat:.4f}, {lon:.4f}) rejected - dist_to_tx={min_dist_to_tx:.1f}km, boundary check failed")
                        # Check if within gray zone (up to 5km beyond coverage boundary)
                        # Also apply directional antenna gain to gray zone
                        in_gray_zone = False
                        for tx_id, params in tx_params.items():
                            # Use cached distance instead of recalculating
                            dist_km = cell_tx_distances[tx_id]
                            max_coverage_dist = max_coverage_distance_per_tx.get(tx_id, 0)

                            # Use cached antenna gain instead of recalculating
                            antenna_gain = cell_antenna_gains[tx_id]

                            # Adjust coverage distance based on antenna gain
                            if antenna_gain != 0:
                                distance_factor = 10 ** (antenna_gain / 35.0)
                                adjusted_coverage_dist = max_coverage_dist * distance_factor
                            else:
                                adjusted_coverage_dist = max_coverage_dist

                            if adjusted_coverage_dist < dist_km <= adjusted_coverage_dist + 5.0:
                                in_gray_zone = True
                                break

                        if in_gray_zone:
                            predicted_points.append({
                                'lat': lat,
                                'lon': lon,
                                'rsrp': -140.0,
                                'rsrq': -30.0,
                                'source': 'outside'
                            })
                        else:
                            predicted_points.append({
                                'lat': lat,
                                'lon': lon,
                                'rsrp': -200.0,
                                'rsrq': -50.0,
                                'source': 'no_coverage'
                            })
                        continue

                    # Within coverage boundary - proceed with interpolation
                    min_dist_to_measurement = min(m['dist_km'] for m in nearby_measurements)

                    # If closer to transmitter than any measurement, use model prediction with boost
                    if min_dist_to_tx < min_dist_to_measurement and min_dist_to_tx < 15.0:
                        # Use model prediction near transmitter
                        dist_km = max(0.1, min_dist_to_tx)

                        path_loss = self.okumura_hata_path_loss(
                            freq_mhz,
                            nearest_tx_params['height'],
                            rx_height,
                            dist_km,
                            nearest_tx_params['environment']
                        )

                        path_loss += nearest_tx_params['correction']

                        # Use cached antenna gain instead of recalculating
                        antenna_gain = cell_antenna_gains[nearest_tx_id]

                        rsrp = nearest_tx_params['tx_power'] - path_loss + antenna_gain
                        rsrq = rsrp - 10

                        predicted_points.append({
                            'lat': lat,
                            'lon': lon,
                            'rsrp': round(rsrp, 1),
                            'rsrq': round(rsrq, 1),
                            'source': 'interpolated'
                        })
                    else:
                        # Use IDW interpolation with very strong emphasis on nearest measurement
                        # This ensures cells near measurements directly reflect those measurements

                        # OPTIMIZATION: Limit to K nearest measurements for speed
                        # Sort by distance and take only the 10 closest
                        # This provides consistent results across zoom levels
                        nearby_measurements_sorted = sorted(nearby_measurements, key=lambda m: m['dist_km'])
                        nearby_measurements_limited = nearby_measurements_sorted[:10]

                        # Find distance to nearest measurement
                        min_meas_dist = nearby_measurements_limited[0]['dist_km']

                        # Very aggressive IDW power - nearest measurement dominates
                        # This prevents green areas from being averaged down to yellow/red
                        if min_meas_dist < 0.3:
                            idw_power = 12  # Extreme emphasis - nearly 100% nearest measurement
                        elif min_meas_dist < 0.5:
                            idw_power = 10  # Very strong emphasis
                        elif min_meas_dist < 1.0:
                            idw_power = 8   # Strong emphasis
                        elif min_meas_dist < 2.0:
                            idw_power = 6   # Moderate emphasis
                        elif min_meas_dist < 5.0:
                            idw_power = 4   # Some emphasis
                        else:
                            idw_power = 3   # Standard IDW

                        weighted_rsrp = 0
                        weighted_rsrq = 0
                        weight_sum = 0

                        for m in nearby_measurements_limited:
                            # Weight by inverse distance with aggressive power
                            if m['dist_km'] < 0.01:
                                weight = 1000000.0  # Extremely close - use measurement directly
                            else:
                                weight = 1.0 / (m['dist_km'] ** idw_power)

                            # Give extra weight to strong measurements, but only within realistic range
                            # This prevents green from extending unrealistically far (>80km)
                            signal_quality_multiplier = 1.0
                            if m['rsrp'] > -95:  # Green coverage (good signal)
                                # Green boost decreases with distance - only effective within 15km
                                if m['dist_km'] < 5.0:
                                    signal_quality_multiplier = 50.0  # Strong boost nearby
                                elif m['dist_km'] < 10.0:
                                    signal_quality_multiplier = 20.0  # Moderate boost
                                elif m['dist_km'] < 15.0:
                                    signal_quality_multiplier = 5.0   # Small boost
                                # Beyond 15km: no boost (multiplier = 1.0)
                            elif m['rsrp'] > -105:  # Yellow coverage (moderate signal)
                                # Yellow boost only within 8km
                                if m['dist_km'] < 5.0:
                                    signal_quality_multiplier = 5.0
                                elif m['dist_km'] < 8.0:
                                    signal_quality_multiplier = 2.0
                            # Red/gray get no boost (multiplier = 1.0)

                            weight *= signal_quality_multiplier

                            weighted_rsrp += m['rsrp'] * weight
                            weighted_rsrq += m['rsrq'] * weight
                            weight_sum += weight

                        if weight_sum > 0:
                            interpolated_rsrp = weighted_rsrp / weight_sum
                            interpolated_rsrq = weighted_rsrq / weight_sum

                            # NO boost - respect actual measured values
                            # Interpolation should reflect real-world measurements, not optimistic predictions

                            predicted_points.append({
                                'lat': lat,
                                'lon': lon,
                                'rsrp': round(interpolated_rsrp, 1),
                                'rsrq': round(interpolated_rsrq, 1),
                                'source': 'interpolated'
                            })
                else:
                    # No nearby measurements - check if within coverage area
                    # For manual ERP: use theoretical max distance
                    # For calibrated ERP: use measured distance + 5km
                    # Apply directional antenna gain to coverage area check
                    within_coverage_area = False
                    for tx_id, params in tx_params.items():
                        # Use cached distance instead of recalculating
                        dist_km = cell_tx_distances[tx_id]
                        max_coverage_dist = max_coverage_distance_per_tx.get(tx_id, 0)

                        # Use cached antenna gain instead of recalculating
                        antenna_gain = cell_antenna_gains[tx_id]

                        # Adjust coverage distance based on antenna gain
                        # Path loss scales logarithmically: 10*log10(d^n) where n≈3.5 for suburban
                        # So a -40dB antenna gain reduces max distance by factor of ~3-4x
                        # Using: new_dist = old_dist * 10^(gain_dB / 35)
                        # This gives realistic range reduction: -40dB → ~0.25x range (4x reduction)
                        if antenna_gain < 0:
                            distance_factor = 10 ** (antenna_gain / 35.0)
                            adjusted_coverage_dist = max_coverage_dist * distance_factor
                        else:
                            # Positive gain extends coverage proportionally
                            distance_factor = 10 ** (antenna_gain / 35.0)
                            adjusted_coverage_dist = max_coverage_dist * distance_factor

                        if dist_km <= adjusted_coverage_dist:
                            within_coverage_area = True
                            break

                    if within_coverage_area:
                        # Predict signal strength from all transmitters using model
                        # Use maximum RSRP from all transmitters (best server selection)
                        best_rsrp = -140  # Very weak signal
                        best_rsrq = -20

                        for tx_id, params in tx_params.items():
                            # Use cached distance instead of recalculating
                            dist_km = cell_tx_distances[tx_id]

                            if dist_km < 0.1:  # Minimum distance 100m
                                dist_km = 0.1

                            # Calculate path loss using Okumura-Hata model
                            path_loss = self.okumura_hata_path_loss(
                                freq_mhz,
                                params['height'],
                                rx_height,
                                dist_km,
                                params['environment']
                            )

                            # Apply calibration correction
                            path_loss += params['correction']

                            # Use cached antenna gain instead of recalculating
                            antenna_gain = cell_antenna_gains[tx_id]

                            # Calculate RSRP with Okumura-Hata propagation
                            rsrp = params['tx_power'] - path_loss + antenna_gain

                            # No coverage boost for pure model predictions
                            # Pure predictions should be conservative - only show strong signal areas
                            # This prevents showing green coverage in unmeasured areas

                            # Estimate RSRQ (simplified: RSRQ ≈ RSRP - 10)
                            # For 5G Broadcast, RSRQ is less critical than RSRP
                            rsrq = rsrp - 10

                            if rsrp > best_rsrp:
                                best_rsrp = rsrp
                                best_rsrq = rsrq

                        predicted_points.append({
                            'lat': lat,
                            'lon': lon,
                            'rsrp': round(best_rsrp, 1),
                            'rsrq': round(best_rsrq, 1),
                            'source': 'predicted'
                        })
                    else:
                        # Check if within gray zone (up to 5km beyond coverage area)
                        # Also apply directional antenna gain to gray zone
                        in_gray_zone = False
                        for tx_id, params in tx_params.items():
                            # Use cached distance instead of recalculating
                            dist_km = cell_tx_distances[tx_id]
                            max_coverage_dist = max_coverage_distance_per_tx.get(tx_id, 0)

                            # Use cached antenna gain instead of recalculating
                            antenna_gain = cell_antenna_gains[tx_id]

                            # Adjust coverage distance based on antenna gain
                            if antenna_gain < 0:
                                distance_factor = 10 ** (antenna_gain / 35.0)
                                adjusted_coverage_dist = max_coverage_dist * distance_factor
                            else:
                                distance_factor = 10 ** (antenna_gain / 35.0)
                                adjusted_coverage_dist = max_coverage_dist * distance_factor

                            # Gray extends up to 5km beyond coverage boundary (also scaled)
                            if adjusted_coverage_dist < dist_km <= adjusted_coverage_dist + 5.0:
                                in_gray_zone = True
                                break

                        if in_gray_zone:
                            # 5-10km beyond measured area - show as gray (unusable)
                            predicted_points.append({
                                'lat': lat,
                                'lon': lon,
                                'rsrp': -140.0,
                                'rsrq': -30.0,
                                'source': 'outside'
                            })
                        else:
                            # Beyond gray zone - mark as no coverage (frontend should skip)
                            predicted_points.append({
                                'lat': lat,
                                'lon': lon,
                                'rsrp': -200.0,  # Special value indicating no coverage
                                'rsrq': -50.0,
                                'source': 'no_coverage'
                            })

        # Time grid generation
        grid_end_time = time.time()
        grid_time_ms = (grid_end_time - grid_start_time) * 1000
        print(f"[PREDICTION] Grid generation completed in {grid_time_ms:.1f}ms")

        # Calculate statistics for diagnostics
        interpolated_count = len([p for p in predicted_points if p['source'] == 'interpolated'])
        predicted_count = len([p for p in predicted_points if p['source'] == 'predicted'])
        outside_count = len([p for p in predicted_points if p['source'] == 'outside'])
        no_coverage_count = len([p for p in predicted_points if p['source'] == 'no_coverage'])

        print(f"[PREDICTION] ====== COVERAGE PREDICTION SUMMARY ======")
        print(f"[PREDICTION] Grid: {grid_size_lat}x{grid_size_lon} = {grid_size_lat*grid_size_lon} cells")
        print(f"[PREDICTION] Bounds: ({south:.4f}, {west:.4f}) to ({north:.4f}, {east:.4f})")
        print(f"[PREDICTION] Source measurements: {len(measurements)} points")
        print(f"[PREDICTION] Generated {len(predicted_points)} grid cells:")
        print(f"[PREDICTION]   - Interpolated (from measurements): {interpolated_count}")
        print(f"[PREDICTION]   - Predicted (model only): {predicted_count}")
        print(f"[PREDICTION]   - Outside measured area (gray): {outside_count}")
        print(f"[PREDICTION]   - No coverage (beyond gray): {no_coverage_count}")
        if directional_rejections > 0:
            rejection_pct = (directional_rejections / total_grid_cells) * 100
            print(f"[PREDICTION] Directional antenna boundaries rejected {directional_rejections} cells ({rejection_pct:.1f}%)")

        predicted_rsrp_values = [p['rsrp'] for p in predicted_points if p['source'] == 'predicted']
        if predicted_rsrp_values:
            min_rsrp = min(predicted_rsrp_values)
            max_rsrp = max(predicted_rsrp_values)
            avg_rsrp = sum(predicted_rsrp_values) / len(predicted_rsrp_values)
            print(f"[PREDICTION] Predicted RSRP range: {min_rsrp:.1f} to {max_rsrp:.1f} dBm (avg: {avg_rsrp:.1f} dBm)")

        interpolated_rsrp_values = [p['rsrp'] for p in predicted_points if p['source'] == 'interpolated']
        if interpolated_rsrp_values:
            min_rsrp = min(interpolated_rsrp_values)
            max_rsrp = max(interpolated_rsrp_values)
            avg_rsrp = sum(interpolated_rsrp_values) / len(interpolated_rsrp_values)
            print(f"[PREDICTION] Interpolated RSRP range: {min_rsrp:.1f} to {max_rsrp:.1f} dBm (avg: {avg_rsrp:.1f} dBm)")

        # Validate predictions against actual measurements
        # For interpolated and predicted points, find nearby measurements and calculate error
        validation_errors = []
        validation_radius_km = 0.5  # 500m radius for validation

        for point in predicted_points:
            if point['source'] in ['interpolated', 'predicted']:
                # Find nearby actual measurements
                nearby_actual = []
                for m in measurements:
                    m_lat = m.get('lat')
                    m_lon = m.get('lon')
                    m_rsrp = m.get('rsrp')
                    if m_lat is not None and m_lon is not None and m_rsrp is not None:
                        dist_km = self.haversine_distance(point['lat'], point['lon'], m_lat, m_lon)
                        if dist_km < validation_radius_km:
                            nearby_actual.append({'rsrp': m_rsrp, 'dist_km': dist_km})

                # If there are very close measurements, calculate error
                if nearby_actual:
                    # Use closest measurement for validation
                    closest = min(nearby_actual, key=lambda x: x['dist_km'])
                    error = abs(point['rsrp'] - closest['rsrp'])
                    validation_errors.append({
                        'source': point['source'],
                        'error': error,
                        'predicted': point['rsrp'],
                        'actual': closest['rsrp'],
                        'distance_km': closest['dist_km']
                    })

        # Calculate validation metrics
        validation_metrics = {}
        if validation_errors:
            errors_by_source = {
                'interpolated': [e['error'] for e in validation_errors if e['source'] == 'interpolated'],
                'predicted': [e['error'] for e in validation_errors if e['source'] == 'predicted']
            }

            for source, errors in errors_by_source.items():
                if errors:
                    mae = np.mean(errors)
                    rmse = np.sqrt(np.mean([e**2 for e in errors]))
                    validation_metrics[source] = {
                        'mae': round(mae, 1),
                        'rmse': round(rmse, 1),
                        'count': len(errors)
                    }
                    print(f"[VALIDATION] {source.capitalize()} error: MAE={mae:.1f}dB, RMSE={rmse:.1f}dB (n={len(errors)})")

        # Total prediction time
        prediction_end_time = time.time()
        total_time_ms = (prediction_end_time - prediction_start_time) * 1000
        print(f"[PREDICTION] ====== TOTAL PREDICTION TIME: {total_time_ms:.1f}ms ======")

        return {
            'success': True,
            'points': predicted_points,
            'model': 'Okumura-Hata',
            'frequency_mhz': freq_mhz,
            'grid': {
                'size_lat': grid_size_lat,
                'size_lon': grid_size_lon,
                'bounds': {
                    'south': south,
                    'north': north,
                    'west': west,
                    'east': east
                },
                'lat_step': lat_step,
                'lon_step': lon_step,
                'aspect_ratio': aspect_ratio
            },
            'calibration': {
                tx_id: {
                    'environment': p['environment'],
                    'correction_db': p['correction']
                } for tx_id, p in tx_params.items()
            },
            'validation': validation_metrics,
            'statistics': {
                'source_measurements': len(measurements),
                'interpolated': interpolated_count,
                'predicted': predicted_count,
                'total': len(predicted_points)
            }
        }

    def haversine_distance(self, lat1, lon1, lat2, lon2):
        """Calculate distance between two points in kilometers"""
        R = 6371  # Earth's radius in km

        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)

        a = math.sin(delta_lat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        return R * c

    def calculate_antenna_gain(self, tx_lat, tx_lon, point_lat, point_lon, antenna_gains):
        """
        Calculate antenna gain based on direction from transmitter to point

        Args:
            tx_lat, tx_lon: Transmitter coordinates
            point_lat, point_lon: Target point coordinates
            antenna_gains: Array of 8 gain values in dB for [N, NE, E, SE, S, SW, W, NW]

        Returns:
            Antenna gain in dB for the direction to the point
        """
        # Calculate bearing from transmitter to point
        lat1 = math.radians(tx_lat)
        lat2 = math.radians(point_lat)
        delta_lon = math.radians(point_lon - tx_lon)

        x = math.sin(delta_lon) * math.cos(lat2)
        y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(delta_lon)

        bearing = math.atan2(x, y)
        bearing_degrees = (math.degrees(bearing) + 360) % 360  # Normalize to 0-360

        # Map bearing to one of 8 sectors (N=0, NE=45, E=90, SE=135, S=180, SW=225, W=270, NW=315)
        # Each sector covers 45 degrees
        sector_index = int((bearing_degrees + 22.5) / 45) % 8

        return antenna_gains[sector_index]

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

    def handle_cb_import_local(self):
        """Import CB message log from local upload"""
        try:
            # Read request body
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8'))

            msg_id = data.get('msg_id')
            content = data.get('content')

            if not msg_id or not content:
                self.send_response(400)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': False,
                    'error': 'Missing msg_id or content'
                }).encode('utf-8'))
                return

            # Ensure directories exist
            CB_LOGS_DIR.mkdir(exist_ok=True)
            DATA_DIR.mkdir(exist_ok=True)

            local_path = CB_LOGS_DIR / f"{msg_id}.json"

            # Check if file already exists
            if local_path.exists():
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': True,
                    'skipped': True,
                    'message': 'CB message already exists'
                }).encode('utf-8'))
                return

            # Parse and validate CB message
            try:
                cb_record = json.loads(content)
            except json.JSONDecodeError:
                self.send_response(400)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': False,
                    'error': 'Invalid JSON format'
                }).encode('utf-8'))
                return

            # Write the file
            local_path.write_text(content)

            # Update CB index
            update_cb_index_entry(msg_id, cb_record)

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                'success': True,
                'skipped': False,
                'message': 'CB message imported successfully'
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
