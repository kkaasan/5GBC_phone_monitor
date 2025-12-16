# 📡 5G Broadcast Monitor

Professional 5G Broadcast signal analysis and coverage mapping tool for real-time RSRP/RSRQ monitoring with GPS correlation and modulation threshold analysis.

![Version](https://img.shields.io/badge/version-1.0-blue)
![Python](https://img.shields.io/badge/python-3.7+-green)
![License](https://img.shields.io/badge/license-MIT-blue)

## 🌟 Features

- **Real-time Signal Monitoring** - RSRP, RSRQ, RSSI, SNR metrics via ADB
- **GPS-Correlated Tracking** - High-precision location data with route visualization
- **Interactive Heatmap** - Coverage analysis with 16-QAM/QPSK modulation thresholds
- **Live Dashboard** - Real-time gauges, network info, and session statistics
- **Session Management** - Automatic logging, indexing, and historical replay
- **Web Control Interface** - Start/stop monitoring, device status, and session browser
- **CSV Export** - Full parameter export for post-processing and reporting
- **Modulation Analysis** - Signal quality classification based on 3GPP standards

## 📁 Project Structure

```
cb_monitor/
├── cb_monitor.py          # Main monitoring backend (ADB integration)
├── api_server.py          # Web API server with control endpoints
├── start.sh               # Quick-start script (server + monitoring)
├── index.html             # Main control interface
├── dashboard.html         # Live monitoring dashboard
├── heatmap.html          # Coverage heatmap viewer
├── sessions.html         # Session browser and export
├── data/                  # Generated data files
│   ├── status.json       # Current live status (with session_id)
│   └── data_index.json   # Session index and metadata
├── logs/                  # Session log files (.jsonl)
└── test_phone.py         # Device testing utilities
```

## 🚀 Quick Start

### Prerequisites

1. **Android SDK Platform Tools** (ADB)
   ```bash
   # macOS with Homebrew
   brew install android-platform-tools

   # Or download from:
   # https://developer.android.com/studio/releases/platform-tools
   ```

2. **Python 3.7+** (no external packages required)

3. **Android Phone** with:
   - USB debugging enabled
   - Location services enabled
   - 5G Broadcast capable device (recommended)

### Installation

```bash
# Clone the repository
git clone git@github.com:kkaasan/5GBC_phone_monitor.git
cd 5GBC_phone_monitor

# Connect your phone via USB and enable USB debugging
# Accept the "Allow USB debugging" prompt on your phone

# Start the server
./start.sh
```

### Access the Interface

Open your browser and navigate to:
- **Main Menu**: http://localhost:8888/index.html
- **Live Dashboard**: http://localhost:8888/dashboard.html
- **Coverage Heatmap**: http://localhost:8888/heatmap.html
- **Sessions & Export**: http://localhost:8888/sessions.html

## 📊 Web Interface

### 1. Main Control Interface (`index.html`)

**Features:**
- Start/Stop monitoring with web buttons
- Real-time device connection status
- Automatic status updates every 3 seconds
- Links to all monitoring views
- Signal classification guide (16-QAM/QPSK thresholds)

**Usage:**
1. Connect phone via USB
2. Click **"▶️ Start Monitoring"**
3. Navigate to Live Dashboard or Heatmap
4. Click **"⏹️ Stop Monitoring"** when done

### 2. Live Dashboard (`dashboard.html`)

**Features:**
- **Real-time Gauges**: RSSI, RSRP, RSRQ, SNR with circular progress indicators
- **Live Map**: GPS location with complete route history
- **Network Info**: MCC, MNC, TAC, Cell ID, PCI, EARFCN
- **Session Statistics**:
  - Total data points collected
  - Signal range (min/max RSSI)
  - Coverage distance traveled
  - **Persists across page refreshes!**
- **Auto-updates**: Every 2 seconds

**Session Persistence:**
The dashboard loads all historical data from the current session on page load, so statistics remain accurate even after refreshing the page.

### 3. Coverage Heatmap (`heatmap.html`)

**Features:**
- **Session Selection**: Browse all captured sessions
- **Direct Session Links**: Click "View Map" from sessions page to open specific session
- **Date/Time Filtering**: Filter data by specific time ranges
- **Interactive Visualization**:
  - 🔥 **Heatmap**: Signal strength gradient overlay
  - 🛣️ **Route**: Path traveled during monitoring
  - 📍 **Markers**: Individual measurement points with popups
- **Export to CSV**: Download session data
- **Collapsible Controls**: Clean interface with expandable control panel
- **Transmitter Filters**: Heatmap/markers honor active transmitters (by PCI); click tower icons to toggle coverage on/off. At least one transmitter must be active to render heatmap.

**Signal Classification (OR Logic):**
- 🟩 **16-QAM Capable**: RSRP ≥ -95 dBm OR RSRQ ≥ -10 dB
- 🟨 **Better Signal**: RSRP ≥ -105 dBm OR RSRQ ≥ -13 dB
- 🟥 **QPSK Reception**: RSRP ≥ -115 dBm OR RSRQ ≥ -17 dB
- ⚫ **Unusable**: RSRP < -120 dBm AND RSRQ < -20 dB

### 4. Sessions & Export (`sessions.html`)

**Features:**
- Browse all captured sessions with statistics
- Session cards showing:
  - Data point count
  - Session duration
  - Start time
  - GPS availability
- **View Map**: Opens heatmap with selected session pre-loaded
- **Export CSV**: Download session data with all parameters

## 📝 Command Line Usage

### Manual Monitoring

```bash
# Start monitoring (captures every 30 seconds)
python3 cb_monitor.py monitor

# List all sessions
python3 cb_monitor.py list

# Export session to CSV
python3 cb_monitor.py export --session 20251214_163944

# Export with custom output file
python3 cb_monitor.py export --session 20251214_163944 --output my_data.csv
```

### Server Options

```bash
# Start server on custom port
python3 api_server.py 9000

# Use the all-in-one start script
./start.sh
```

## 📦 Data Format

### Status JSON (`data/status.json`)

Updated every 30 seconds with current session:

```json
{
  "timestamp": "2025-12-14T16:47:41.534356",
  "session_id": "20251214_164610",
  "lte": {
    "tac": "65534",
    "earfcn": "68676",
    "mcc": "901",
    "mnc": "56",
    "ci": "1280",
    "pci": "45"
  },
  "signal": {
    "rssi": -63,
    "rsrp": -87,
    "rsrq": -8,
    "snr": null
  },
  "location": {
    "latitude": "59.491133",
    "longitude": "24.912215"
  }
}
```

### Session Index (`data/data_index.json`)

Metadata for all sessions:

```json
{
  "sessions": [
    {
      "session_id": "20251214_163944",
      "start_time": "2025-12-14T16:39:44.216175",
      "end_time": "2025-12-14T16:45:46.493860",
      "count": 13,
      "bounds": {
        "min_lat": 59.491145,
        "max_lat": 59.491178,
        "min_lon": 24.912219,
        "max_lon": 24.912242
      }
    }
  ]
}
```

### Session Logs (`logs/*.jsonl`)

One JSON object per line (JSONL format):

```json
{"timestamp":"2025-12-14T16:47:41","lte":{...},"signal":{...},"location":{...}}
{"timestamp":"2025-12-14T16:48:11","lte":{...},"signal":{...},"location":{...}}
```

### CSV Export Format

```csv
timestamp,latitude,longitude,rssi,rsrp,rsrq,snr,mcc,mnc,tac,ci,pci,earfcn
2025-12-14T16:47:41,59.491133,24.912215,-63,-87,-8,,901,56,65534,1280,45,68676
```

## 🎯 Use Cases

### 5G Broadcast Coverage Testing

1. Start monitoring before broadcast transmission
2. Monitor live signal quality on dashboard
3. Drive/walk through coverage area
4. Stop monitoring after test
5. Analyze coverage heatmap with modulation thresholds
6. Export CSV for reporting

### Network Quality Analysis

1. Track signal metrics over time
2. Identify dead zones and weak signal areas
3. Correlate signal strength with GPS location
4. Monitor cell tower handovers (PCI/CI changes)

### Drive Testing

1. Mount phone in vehicle
2. Start monitoring via web interface
3. Drive planned route
4. Real-time monitoring on passenger device
5. Post-analysis with heatmap filtering

## 🔧 Configuration

Edit `cb_monitor.py` to customize:

```python
# Capture interval (seconds)
SNAPSHOT_INTERVAL = 30  # Default: 30 seconds

# ADB path (auto-detected on macOS)
ADB_PATH = '/opt/homebrew/bin/adb'
```

## 🛠️ Troubleshooting

### No Device Connected

```bash
# Check ADB connection
adb devices -l

# Restart ADB server
adb kill-server
adb start-server

# Verify phone settings:
# - USB Debugging enabled (Developer Options)
# - Accept "Allow USB debugging" prompt
# - Use data cable (not charge-only)
```

### Web Interface Not Updating

1. **Hard refresh**: Press `Cmd+Shift+R` (Mac) or `Ctrl+Shift+R` (Windows)
2. **Check console**: Press `F12` → Console tab for errors
3. **Verify server**: Ensure `api_server.py` is running
4. **Check monitoring**: Verify `cb_monitor.py monitor` is active

### No GPS Data

- Enable Location Services on phone
- Wait 30-60 seconds for GPS lock
- Move to outdoor location for better signal
- Check `adb shell dumpsys location`

### No Signal Data

- Verify mobile network connection
- Test manually: `adb shell dumpsys telephony.registry`
- Some phones require root for full access
- Try different USB port/cable

### Browser Caching Issues

```bash
# Clear cache with hard refresh
Cmd+Shift+R (Mac) or Ctrl+Shift+R (Windows)

# Or disable cache in DevTools
F12 → Network tab → Disable cache checkbox
```

## 📱 Compatible Devices

**Tested:**
- ✅ Motorola Edge 50 Fusion
- ✅ Samsung Galaxy series
- ✅ Google Pixel phones
- ✅ OnePlus devices

**Requirements:**
- Android 8.0+
- ADB support
- Location services
- 5G Broadcast capability (for broadcast testing)

## 🔬 Technical Details

### Signal Metrics

| Metric | Description | Range | Unit |
|--------|-------------|-------|------|
| RSSI | Received Signal Strength Indicator | -120 to -40 | dBm |
| RSRP | Reference Signal Received Power | -140 to -80 | dBm |
| RSRQ | Reference Signal Received Quality | -20 to -3 | dB |
| SNR | Signal-to-Noise Ratio | -10 to 30 | dB |

### Modulation Thresholds (3GPP Standards)

- **16-QAM**: Higher data rates, requires RSRP ≥ -95 dBm OR RSRQ ≥ -10 dB
- **QPSK**: Lower data rates, more robust, requires RSRP ≥ -115 dBm OR RSRQ ≥ -17 dB

### Data Collection

- **Sampling Rate**: Every 30 seconds (configurable)
- **Data Source**: Android telephony API via ADB
- **GPS Source**: Android location services
- **Storage**: JSONL (one JSON object per line)
- **Export**: CSV with all parameters

## 🔐 Privacy & Security

- ✅ All data stays on local machine
- ✅ No internet required (except map tiles)
- ✅ No external servers
- ✅ No data collection or telemetry
- ✅ ADB connection only to your device

## 📄 API Endpoints

The API server (`api_server.py`) provides:

```
GET  /api/monitor/status        - Get monitoring and device status
POST /api/monitor/start         - Start monitoring
POST /api/monitor/stop          - Stop monitoring
GET  /api/export/{session_id}   - Export session to CSV
```

## 🎉 Features Summary

- ✅ Real-time signal monitoring (RSRP, RSRQ, RSSI, SNR)
- ✅ GPS location tracking with route visualization
- ✅ Interactive coverage heatmaps
- ✅ 16-QAM/QPSK modulation threshold analysis
- ✅ Session persistence across page refreshes
- ✅ Web-based start/stop control
- ✅ Direct session linking from browser
- ✅ Date/time range filtering
- ✅ CSV export with full network parameters
- ✅ Cell tower tracking (PCI, Cell ID, TAC)
- ✅ Multiple session management
- ✅ Zero external Python dependencies
- ✅ Works offline (except OpenStreetMap tiles)

## 🚧 Known Limitations

- SNR data not always available on all devices
- GPS lock may take 30-60 seconds initially
- Map tiles require internet connection
- Some devices require root for full telephony access

## 📈 Roadmap

Future enhancements:
- [ ] Multi-device monitoring support
- [ ] Advanced filtering (by PCI, Cell ID, signal threshold)
- [ ] Session comparison view
- [ ] KML/KMZ export for Google Earth
- [ ] Customizable capture intervals via web UI
- [ ] Signal quality alerts/notifications

## 🤝 Contributing

Contributions welcome! Areas for improvement:
- Additional Android device compatibility testing
- UI/UX enhancements
- Additional export formats
- Performance optimizations

## 📜 License

MIT License - Use freely for testing and analysis purposes.

## 🆘 Support

**Issues:**
- Check troubleshooting section above
- Review browser console for errors (F12)
- Verify ADB connection: `adb devices -l`
- Check log files in `logs/` directory

**For questions:**
- Open an issue on GitHub
- Check existing issues for solutions

---

**Version**: 1.0
**Created**: December 2025
**Purpose**: Professional 5G Broadcast signal monitoring and coverage analysis
**Tech Stack**: Python 3, Leaflet.js, Android ADB, JSONL storage

🤖 *Built with [Claude Code](https://claude.com/claude-code)*
