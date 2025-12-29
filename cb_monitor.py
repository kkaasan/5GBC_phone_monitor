#!/usr/bin/env python3
"""
Cell Broadcast Monitor - Main Backend Script
Handles ADB log capture, data management, and web interface updates
"""

import os
import sys
import json
import csv
import re
import subprocess
import signal
import time
from datetime import datetime, timedelta
from pathlib import Path
from threading import Thread, Event
import http.server
import socketserver

# Configuration
DATA_DIR = Path(__file__).parent / "data"
LOGS_DIR = Path(__file__).parent / "logs"
CB_LOGS_DIR = Path(__file__).parent / "cb_logs"
STATIC_DIR = Path(__file__).parent / "static"
STATUS_FILE = DATA_DIR / "status.json"
DATA_INDEX_FILE = DATA_DIR / "data_index.json"
CB_INDEX_FILE = DATA_DIR / "cb_index.json"
SNAPSHOT_INTERVAL = 30  # seconds

# ADB path - try common locations
ADB_PATH = '/opt/homebrew/bin/adb'  # Default for Apple Silicon Mac
if not os.path.exists(ADB_PATH):
    ADB_PATH = '/usr/local/bin/adb'  # Intel Mac
if not os.path.exists(ADB_PATH):
    ADB_PATH = 'adb'  # Fallback to PATH

# Ensure directories exist
DATA_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)
CB_LOGS_DIR.mkdir(exist_ok=True)
STATIC_DIR.mkdir(exist_ok=True)

class CBMonitor:
    def __init__(self):
        self.running = False
        self.stop_event = Event()
        self.current_session = None
        self.data_points = []
        self.cb_messages = []
        self.logcat_process = None

    def check_adb(self):
        """Check if ADB is available"""
        try:
            result = subprocess.run([ADB_PATH, 'devices'],
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                devices = [line for line in result.stdout.split('\n')
                          if line and not line.startswith('List')]
                if devices:
                    print(f"✅ ADB connected: {devices[0]}")
                    return True
                else:
                    print("⚠️  No devices connected")
                    return False
            return False
        except FileNotFoundError:
            print("❌ ADB not found. Please install Android SDK Platform Tools")
            print("   Download from: https://developer.android.com/studio/releases/platform-tools")
            return False
        except Exception as e:
            print(f"❌ ADB error: {e}")
            return False

    def get_device_info(self):
        """Get device brand and model"""
        try:
            brand = subprocess.check_output(['adb', 'shell', 'getprop', 'ro.product.brand'],
                                          text=True, timeout=5).strip()
            model = subprocess.check_output(['adb', 'shell', 'getprop', 'ro.product.model'],
                                          text=True, timeout=5).strip()
            return f"{brand} {model}"
        except:
            return "Unknown Device"

    def normalize_value(self, value):
        """Normalize signal values (handle invalid values)"""
        if value is None or value in ['-', '', 'null', '2147483647', '-2147483648']:
            return None
        try:
            val = int(value)
            if val == 2147483647 or val == -2147483648:
                return None
            return val
        except:
            return None

    def get_cell_info(self):
        """Get current cell info and signal strength"""
        data = {}

        try:
            # Method 1: Try dumpsys telephony.registry first (most reliable)
            print("   Trying dumpsys telephony.registry...")
            result = subprocess.run([ADB_PATH, 'shell', 'dumpsys', 'telephony.registry'],
                                  capture_output=True, text=True, timeout=10)

            if result.returncode == 0:
                reg_out = result.stdout

                # Look for CellIdentityLte data in the entire output
                # Extract all cell identity fields
                cell_patterns = {
                    'tac': r'mTac[=:\s]+(\d+)',
                    'earfcn': r'mEarfcn[=:\s]+(\d+)',
                    'mcc': r'mMcc[=:\s]+(\d+)',
                    'mnc': r'mMnc[=:\s]+(\d+)',
                    'ci': r'mCi[=:\s]+(\d+)',
                    'pci': r'mPci[=:\s]+(\d+)',
                }

                for field, pattern in cell_patterns.items():
                    # Find all matches
                    all_matches = re.findall(pattern, reg_out)
                    if all_matches:
                        # Filter out invalid markers (2147483647 = invalid/unset)
                        valid_values = []
                        for val in all_matches:
                            int_val = int(val)
                            # Skip the specific invalid marker
                            if int_val == 2147483647 or int_val < 0:
                                continue

                            # Apply normalization for specific fields
                            if field in ['tac', 'ci']:
                                normalized = self.normalize_value(val)
                                if normalized is not None:
                                    valid_values.append(str(normalized))
                            else:
                                valid_values.append(val)

                        if valid_values:
                            data[field] = valid_values[0]
                            print(f"   ✅ Found {field}: {data[field]}")
                        else:
                            print(f"   ⚠️  {field} values found but all invalid: {all_matches[:3]}")

                # Look for signal strength - search ALL instances and pick valid ones
                sig_patterns = {
                    'rssi': r'(?:mRssi|rssi|Rssi)[=:\s]+(-?\d+)',
                    'rsrp': r'(?:mRsrp|rsrp|Rsrp)[=:\s]+(-?\d+)',
                    'rsrq': r'(?:mRsrq|rsrq|Rsrq)[=:\s]+(-?\d+)',
                }

                for field, pattern in sig_patterns.items():
                    # Find ALL matches for this field
                    all_matches = re.findall(pattern, reg_out)
                    print(f"   Found {len(all_matches)} {field} values: {all_matches[:5]}...")

                    # Filter out invalid values and pick the first valid one
                    valid_values = [self.normalize_value(m) for m in all_matches]
                    valid_values = [v for v in valid_values if v is not None]

                    if valid_values:
                        data[field] = valid_values[0]
                        print(f"   ✅ Using {field}: {data[field]} dBm")
                    else:
                        print(f"   ⚠️  No valid {field} found (all were invalid/2147483647)")

                # Also try looking in ServiceState sections
                service_state_matches = re.findall(r'ServiceState=\{[^}]+\}', reg_out)
                if service_state_matches and ('rssi' not in data or data['rssi'] is None):
                    print(f"   Searching {len(service_state_matches)} ServiceState sections...")
                    for ss in service_state_matches:
                        for field, pattern in sig_patterns.items():
                            if field not in data or data[field] is None:
                                match = re.search(pattern, ss)
                                if match:
                                    val = self.normalize_value(match.group(1))
                                    if val is not None:
                                        data[field] = val
                                        print(f"   ✅ Found {field} in ServiceState: {val}")

            # Method 2: Try cmd phone cell-info as backup
            if not data or 'rssi' not in data or data.get('rssi') is None:
                print("   Trying cmd phone cell-info...")
                result = subprocess.run([ADB_PATH, 'shell', 'cmd', 'phone', 'cell-info'],
                                      capture_output=True, text=True, timeout=5)

                if result.returncode == 0 and 'Unknown' not in result.stdout:
                    ci_out = result.stdout

                    # Look for LTE info
                    lte_match = re.search(r'CellInfoLte.*?mTac=(\d+).*?mEarfcn=(\d+).*?mMcc=(\d+).*?mMnc=(\d+).*?mCi=(\d+).*?mPci=(\d+)', ci_out, re.DOTALL)
                    if lte_match:
                        data['tac'] = lte_match.group(1)
                        data['earfcn'] = lte_match.group(2)
                        data['mcc'] = lte_match.group(3)
                        data['mnc'] = lte_match.group(4)
                        data['ci'] = lte_match.group(5)
                        data['pci'] = lte_match.group(6)

                    # Look for signal
                    sig_match = re.search(r'rssi=(-?\d+).*?rsrp=(-?\d+).*?rsrq=(-?\d+)', ci_out)
                    if sig_match:
                        data['rssi'] = self.normalize_value(sig_match.group(1))
                        data['rsrp'] = self.normalize_value(sig_match.group(2))
                        data['rsrq'] = self.normalize_value(sig_match.group(3))

            # Log what we got
            if data:
                print(f"   ✅ Extracted: MCC={data.get('mcc')}, MNC={data.get('mnc')}, PCI={data.get('pci')}, RSSI={data.get('rssi')}")
            else:
                print("   ⚠️  No cell data found")

            return data

        except subprocess.TimeoutExpired:
            print(f"   ⚠️  Timeout getting cell info")
            return {}
        except Exception as e:
            print(f"   ⚠️  Error getting cell info: {e}")
            import traceback
            traceback.print_exc()
            return {}

    def get_location(self):
        """Get current GPS location"""
        try:
            print("   Getting GPS location...")
            result = subprocess.run([ADB_PATH, 'shell', 'dumpsys', 'location'],
                                  capture_output=True, text=True, timeout=5)

            if result.returncode != 0:
                print("   ⚠️  Location dumpsys failed")
                return {'latitude': None, 'longitude': None}

            # Try GPS first
            gps_match = re.search(r'last location=Location\[[^\s]+\s+([\d.-]+),([\d.-]+)',
                                result.stdout)
            if gps_match:
                lat = gps_match.group(1)
                lon = gps_match.group(2)
                print(f"   ✅ GPS: {lat}, {lon}")
                return {
                    'latitude': lat,
                    'longitude': lon
                }

            # Try any location
            any_match = re.search(r'Location\[[^\s]+\s+([\d.-]+),([\d.-]+)', result.stdout)
            if any_match:
                lat = any_match.group(1)
                lon = any_match.group(2)
                print(f"   ✅ Location (not GPS): {lat}, {lon}")
                return {
                    'latitude': lat,
                    'longitude': lon
                }

            print("   ⚠️  No GPS location found")
            return {'latitude': None, 'longitude': None}
        except Exception as e:
            print(f"   ⚠️  Error getting location: {e}")
            return {'latitude': None, 'longitude': None}

    def parse_cb_message(self, log_lines):
        """Parse Cell Broadcast message from logcat lines"""
        try:
            cb_data = {}
            message_lines = []

            for line in log_lines:
                # Extract SmsCbMessage details
                if 'SmsCbMessage{' in line:
                    # Parse all the fields
                    match = re.search(r'geographicalScope=(\d+)', line)
                    if match:
                        cb_data['geographicalScope'] = int(match.group(1))

                    match = re.search(r'serialNumber=(\d+)', line)
                    if match:
                        cb_data['serialNumber'] = int(match.group(1))

                    match = re.search(r'location=\[([^\]]+)\]', line)
                    if match:
                        cb_data['location'] = match.group(1)

                    match = re.search(r'serviceCategory=(\d+)', line)
                    if match:
                        cb_data['serviceCategory'] = int(match.group(1))

                    match = re.search(r'language=(\w+)', line)
                    if match:
                        cb_data['language'] = match.group(1)

                    match = re.search(r'priority=(\d+)', line)
                    if match:
                        cb_data['priority'] = int(match.group(1))

                    match = re.search(r'received time=(\d+)', line)
                    if match:
                        cb_data['receivedTime'] = int(match.group(1))

                    match = re.search(r'slotIndex = (\d+)', line)
                    if match:
                        cb_data['slotIndex'] = int(match.group(1))

                    match = re.search(r'geo=([^}]+)', line)
                    if match:
                        cb_data['geo'] = match.group(1).strip()

                    # Extract SmsCbCmasInfo
                    match = re.search(r'SmsCbCmasInfo\{messageClass=(-?\d+), category=(-?\d+), responseType=(-?\d+), severity=(-?\d+), urgency=(-?\d+), certainty=(-?\d+)\}', line)
                    if match:
                        cb_data['cmasInfo'] = {
                            'messageClass': int(match.group(1)),
                            'category': int(match.group(2)),
                            'responseType': int(match.group(3)),
                            'severity': int(match.group(4)),
                            'urgency': int(match.group(5)),
                            'certainty': int(match.group(6))
                        }

                    match = re.search(r'maximumWaitingTime=(\d+)', line)
                    if match:
                        cb_data['maximumWaitingTime'] = int(match.group(1))

                    # Extract body (it's after "body=" and can span multiple lines)
                    body_match = re.search(r'body=(.+)', line)
                    if body_match:
                        body_text = body_match.group(1)
                        # Remove trailing metadata if present
                        if ', priority=' in body_text:
                            body_text = body_text.split(', priority=')[0]
                        message_lines.append(body_text)

                # Check for message body continuation (lines that are just message content)
                elif 'GsmCellBroadcastHandler' in line and any(x in line for x in ['D/GsmCellBroadcastHandler']) and not any(x in line for x in ['SmsCbMessage', 'Dispatching', 'Found', 'compare', 'Duplicate', 'Not a duplicate']):
                    # Extract just the message part after the log prefix
                    parts = line.split('GsmCellBroadcastHandler(')
                    if len(parts) > 1:
                        message_part = parts[1].split('): ', 1)
                        if len(message_part) > 1:
                            content = message_part[1].strip()
                            if content and content not in message_lines:
                                message_lines.append(content)

            # Join all message lines
            if message_lines:
                cb_data['body'] = '\n'.join(message_lines).strip()

            if cb_data and 'body' in cb_data:
                return cb_data
            return None

        except Exception as e:
            print(f"   ⚠️  Error parsing CB message: {e}")
            return None

    def monitor_logcat(self):
        """Monitor logcat for Cell Broadcast messages"""
        try:
            # Clear logcat first
            subprocess.run([ADB_PATH, 'logcat', '-c'], timeout=5)

            # Start logcat monitoring
            self.logcat_process = subprocess.Popen(
                [ADB_PATH, 'logcat', '-v', 'time', 'GsmCellBroadcastHandler:D', '*:S'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1
            )

            print("   📻 CB logcat monitoring started")

            current_message_lines = []
            in_message = False

            while not self.stop_event.is_set() and self.running:
                line = self.logcat_process.stdout.readline()
                if not line:
                    break

                # Detect start of new CB message
                if 'Not a duplicate message' in line or 'Duplicate message detected' in line:
                    # Save previous message if exists
                    if current_message_lines and in_message:
                        cb_msg = self.parse_cb_message(current_message_lines)
                        if cb_msg:
                            self.save_cb_message(cb_msg)

                    # Start new message
                    current_message_lines = [line]
                    in_message = True

                elif in_message:
                    current_message_lines.append(line)

                    # Check if message is complete
                    if 'release wakelock' in line or 'call cancel' in line or 'broadcast complete' in line:
                        cb_msg = self.parse_cb_message(current_message_lines)
                        if cb_msg:
                            self.save_cb_message(cb_msg)
                        current_message_lines = []
                        in_message = False

        except Exception as e:
            print(f"   ⚠️  Error in logcat monitoring: {e}")
        finally:
            if self.logcat_process:
                self.logcat_process.terminate()
                self.logcat_process = None

    def save_cb_message(self, cb_data):
        """Save CB message to file and index"""
        try:
            timestamp = datetime.now()

            # Get current location to associate with message
            location = self.get_location()

            # Create full CB message record
            cb_record = {
                'timestamp': timestamp.isoformat(),
                'receivedTime': cb_data.get('receivedTime'),
                'serialNumber': cb_data.get('serialNumber'),
                'serviceCategory': cb_data.get('serviceCategory'),
                'body': cb_data.get('body', ''),
                'language': cb_data.get('language'),
                'priority': cb_data.get('priority'),
                'geographicalScope': cb_data.get('geographicalScope'),
                'location': cb_data.get('location'),
                'geo': cb_data.get('geo'),
                'cmasInfo': cb_data.get('cmasInfo'),
                'maximumWaitingTime': cb_data.get('maximumWaitingTime'),
                'slotIndex': cb_data.get('slotIndex'),
                'coordinates': location
            }

            # Generate unique ID for this message
            msg_id = f"{timestamp.strftime('%Y%m%d_%H%M%S')}_{cb_data.get('serialNumber', 0)}"

            # Save to file
            cb_file = CB_LOGS_DIR / f"{msg_id}.json"
            with open(cb_file, 'w') as f:
                json.dump(cb_record, f, indent=2)

            # Update CB index
            self.update_cb_index(msg_id, cb_record)

            # Extract title from body (first line)
            title = cb_record['body'].split('\n')[0][:100] if cb_record['body'] else 'CB Message'

            print(f"\n🚨 CB Message Received: {title}")
            print(f"   ID: {msg_id}")
            print(f"   Priority: {cb_record['priority']}")

            self.cb_messages.append(cb_record)

        except Exception as e:
            print(f"   ⚠️  Error saving CB message: {e}")

    def update_cb_index(self, msg_id, cb_record):
        """Update CB message index"""
        try:
            if CB_INDEX_FILE.exists():
                with open(CB_INDEX_FILE, 'r') as f:
                    index = json.load(f)
            else:
                index = {'messages': []}

            # Extract heading from body
            heading = cb_record['body'].split('\n')[0][:100] if cb_record['body'] else 'CB Message'

            # Create index entry
            index_entry = {
                'id': msg_id,
                'timestamp': cb_record['timestamp'],
                'heading': heading,
                'priority': cb_record.get('priority'),
                'language': cb_record.get('language'),
                'serviceCategory': cb_record.get('serviceCategory')
            }

            # Check if already exists (avoid duplicates)
            existing = [m for m in index['messages'] if m['id'] == msg_id]
            if not existing:
                index['messages'].insert(0, index_entry)  # Add to beginning

                with open(CB_INDEX_FILE, 'w') as f:
                    json.dump(index, f, indent=2)

        except Exception as e:
            print(f"   ⚠️  Error updating CB index: {e}")

    def capture_snapshot(self):
        """Capture a single network snapshot"""
        timestamp = datetime.now()

        print(f"\n📡 Capturing snapshot at {timestamp.strftime('%H:%M:%S')}...")

        cell_info = self.get_cell_info()
        location = self.get_location()

        snapshot = {
            'timestamp': timestamp.isoformat(),
            'lte': {
                'tac': cell_info.get('tac', '-'),
                'earfcn': cell_info.get('earfcn', '-'),
                'mcc': cell_info.get('mcc', '-'),
                'mnc': cell_info.get('mnc', '-'),
                'ci': cell_info.get('ci', '-'),
                'pci': cell_info.get('pci', '-')
            },
            'signal': {
                'rssi': cell_info.get('rssi'),
                'rsrp': cell_info.get('rsrp'),
                'rsrq': cell_info.get('rsrq'),
                'snr': None  # SNR not always available
            },
            'location': location
        }

        return snapshot

    def update_status(self, snapshot):
        """Update current status file for live dashboard"""
        # Add session_id to status for dashboard to know which session is active
        status_data = snapshot.copy()
        status_data['session_id'] = self.current_session

        with open(STATUS_FILE, 'w') as f:
            json.dump(status_data, f, indent=2)

    def save_to_log(self, snapshot):
        """Save snapshot to current session log file"""
        if not self.current_session:
            return

        log_file = LOGS_DIR / f"{self.current_session}.jsonl"
        with open(log_file, 'a') as f:
            f.write(json.dumps(snapshot) + '\n')

        # Also save to data points for session
        self.data_points.append(snapshot)

    def start_session(self):
        """Start a new monitoring session"""
        session_id = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.current_session = session_id
        self.data_points = []

        print(f"\n📡 Starting session: {session_id}")
        print(f"   Log file: logs/{session_id}.jsonl")
        print(f"   Interval: {SNAPSHOT_INTERVAL}s")
        print(f"   Press Ctrl+C to stop\n")

        return session_id

    def stop_session(self):
        """Stop current session and update index"""
        if not self.current_session or not self.data_points:
            return

        session_id = self.current_session

        # Calculate session metadata
        start_time = datetime.fromisoformat(self.data_points[0]['timestamp'])
        end_time = datetime.fromisoformat(self.data_points[-1]['timestamp'])

        # Get location bounds
        lats = [float(p['location']['latitude']) for p in self.data_points
                if p['location']['latitude']]
        lons = [float(p['location']['longitude']) for p in self.data_points
                if p['location']['longitude']]

        metadata = {
            'session_id': session_id,
            'start_time': start_time.isoformat(),
            'end_time': end_time.isoformat(),
            'count': len(self.data_points),
            'bounds': {
                'min_lat': min(lats) if lats else None,
                'max_lat': max(lats) if lats else None,
                'min_lon': min(lons) if lons else None,
                'max_lon': max(lons) if lons else None
            }
        }

        # Update data index
        self.update_data_index(metadata)

        print(f"\n✅ Session saved: {session_id}")
        print(f"   Data points: {len(self.data_points)}")
        print(f"   Duration: {end_time - start_time}")

        self.current_session = None
        self.data_points = []

    def update_data_index(self, session_metadata):
        """Update the data index with new session"""
        if DATA_INDEX_FILE.exists():
            with open(DATA_INDEX_FILE, 'r') as f:
                index = json.load(f)
        else:
            index = {'sessions': []}

        # Add or update session
        existing = [s for s in index['sessions']
                   if s['session_id'] == session_metadata['session_id']]
        if existing:
            index['sessions'].remove(existing[0])

        index['sessions'].append(session_metadata)
        index['sessions'].sort(key=lambda x: x['start_time'], reverse=True)

        with open(DATA_INDEX_FILE, 'w') as f:
            json.dump(index, f, indent=2)

    def monitoring_loop(self):
        """Main monitoring loop"""
        self.running = True

        while not self.stop_event.is_set():
            try:
                snapshot = self.capture_snapshot()

                # Update live status
                self.update_status(snapshot)

                # Save to log
                self.save_to_log(snapshot)

                # Print status
                lat = snapshot['location']['latitude'] or '-'
                lon = snapshot['location']['longitude'] or '-'
                rssi = snapshot['signal']['rssi']
                rsrp = snapshot['signal']['rsrp']

                print(f"[{snapshot['timestamp']}] "
                      f"RSSI: {rssi if rssi else '-':>4} | "
                      f"RSRP: {rsrp if rsrp else '-':>4} | "
                      f"GPS: {lat},{lon}")

                # Wait for next interval
                self.stop_event.wait(SNAPSHOT_INTERVAL)

            except Exception as e:
                print(f"⚠️  Error in monitoring loop: {e}")
                time.sleep(5)

        self.running = False

    def start_monitoring(self):
        """Start the monitoring process"""
        if not self.check_adb():
            return False

        device = self.get_device_info()
        print(f"📱 Device: {device}")

        self.start_session()

        # Handle Ctrl+C gracefully
        def signal_handler(sig, frame):
            print("\n\n⏹️  Stopping monitoring...")
            self.stop_event.set()

        signal.signal(signal.SIGINT, signal_handler)

        # Start monitoring thread
        monitor_thread = Thread(target=self.monitoring_loop)
        monitor_thread.start()

        # Start CB logcat monitoring thread
        logcat_thread = Thread(target=self.monitor_logcat, daemon=True)
        logcat_thread.start()

        # Wait for completion
        monitor_thread.join()

        # Stop logcat monitoring
        self.stop_event.set()
        if self.logcat_process:
            self.logcat_process.terminate()

        # Save session
        self.stop_session()

        # Clear status.json to prevent dashboard from showing stale data
        if STATUS_FILE.exists():
            STATUS_FILE.unlink()
            print("   Cleared status file")

        return True

def export_to_csv(session_id, output_file=None):
    """Export session data to CSV"""
    log_file = LOGS_DIR / f"{session_id}.jsonl"

    if not log_file.exists():
        print(f"❌ Session not found: {session_id}")
        return False

    if not output_file:
        output_file = DATA_DIR / f"{session_id}.csv"

    # Read data
    data_points = []
    with open(log_file, 'r') as f:
        for line in f:
            data_points.append(json.loads(line))

    # Write CSV
    with open(output_file, 'w', newline='') as f:
        fieldnames = [
            'timestamp', 'latitude', 'longitude',
            'rssi', 'rsrp', 'rsrq', 'snr',
            'mcc', 'mnc', 'tac', 'ci', 'pci', 'earfcn'
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
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

    print(f"✅ CSV exported: {output_file}")
    print(f"   Records: {len(data_points)}")
    return True

def list_sessions():
    """List all available sessions"""
    if not DATA_INDEX_FILE.exists():
        print("No sessions found")
        return

    with open(DATA_INDEX_FILE, 'r') as f:
        index = json.load(f)

    print("\n📊 Available Sessions:\n")
    for session in index['sessions']:
        start = datetime.fromisoformat(session['start_time'])
        end = datetime.fromisoformat(session['end_time'])
        duration = end - start

        print(f"  {session['session_id']}")
        print(f"    Time: {start.strftime('%Y-%m-%d %H:%M:%S')} - {end.strftime('%H:%M:%S')}")
        print(f"    Duration: {duration}")
        print(f"    Points: {session['count']}")
        print()

def start_web_server(port=8888):
    """Start simple HTTP server for web interface with API support"""
    os.chdir(Path(__file__).parent)

    # Global monitor instance for API access
    monitor = CBMonitor()
    TRANSMITTERS_FILE = DATA_DIR / "transmitters.json"

    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, format, *args):
            """Override to add custom logging"""
            sys.stderr.write("[SERVER]  %s - - [%s] %s\n" %
                           (self.address_string(),
                            self.log_date_time_string(),
                            format%args))

        def end_headers(self):
            self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
            self.send_header('Expires', '0')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type')
            super().end_headers()

        def do_OPTIONS(self):
            """Handle CORS preflight"""
            print(f"[API] OPTIONS {self.path}")
            self.send_response(200)
            self.end_headers()

        def do_GET(self):
            """Handle GET requests"""
            # Strip query string from path
            path = self.path.split('?')[0]

            print(f"[API] GET {path}")

            if path.startswith('/api/monitor/status'):
                self.handle_monitor_status()
            elif path.startswith('/api/export/'):
                session_id = path.split('/')[-1]
                self.handle_export(session_id)
            elif path.startswith('/api/cb/list'):
                print(f"[API] Handling CB list request")
                self.handle_cb_list()
            elif path.startswith('/api/cb/message/'):
                msg_id = path.split('/')[-1]
                print(f"[API] Handling CB message request for: {msg_id}")
                self.handle_cb_message(msg_id)
            else:
                super().do_GET()

        def do_POST(self):
            """Handle POST requests"""
            print(f"[API] POST {self.path}")
            try:
                if self.path == '/api/monitor/start':
                    self.handle_monitor_start()
                elif self.path == '/api/monitor/stop':
                    self.handle_monitor_stop()
                elif self.path == '/api/transmitters/save':
                    self.handle_transmitters_save()
                else:
                    print(f"[API] No handler for: {self.path}")
                    self.send_error(404, "API endpoint not found")
            except Exception as e:
                print(f"[API ERROR] {e}")
                import traceback
                traceback.print_exc()
                self.send_error(500, str(e))

        def handle_monitor_status(self):
            """Get monitoring status"""
            status = {
                'running': monitor.running,
                'device': None
            }

            if monitor.check_adb():
                status['device'] = {'model': monitor.get_device_info()}

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(status).encode())

        def handle_monitor_start(self):
            """Start monitoring"""
            if monitor.running:
                response = {'success': False, 'error': 'Already running'}
            else:
                # Start monitoring in background thread
                def start_bg():
                    monitor.start_monitoring()

                Thread(target=start_bg, daemon=True).start()
                time.sleep(1)  # Give it time to start
                response = {'success': True}

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(response).encode())

        def handle_monitor_stop(self):
            """Stop monitoring"""
            if not monitor.running:
                response = {'success': False, 'error': 'Not running'}
            else:
                monitor.stop_event.set()
                response = {'success': True}

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(response).encode())

        def handle_export(self, session_id):
            """Export session to CSV"""
            output_file = DATA_DIR / f"{session_id}.csv"

            if export_to_csv(session_id, output_file):
                # Send CSV file
                self.send_response(200)
                self.send_header('Content-Type', 'text/csv')
                self.send_header('Content-Disposition', f'attachment; filename="{session_id}.csv"')
                self.end_headers()

                with open(output_file, 'rb') as f:
                    self.wfile.write(f.read())
            else:
                self.send_error(404, "Session not found")

        def handle_transmitters_save(self):
            """Save transmitter configuration"""
            try:
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)
                data = json.loads(post_data.decode('utf-8'))

                # Save to file
                with open(TRANSMITTERS_FILE, 'w') as f:
                    json.dump(data, f, indent=2)

                response = {'success': True}
                self.send_response(200)
            except Exception as e:
                response = {'success': False, 'error': str(e)}
                self.send_response(500)

            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(response).encode())

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
                self.wfile.write(json.dumps(index).encode())
            except Exception as e:
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
                    self.wfile.write(json.dumps(message).encode())
                else:
                    self.send_error(404, "Message not found")
            except Exception as e:
                self.send_error(500, str(e))

    # Verify Handler class has do_POST
    print(f"[STARTUP] Handler has do_POST: {hasattr(Handler, 'do_POST')}")
    print(f"[STARTUP] Transmitters file: {TRANSMITTERS_FILE}")

    with socketserver.TCPServer(("", port), Handler) as httpd:
        print(f"\n🌐 Web server started: http://localhost:{port}")
        print(f"   Home: http://localhost:{port}/index.html")
        print(f"   Dashboard: http://localhost:{port}/dashboard.html")
        print(f"   Heatmap: http://localhost:{port}/heatmap.html")
        print(f"   Emergency Warnings: http://localhost:{port}/emergency_warnings.html")
        print(f"   Settings: http://localhost:{port}/settings.html")
        print(f"   API endpoints: /api/monitor/*, /api/transmitters/*, /api/export/*, /api/cb/*")
        print(f"   Press Ctrl+C to stop\n")

        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n⏹️  Server stopped")

def main():
    import argparse

    parser = argparse.ArgumentParser(description='Cell Broadcast Monitor')
    parser.add_argument('command', nargs='?', default='monitor',
                       choices=['monitor', 'export', 'list', 'serve'],
                       help='Command to execute')
    parser.add_argument('--session', help='Session ID for export')
    parser.add_argument('--output', help='Output file for export')
    parser.add_argument('--port', type=int, default=8888, help='Web server port')

    args = parser.parse_args()

    if args.command == 'monitor':
        monitor = CBMonitor()
        monitor.start_monitoring()

    elif args.command == 'export':
        if not args.session:
            print("❌ Please specify --session")
            return
        export_to_csv(args.session, args.output)

    elif args.command == 'list':
        list_sessions()

    elif args.command == 'serve':
        start_web_server(args.port)

if __name__ == '__main__':
    main()
