# Cell Broadcast Monitor

Complete monitoring and analysis solution for Cell Broadcast signal testing.

## 📁 Directory Structure

```
cb_monitor/
├── cb_monitor.py          # Main backend script for data capture
├── api_server.py          # Web server with CSV export API
├── index.html             # Main menu/landing page
├── dashboard.html         # Live monitoring dashboard
├── heatmap.html          # Historical heatmap viewer
├── data/                  # Generated data files
│   ├── status.json       # Current live status
│   └── data_index.json   # Session index
├── logs/                  # Session log files (.jsonl)
└── static/               # Additional assets (optional)
```

## 🚀 Quick Start

### Prerequisites

1. **Android SDK Platform Tools** (for ADB)
   - Download: https://developer.android.com/studio/releases/platform-tools
   - Make sure `adb` is in your PATH

2. **Python 3.7+**
   - No additional packages required (uses only stdlib)

3. **Android phone** connected via USB with:
   - USB debugging enabled
   - Location services enabled (for GPS)

### Basic Usage

**1. Start Monitoring**
```bash
cd cb_monitor
python3 cb_monitor.py monitor
```

This will:
- Check ADB connection
- Start capturing data every 30 seconds
- Save to `logs/YYYYMMDD_HHMMSS.jsonl`
- Update `data/status.json` for live dashboard

**2. Start Web Server** (in another terminal)
```bash
python3 api_server.py
```

Or use the simpler http.server:
```bash
python3 -m http.server 8888
```

**3. Open Dashboard**
- Navigate to: http://localhost:8888
- Click "Live Dashboard" to see real-time monitoring
- Click "RSSI Heatmap" to view historical data

**4. Stop Monitoring**
- Press `Ctrl+C` in the monitoring terminal
- Session will be automatically saved and indexed

## 📊 Web Interface

### Live Dashboard (`dashboard.html`)
Real-time monitoring interface with:
- **Signal Gauges**: RSSI, RSRP, RSRQ, SNR values
- **Live Map**: GPS location with route history
- **Network Info**: MCC, MNC, TAC, Cell ID, PCI, EARFCN
- **Session Stats**: Data points, signal range, coverage distance

Updates every 2 seconds from `data/status.json`

### Heatmap Viewer (`heatmap.html`)
Historical data analysis with:
- **Session Selection**: Dropdown of all captured sessions
- **Date/Time Filter**: Filter data by specific time ranges
- **Interactive Map**:
  - 🔥 Heatmap overlay (signal strength gradient)
  - 🛣️ Route line (path traveled)
  - 📍 Markers (individual data points)
- **Export to CSV**: Download session data
- **Signal Color Coding**:
  - 🟢 Green: Excellent (> -80 dBm)
  - 🟡 Yellow: Good (-90 to -80 dBm)
  - 🟠 Orange: Fair (-100 to -90 dBm)
  - 🔴 Red: Poor (< -100 dBm)

## 📝 Command Line Usage

```bash
# Start monitoring
python3 cb_monitor.py monitor

# List all sessions
python3 cb_monitor.py list

# Export session to CSV
python3 cb_monitor.py export --session YYYYMMDD_HHMMSS

# Export with custom output file
python3 cb_monitor.py export --session YYYYMMDD_HHMMSS --output mydata.csv

# Start web server on custom port
python3 api_server.py 9000
```

## 📦 Data Format

### Status JSON (`data/status.json`)
Updated every 30 seconds during monitoring:
```json
{
  "timestamp": "2025-12-10T14:30:15",
  "lte": {
    "tac": "65534",
    "earfcn": "68676",
    "mcc": "248",
    "mnc": "01",
    "ci": "12345",
    "pci": "41"
  },
  "signal": {
    "rssi": -75,
    "rsrp": -95,
    "rsrq": -10,
    "snr": null
  },
  "location": {
    "latitude": "59.437",
    "longitude": "24.745"
  }
}
```

### Session Logs (`logs/*.jsonl`)
One JSON object per line:
```json
{"timestamp":"2025-12-10T14:30:15","lte":{...},"signal":{...},"location":{...}}
{"timestamp":"2025-12-10T14:30:45","lte":{...},"signal":{...},"location":{...}}
```

### CSV Export Format
```csv
timestamp,latitude,longitude,rssi,rsrp,rsrq,snr,mcc,mnc,tac,ci,pci,earfcn
2025-12-10T14:30:15,59.437,24.745,-75,-95,-10,,248,01,65534,12345,41,68676
```

## 🔧 Configuration

Edit `cb_monitor.py` to change:
```python
SNAPSHOT_INTERVAL = 30  # Seconds between captures (default: 30)
```

## 🎯 Use Cases

### Cell Broadcast Testing
1. Start monitoring before CB test
2. View live dashboard to ensure data capture
3. After test, use heatmap to analyze:
   - Signal coverage during CB transmission
   - Dead zones (weak signal areas)
   - Route correlation with signal strength

### Coverage Mapping
1. Start monitoring while driving/walking
2. Heatmap shows coverage quality
3. Export CSV for further GIS analysis

### Network Analysis
1. Track cell tower handovers (PCI/CI changes)
2. Correlate signal with location
3. Identify problem areas

## 📥 CSV Export Features

The CSV export includes ALL network statistics:

| Field | Description |
|-------|-------------|
| `timestamp` | ISO format date/time |
| `latitude` | GPS latitude |
| `longitude` | GPS longitude |
| `rssi` | Received Signal Strength Indicator (dBm) |
| `rsrp` | Reference Signal Received Power (dBm) |
| `rsrq` | Reference Signal Received Quality (dB) |
| `snr` | Signal-to-Noise Ratio (dB) |
| `mcc` | Mobile Country Code |
| `mnc` | Mobile Network Code |
| `tac` | Tracking Area Code |
| `ci` | Cell ID |
| `pci` | Physical Cell ID |
| `earfcn` | E-UTRA Absolute Radio Frequency Channel Number |

## 🗺️ Heatmap Date/Time Filtering

The heatmap viewer allows precise time-range selection:

1. **Select Session**: Choose from dropdown
2. **Select Date**: Pick the date (auto-filled from session)
3. **Set Time Range**:
   - From: Start time (e.g., 10:00)
   - To: End time (e.g., 13:00)
4. **Apply Filter**: Click "Apply Filter"
5. **View Results**: Heatmap updates to show only selected timeframe

**Example**: Filter CB test from 12:30-12:35:
- Date: 2025-12-10
- From: 12:30
- To: 12:35
- Result: Only data points in that 5-minute window

## 🛠️ Troubleshooting

### "ADB not found"
```bash
# Install Android SDK Platform Tools
# macOS with Homebrew:
brew install android-platform-tools

# Or download from:
# https://developer.android.com/studio/releases/platform-tools
```

### "No devices connected"
```bash
# Check device connection:
adb devices

# Enable USB debugging on phone:
# Settings → Developer Options → USB Debugging
```

### "No GPS data"
- Enable Location Services on phone
- May take 30-60 seconds to get GPS lock
- Try outdoor location for better GPS signal

### "No signal data (all '--')"
- Check that phone has mobile network connection
- Try `adb shell cmd phone cell-info` manually
- Some phones may require root or special permissions

### Web interface shows "No data"
- Make sure monitoring is running (`python3 cb_monitor.py monitor`)
- Check that `data/status.json` exists and is updating
- Refresh the browser page

## 📱 Compatible Devices

Tested on:
- ✅ Motorola Edge 50
- ✅ Samsung (most models)
- ✅ Google Pixel phones
- ✅ OnePlus phones

Should work on any Android device with:
- Android 8.0+
- ADB support
- Location services

## 🔐 Privacy & Security

- All data stays on your local machine
- No internet connection required (except map tiles)
- No data sent to external servers
- ADB connection only to connected device

## 📄 License

Created for Cell Broadcast testing and monitoring.
Use freely for testing and analysis purposes.

## 🆘 Support

For issues or questions:
1. Check troubleshooting section above
2. Verify ADB connection: `adb devices`
3. Check log files in `logs/` directory
4. Ensure web server is running on port 8888

## 🎉 Features Summary

✅ Real-time signal monitoring
✅ GPS location tracking
✅ Interactive heatmaps
✅ Historical data viewer
✅ Date/time range filtering
✅ CSV export with all network stats
✅ Route visualization
✅ Cell tower tracking (PCI, Cell ID)
✅ Multiple session management
✅ Zero external dependencies
✅ Works offline (except map tiles)

---

**Version**: 1.0
**Created**: 2025-12-10
**Purpose**: Cell Broadcast signal monitoring and analysis
