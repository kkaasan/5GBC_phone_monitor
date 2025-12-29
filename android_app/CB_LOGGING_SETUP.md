# Cell Broadcast Logging Setup for Android App

The CB Monitor Android app now supports capturing Cell Broadcast (CB) messages directly on the device while logging. This allows you to capture CB messages while mobile, without needing to be connected to a computer.

## How CB Logging Works

The app uses two methods to capture CB messages:

1. **BroadcastReceiver** - Receives CB messages directly from the system (works on some devices)
2. **Logcat Reader** - Captures CB messages from system logs (more reliable, requires permission)

## Setup Instructions

### Method 1: Grant READ_LOGS Permission (Recommended)

The most reliable way to capture CB messages is by granting the READ_LOGS permission via ADB. This allows the app to read logcat and capture CB messages.

**Steps:**

1. **Connect your phone to computer via USB**
   - Enable USB debugging in Developer Options

2. **Grant READ_LOGS permission via ADB:**
   ```bash
   adb shell pm grant ee.levira.cbmonitor android.permission.READ_LOGS
   ```

3. **Start logging in the app**
   - Open the CB Monitor app
   - Tap "Start logging"
   - CB messages will be automatically captured while logging is active

4. **Import CB logs to web interface**
   - Connect phone to computer via ADB
   - Go to Emergency Warnings page in the web interface
   - Click "Import from Phone" button
   - CB messages from the phone will be imported and deleted from device

### Method 2: BroadcastReceiver (Limited)

The app also registers a BroadcastReceiver for CB messages. This may work on some devices/ROMs without additional setup, but is not guaranteed due to system restrictions.

**No additional setup required** - The receiver is automatically registered and will capture CB messages if the system allows it.

## How to Use

1. **Start Logging:**
   - Open the CB Monitor app
   - Tap "Start logging"
   - Network data will be logged every 30 seconds
   - CB messages will be captured automatically when received

2. **CB Message Storage:**
   - CB messages are saved to: `/Android/data/ee.levira.cbmonitor/files/cb_monitor/cb_logs/`
   - Each message is saved as a separate JSON file
   - Format: `{YYYYMMDD_HHmmss}_{serialNumber}.json`

3. **Import CB Messages:**
   - Connect phone via ADB
   - Open web interface at http://localhost:8888
   - Navigate to "Emergency Warnings" page
   - Click "Import from Phone"
   - Messages will be imported and removed from device

## CB Message Data Format

Each CB message is saved with the following information:

```json
{
  "timestamp": "2024-12-29T14:30:22.123+02:00",
  "receivedTime": 1735476622123,
  "serialNumber": 12345,
  "serviceCategory": 4370,
  "body": "Emergency alert message text...",
  "language": "en",
  "priority": 3,
  "geographicalScope": 1,
  "geo": "polygon|...",
  "cmasInfo": {
    "messageClass": 1,
    "category": 2,
    "responseType": 1,
    "severity": 2,
    "urgency": 1,
    "certainty": 1
  },
  "coordinates": {
    "latitude": "59.123456",
    "longitude": "24.123456"
  },
  "source": "android_logcat"
}
```

## Troubleshooting

### CB Messages Not Being Captured

1. **Check READ_LOGS permission:**
   ```bash
   adb shell dumpsys package ee.levira.cbmonitor | grep READ_LOGS
   ```
   - Should show "granted=true"
   - If not, run the grant command again

2. **Verify CB messages are being broadcast:**
   - Test by sending a test CB message (if you have access to CBC equipment)
   - Check logcat manually:
     ```bash
     adb logcat -v time GsmCellBroadcastHandler:D *:S
     ```

3. **Check app logs:**
   ```bash
   adb logcat -v time LogcatCBLogger:* CBReceiver:* MonitoringService:* *:S
   ```
   - Look for "Starting CB logcat monitoring" message
   - Look for "CB message saved" messages

### Permission Errors

If you see permission errors in logcat:

- Make sure USB debugging is enabled
- Grant READ_LOGS permission again via ADB
- Restart the app after granting permission

### No Import Button in Web Interface

The import functionality is available in the Emergency Warnings page:
- Go to http://localhost:8888/emergency_warnings.html
- Look for "Import from Phone" button
- Make sure ADB is connected and working

## Technical Details

### Logcat Monitoring

The `LogcatCBLogger` class:
- Runs in background coroutine while logging is active
- Filters for `GsmCellBroadcastHandler` messages
- Parses CB message structure from logcat output
- Associates GPS coordinates from current logging session
- Saves each CB message as separate JSON file
- Updates CB index for web interface

### BroadcastReceiver

The `CellBroadcastReceiver` class:
- Registered for CB broadcast intents
- Processes `SmsCbMessage` objects directly
- Works if system allows app to receive CB broadcasts
- Automatically saves messages with GPS coordinates

### Storage Locations

- **Network logs:** `/Android/data/ee.levira.cbmonitor/files/cb_monitor/{session_id}.jsonl`
- **CB logs:** `/Android/data/ee.levira.cbmonitor/files/cb_monitor/cb_logs/{msg_id}.json`
- **CB index:** `/Android/data/ee.levira.cbmonitor/files/cb_monitor/cb_index.json`
- **Status:** `/Android/data/ee.levira.cbmonitor/files/cb_monitor/status.json`

## Web Interface Integration

The web interface provides a unified view of:
- Network monitoring data (heatmaps, signal strength, etc.)
- Emergency CB messages
- Message details including priority, CMAS info, coordinates

All data can be imported from the phone via ADB and viewed/analyzed in the web interface.

## Performance Impact

- Logcat reading uses minimal CPU and battery
- CB messages are typically infrequent (only during emergencies)
- No impact when no CB messages are being broadcast
- Background logging continues with screen off

## Privacy & Security

- CB messages are stored locally on device and your computer
- No data is sent to external servers
- Messages are deleted from phone after import
- All data remains under your control
