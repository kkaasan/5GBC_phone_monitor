# Repository Guidelines

## Project Structure & Modules
- Python back end lives in `cb_monitor.py` (data capture via ADB) and `api_server.py` (HTTP API + static file server).
- Web UI lives in `index.html`, `dashboard.html`, `heatmap.html`, `sessions.html`, plus assets in `static/` and `favicon.svg`.
- Generated artifacts: `data/status.json` and `data/data_index.json` for live status and session index; session logs in `logs/*.jsonl`.
- Utility scripts: `start.sh` for one-shot server startup, `test_phone.py` for device capability checks.

## Build, Test & Run
- Start everything locally: `./start.sh` (runs API server on port 8888 and serves UI).
- Run API server only: `python3 api_server.py 8888`.
- Collect data manually: `python3 cb_monitor.py monitor` (captures every 30s; writes to `data/` and `logs/`).
- Export a session: `python3 cb_monitor.py export --session <id> [--output my.csv]`.
- Device probe: `python3 test_phone.py` (verifies ADB connectivity and available metrics).

## Coding Style & Conventions
- Language: Python 3.7+ and plain HTML/JS/CSS; avoid adding external Python deps.
- Follow PEP 8 with 4-space indents; keep functions small and log messages explicit (`[MONITOR]`, `[SERVER]` tags).
- Prefer clear naming tied to domain terms (rsrp, rsrq, session_id, earfcn); keep filenames lowercase with underscores.
- Keep UI assets self-contained (no build step); favor vanilla JS and Leaflet-friendly patterns already used.

## Testing Guidelines
- There is no formal test suite; rely on `test_phone.py` for device/ADB checks and manual browser verification.
- When changing data capture, validate by running `cb_monitor.py monitor` against a device and watching `data/status.json` update cadence.
- For UI changes, exercise live pages via `http://localhost:8888/dashboard.html` and `heatmap.html` with existing session files in `data/` and `logs/`.

## Commit & PR Expectations
- Commit messages: short, imperative summaries mirroring existing history (e.g., “Add data staleness detection”).
- Include what changed and why in PR descriptions; link related issues and note device/OS tested.
- Attach screenshots/GIFs for UI updates and mention any required ADB/port changes.
- Keep generated data/logs out of commits; only commit sample fixtures if intentionally added.

## Security & Configuration
- ADB access is required; verify `ADB_PATH` in `cb_monitor.py` or set `PATH` accordingly.
- Data stays local; avoid introducing network calls beyond map tiles. Handle session IDs and file writes atomically to prevent partial logs.
- If adjusting capture intervals or ports, document defaults in `README.md` and echo them in log banners for operators.
