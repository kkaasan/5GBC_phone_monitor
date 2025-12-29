#!/usr/bin/env python3
"""
Import Cell Broadcast messages from log dump files
Place your log dump files in: cb_monitor/cb_dumps/
Then run: python3 import_cb_logs.py
"""

import os
import json
import re
from datetime import datetime
from pathlib import Path

# Directories
CB_DUMPS_DIR = Path(__file__).parent / "cb_dumps"
CB_LOGS_DIR = Path(__file__).parent / "cb_logs"
DATA_DIR = Path(__file__).parent / "data"
CB_INDEX_FILE = DATA_DIR / "cb_index.json"

# Ensure directories exist
CB_DUMPS_DIR.mkdir(exist_ok=True)
CB_LOGS_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)

def parse_cb_message_from_dump(log_lines):
    """Parse Cell Broadcast message from log dump lines"""
    try:
        cb_data = {}
        message_lines = []
        log_timestamp = None

        for line in log_lines:
            # Extract timestamp from log line (format: 10-29 13:36:48.766)
            ts_match = re.match(r'^(\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d{3})', line)
            if ts_match and not log_timestamp:
                log_timestamp = ts_match.group(1)

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
            elif 'GsmCellBroadcastHandler' in line and any(x in line for x in ['D/GsmCellBroadcastHandler']) and not any(x in line for x in ['SmsCbMessage', 'Dispatching', 'Found', 'compare', 'Duplicate', 'Not a duplicate', 'Idle:', 'Waiting:', 'call cancel', 'Airplane mode']):
                # Extract just the message part after the log prefix
                parts = line.split('): ')
                if len(parts) > 1:
                    content = parts[-1].strip()
                    if content and content not in message_lines and len(content) > 2:
                        message_lines.append(content)

        # Join all message lines
        if message_lines:
            full_body = '\n'.join(message_lines).strip()

            # Clean up body - remove metadata that got included
            # Find where actual metadata starts (after the real message)
            if ', priority=' in full_body:
                # Split at priority and take everything before it
                body_parts = full_body.split(', priority=')
                cb_data['body'] = body_parts[0].strip()

                # Parse the metadata that was in the body
                metadata_part = ', priority=' + body_parts[1]

                # Extract priority if not already set
                if 'priority' not in cb_data or cb_data['priority'] is None:
                    match = re.search(r'priority=(\d+)', metadata_part)
                    if match:
                        cb_data['priority'] = int(match.group(1))

                # Extract geo if not already set
                if 'geo' not in cb_data or cb_data['geo'] is None:
                    match = re.search(r'geo=(polygon\|[^}]+)', metadata_part)
                    if match:
                        cb_data['geo'] = match.group(1).strip()

                # Extract received time if not already set
                if 'receivedTime' not in cb_data or cb_data['receivedTime'] is None:
                    match = re.search(r'received time=(\d+)', metadata_part)
                    if match:
                        cb_data['receivedTime'] = int(match.group(1))

                # Extract slotIndex if not already set
                if 'slotIndex' not in cb_data or cb_data['slotIndex'] is None:
                    match = re.search(r'slotIndex = (\d+)', metadata_part)
                    if match:
                        cb_data['slotIndex'] = int(match.group(1))

                # Extract maximumWaitingTime if not already set
                if 'maximumWaitingTime' not in cb_data or cb_data['maximumWaitingTime'] is None:
                    match = re.search(r'maximumWaitingTime=(\d+)', metadata_part)
                    if match:
                        cb_data['maximumWaitingTime'] = int(match.group(1))

                # Extract CMAS info if not already set
                if 'cmasInfo' not in cb_data or cb_data['cmasInfo'] is None:
                    match = re.search(r'SmsCbCmasInfo\{messageClass=(-?\d+), category=(-?\d+), responseType=(-?\d+), severity=(-?\d+), urgency=(-?\d+), certainty=(-?\d+)\}', metadata_part)
                    if match:
                        cb_data['cmasInfo'] = {
                            'messageClass': int(match.group(1)),
                            'category': int(match.group(2)),
                            'responseType': int(match.group(3)),
                            'severity': int(match.group(4)),
                            'urgency': int(match.group(5)),
                            'certainty': int(match.group(6))
                        }
            else:
                cb_data['body'] = full_body

        if cb_data and 'body' in cb_data:
            cb_data['logTimestamp'] = log_timestamp
            return cb_data
        return None

    except Exception as e:
        print(f"   ⚠️  Error parsing CB message: {e}")
        return None

def extract_gps_from_dump(dump_content):
    """Try to extract GPS coordinates from the dump file"""
    # Look for "Last known location" or GPS coordinates in the dump
    lat_match = re.search(r'Latitude=([\d.-]+)', dump_content)
    lon_match = re.search(r'Longitude=([\d.-]+)', dump_content)

    if lat_match and lon_match:
        lat = lat_match.group(1)
        lon = lon_match.group(1)
        if lat != '-' and lon != '-':
            return {'latitude': lat, 'longitude': lon}

    return {'latitude': None, 'longitude': None}

def import_cb_dump(dump_file):
    """Import CB messages from a single dump file"""
    print(f"\n📄 Processing: {dump_file.name}")

    try:
        with open(dump_file, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        # Extract GPS coordinates if available
        gps_coords = extract_gps_from_dump(content)

        lines = content.split('\n')

        # Find all CB message blocks
        current_message_lines = []
        in_message = False
        messages_found = 0

        for line in lines:
            # Detect start of new CB message
            if 'Not a duplicate message' in line or ('SmsCbMessage{' in line and 'Duplicate message detected' not in line):
                # Save previous message if exists
                if current_message_lines and in_message:
                    cb_msg = parse_cb_message_from_dump(current_message_lines)
                    if cb_msg:
                        save_cb_message(cb_msg, gps_coords, dump_file.stem)
                        messages_found += 1

                # Start new message
                current_message_lines = [line]
                in_message = True

            elif in_message:
                current_message_lines.append(line)

                # Check if message is complete
                if 'release wakelock' in line or 'call cancel' in line or 'broadcast complete' in line or 'Idle:' in line:
                    cb_msg = parse_cb_message_from_dump(current_message_lines)
                    if cb_msg:
                        save_cb_message(cb_msg, gps_coords, dump_file.stem)
                        messages_found += 1
                    current_message_lines = []
                    in_message = False

        # Save last message if exists
        if current_message_lines and in_message:
            cb_msg = parse_cb_message_from_dump(current_message_lines)
            if cb_msg:
                save_cb_message(cb_msg, gps_coords, dump_file.stem)
                messages_found += 1

        print(f"   ✅ Found {messages_found} CB message(s)")
        return messages_found

    except Exception as e:
        print(f"   ❌ Error processing file: {e}")
        return 0

def save_cb_message(cb_data, gps_coords, source_file):
    """Save CB message to file and index"""
    try:
        # Parse timestamp from log or use current time
        if cb_data.get('logTimestamp'):
            # Parse "10-29 13:36:48.766" format
            ts_str = cb_data['logTimestamp']
            # Assume current year
            year = datetime.now().year
            month, day_time = ts_str.split('-', 1)
            day, time_str = day_time.split(' ', 1)
            timestamp = datetime.strptime(f"{year}-{month.zfill(2)}-{day.zfill(2)} {time_str}", "%Y-%m-%d %H:%M:%S.%f")
        else:
            timestamp = datetime.now()

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
            'coordinates': gps_coords,
            'source': source_file
        }

        # Generate unique ID for this message
        msg_id = f"{timestamp.strftime('%Y%m%d_%H%M%S')}_{cb_data.get('serialNumber', 0)}"

        # Save to file
        cb_file = CB_LOGS_DIR / f"{msg_id}.json"
        with open(cb_file, 'w') as f:
            json.dump(cb_record, f, indent=2)

        # Update CB index
        update_cb_index(msg_id, cb_record)

        # Extract title from body (first line)
        title = cb_record['body'].split('\n')[0][:100] if cb_record['body'] else 'CB Message'

        print(f"      💾 Saved: {title[:60]}")

    except Exception as e:
        print(f"   ⚠️  Error saving CB message: {e}")

def update_cb_index(msg_id, cb_record):
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

def main():
    print("🚨 Cell Broadcast Message Importer")
    print("=" * 50)
    print(f"\nLooking for dump files in: {CB_DUMPS_DIR}")

    # Find all dump files
    dump_files = list(CB_DUMPS_DIR.glob("*.txt")) + list(CB_DUMPS_DIR.glob("*.log"))

    if not dump_files:
        print("\n⚠️  No dump files found!")
        print(f"\nPlease place your CB log dump files (.txt or .log) in:")
        print(f"   {CB_DUMPS_DIR}")
        print("\nExample:")
        print(f"   {CB_DUMPS_DIR}/cb_log_20251029_143307.txt")
        return

    print(f"\n📁 Found {len(dump_files)} dump file(s)")

    total_messages = 0
    for dump_file in dump_files:
        messages = import_cb_dump(dump_file)
        total_messages += messages

    print("\n" + "=" * 50)
    print(f"✅ Import complete!")
    print(f"   Total CB messages imported: {total_messages}")
    print(f"   Saved to: {CB_LOGS_DIR}")
    print(f"\n📊 View messages at: http://localhost:8888/emergency_warnings.html")

if __name__ == '__main__':
    main()
