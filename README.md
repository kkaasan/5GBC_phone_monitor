# 📡 5G Broadcast Monitor

Professional 5G Broadcast signal analysis and coverage mapping tool for real-time RSRP/RSRQ monitoring with GPS correlation and modulation threshold analysis.

![Version](https://img.shields.io/badge/version-1.2-blue)
![Python](https://img.shields.io/badge/python-3.7+-green)
![Android](https://img.shields.io/badge/android-8.0+-green)
![License](https://img.shields.io/badge/license-MIT-blue)

## 🌟 Features

### Desktop Monitoring (ADB-based)
- **Real-time Signal Monitoring** - RSRP, RSRQ, RSSI, SNR metrics via ADB
- **GPS-Correlated Tracking** - High-precision location data with route visualization
- **Interactive Heatmap** - Coverage analysis with 16-QAM/QPSK modulation thresholds
- **Live Dashboard** - Real-time gauges, network info, and session statistics
- **Session Management** - Automatic logging, indexing, and historical replay
- **Web Control Interface** - Start/stop monitoring, device status, and session browser
- **CSV Export** - Full parameter export for post-processing and reporting
- **Modulation Analysis** - Signal quality classification based on 3GPP standards

### 📱 Native Android App (NEW!)
- **Standalone Monitoring** - No PC or ADB required, runs independently on your phone
- **Background Logging** - Continues monitoring with screen off using foreground service
- **Robust Network Collection** - Retry mechanism with exponential backoff for reliable data
- **Battery Optimization** - Requests Doze mode exemption for uninterrupted monitoring
- **Live Cell View** - Real-time display of signal metrics and GPS status
- **Automatic File Export** - Saves logs to device storage in JSONL format
- **Session Management** - Compatible with desktop heatmap viewer

## 📁 Project Structure

```
cb_monitor/
├── cb_monitor.py          # Main monitoring backend (ADB integration)
├── api_server.py          # Web API server with control endpoints
├── start.sh               # Quick-start script (starts web API server)
├── index.html             # Main control interface
├── dashboard.html         # Live monitoring dashboard
├── heatmap.html           # Coverage heatmap viewer
├── sessions.html          # Session browser and export
├── settings.html          # Transmitter configuration (tower locations & PCI)
├── android_app/           # Native Android app (standalone monitoring)
│   ├── app/src/main/java/ee/levira/cbmonitor/
│   │   ├── MainActivity.kt          # App UI and controls
│   │   └── MonitoringService.kt     # Background monitoring service
│   └── app/build/outputs/apk/debug/
│       └── app-debug.apk            # Pre-built APK for installation
├── data/                  # Generated data files
│   ├── status.json       # Current live status (with session_id)
│   └── data_index.json   # Session index and metadata
├── logs/                  # Session log files (.jsonl)
├── static/                # Additional static assets (if any)
├── favicon.svg            # App icon
└── test_phone.py         # Device testing utilities
```

## 📲 Android App Installation

### Download Pre-built APK

**Direct Download:**
[📥 Download app-debug.apk](https://github.com/kkaasan/5GBC_phone_monitor/raw/main/android_app/app/build/outputs/apk/debug/app-debug.apk)

### Installation Steps

1. **Enable Unknown Sources** (if not already enabled)
   - Go to Settings → Security → Install unknown apps
   - Select your browser or file manager
   - Allow installation from this source

2. **Download and Install**
   - Click the download link above on your Android device
   - Or transfer the APK file to your phone via USB/cloud storage
   - Tap the APK file to install
   - Accept permissions when prompted

3. **Grant Permissions**
   - Location (Fine & Background) - Required for GPS data
   - Phone State - Required for network signal data
   - Battery Optimization Exemption - Recommended for reliable background monitoring

4. **Start Monitoring**
   - Open the app
   - Tap "Start Logging"
   - Grant battery optimization exemption when prompted
   - The app will log data every 30 seconds to device storage

### Accessing Logs

Logs are saved to: `/storage/emulated/0/Android/data/ee.levira.cbmonitor/files/cb_monitor/`

You can:
- Copy logs to PC via USB
- Import into desktop heatmap viewer
- View with any text editor (JSONL format)

### Features

- ✅ **Background Monitoring**: Continues with screen off via foreground service
- ✅ **Retry Logic**: Exponential backoff (2-12s timeouts) for reliable cell data
- ✅ **Stale Detection**: Automatically detects and refreshes stale network data
- ✅ **Battery Optimized**: Requests Doze mode exemption for uninterrupted monitoring
- ✅ **Live Display**: Real-time signal metrics and GPS status
- ✅ **Green Border**: 5dp border indicates active logging
- ✅ **Compatible Format**: JSONL logs work with desktop heatmap viewer

## 🚀 Quick Start (Desktop Monitoring)

### Prerequisites

1. **Android SDK Platform Tools** (ADB)
   ```bash
   # macOS with Homebrew
   brew install android-platform-tools

   # Or download from:
   # https://developer.android.com/studio/releases/platform-tools
   ```
   ```powershell
   # Windows (PowerShell)
   winget install --id=Google.PlatformTools
   # Or download the ZIP from the link above and add adb.exe to PATH
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

# Start the web server (macOS/Linux)
# Monitoring is controlled from the web UI (Home page)
./start.sh

# Start the web server (Windows)
python api_server.py 8888
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
-- **Transmitter Filters**: Heatmap/markers honor active transmitters (by PCI); click tower icons to toggle coverage on/off. At least one transmitter with a configured PCI must be active to render the heatmap.

### 4. Transmitter Settings (`settings.html`)

**Purpose:**
- Configure transmitter locations and PCIs to drive **transmitter-aware interpolation** in the heatmap.
- Persist configuration to `data/transmitters.json` via the API server.

**Features:**
- 📡 **Interactive map**: Click on the map to add transmitters; drag markers to refine positions.
- ✏️ **Editable list**: Rename transmitters, edit latitude/longitude, and set **PCI** (0–503).
- 💾 **Save to file**: Writes configuration through `POST /api/transmitters/save` so `heatmap.html` can use it.
- 🔗 **Integration with heatmap**:
  - Each measurement point is matched to a transmitter by PCI.
  - You can toggle transmitters on/off directly in `heatmap.html`; only active transmitters contribute to the RF interpolation.

**Signal Classification (OR Logic):**
- 🟩 **16-QAM Capable**: RSRP ≥ -95 dBm OR RSRQ ≥ -10 dB
- 🟨 **Better Signal**: RSRP ≥ -105 dBm OR RSRQ ≥ -13 dB
- 🟥 **QPSK Reception**: RSRP ≥ -115 dBm OR RSRQ ≥ -17 dB
- ⚫ **Unusable**: RSRP < -120 dBm AND RSRQ < -20 dB

### 5. Sessions & Export (`sessions.html`)

**Features:**
- Browse all captured sessions with statistics
- Session cards showing:
  - Data point count
  - Session duration
  - Start time
  - GPS availability
- **View Map**: Opens heatmap with selected session pre-loaded
- **Export CSV**: Download per-session data with all parameters
- **Bulk operations** (via the API server):
  - Multi-select sessions and export them combined via `POST /api/sessions/export`
  - Multi-select sessions and delete them via `POST /api/sessions/delete`

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
- ✅ Motorola Edge 50 Fusion (primary validated device - ADB & Native App)

**Requirements for Desktop Monitoring (ADB):**
- Android 8.0+
- ADB support
- USB debugging enabled
- Location services
- 5G Broadcast capability (for broadcast testing)

**Requirements for Native Android App:**
- Android 8.0+ (API 26+)
- Location permissions (Fine & Background)
- Phone state permission
- Battery optimization exemption (recommended)
- ~7MB storage space

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

```text
GET  /api/monitor/status          - Get monitoring and device status
POST /api/monitor/start           - Start monitoring (spawns cb_monitor.py monitor)
POST /api/monitor/stop            - Stop monitoring (SIGINT to cb_monitor.py)

GET  /api/export/{session_id}     - Export a single session to CSV

POST /api/transmitters/save       - Save transmitter configuration to data/transmitters.json

POST /api/sessions/delete         - Delete a session (log file + index entry)
POST /api/sessions/export         - Export multiple sessions as a single combined CSV
```

## 🎉 Features Summary

### Desktop Monitoring
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

### Android App
- ✅ Standalone operation (no PC required)
- ✅ Background monitoring with screen off
- ✅ Retry mechanism with exponential backoff
- ✅ Stale data detection and automatic refresh
- ✅ Battery optimization exemption support
- ✅ Foreground service for reliable operation
- ✅ Live signal and GPS display
- ✅ Compatible JSONL log format
- ✅ 30-second capture interval

## 🚧 Known Limitations

- SNR data not always available on all devices
- GPS lock may take 30-60 seconds initially
- Map tiles require internet connection
- Some devices require root for full telephony access

## 📈 Roadmap

Future enhancements:
- [x] Native Android app for standalone monitoring (✅ Completed v1.2)
- [x] Background monitoring with screen off (✅ Completed v1.2)
- [x] Retry logic for reliable cell data collection (✅ Completed v1.2)
- [ ] Multi-device monitoring support
- [ ] Advanced filtering (by PCI, Cell ID, signal threshold)
- [ ] Session comparison view
- [ ] KML/KMZ export for Google Earth
- [ ] Customizable capture intervals via web UI
- [ ] Signal quality alerts/notifications
- [ ] Android app: Auto-upload logs to server
- [ ] Android app: Real-time map view

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

**Version**: 1.2
**Created**: December 2025
**Purpose**: Professional 5G Broadcast signal monitoring and coverage analysis
**Tech Stack**: Python 3, Leaflet.js, Android ADB, Kotlin/Android, JSONL storage

**What's New in v1.2:**
- 📱 Native Android app for standalone monitoring
- 🔋 Background monitoring with battery optimization
- 🔄 Retry mechanism with exponential backoff for reliable cell data
- 📊 Stale data detection and automatic refresh
- 🟢 Visual logging indicator (5dp green border)

Developed by **Kristo Kaasan** in cooperation with **Claude Code** and **Codex**.
