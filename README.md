# Owlet Dream Logger

Real-time monitoring dashboard for the **Owlet Smart Sock 3**. Displays live baby vitals (heart rate, oxygen saturation, movement), logs all data to CSV, and provides detailed device diagnostics.

Available as both a **web dashboard** (FastAPI) and a **standalone desktop app** (CustomTkinter).

![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

## Features

- **Live Vitals** — Heart rate, SpO2, skin temperature, and movement streamed every 2 seconds
- **Device Alerts** — Real-time Owlet alerts: low oxygen, high/low HR, critical battery, sock off, sock disconnected
- **Color-Coded Ranges** — HR and oxygen values change color based on clinical ranges
- **Quality Badges** — LIVE, WEAK, DOCKED, FROZEN, MOVING, NOISE status indicators
- **Stale Data Detection** — Warnings when the base station loses connection
- **Technical Diagnostics** — Battery, WiFi signal, sock placement, skin temp, charging status
- **CSV Logging** — Every reading automatically saved to `owlet_data_log.csv`
- **Token Auto-Refresh** — Long-running sessions stay connected without re-authentication
- **Device Insights** — Firmware versions, MAC addresses, monitoring settings, and decoded alert history (desktop: Device Insights tab)
- **Alert History Summary** — Decoded RED_ALERT_SUMMARY showing HR, SpO2, duration, and type for every alert event
- **Two Interfaces** — Web dashboard for multi-device access, desktop app for simplicity

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Run

**Web dashboard** (accessible from any device on your network):

```bash
python main.py
# Open http://localhost:8000
```

**Desktop app** (standalone window, no browser needed):

```bash
python desktop_app.py
```

## Project Structure

```
owlet/
├── main.py                 # FastAPI web server entry point
├── desktop_app.py          # Standalone desktop GUI (CustomTkinter)
├── launcher.py             # Launcher for .exe builds (PyInstaller)
├── config.py               # Application settings
├── worker.py               # Background Owlet API polling loop
├── owlet_service.py        # Device discovery
├── data_processing.py      # Raw data → structured vitals
├── csv_logger.py           # CSV file logging
├── session.py              # In-memory session store (web mode)
├── dashboard.py            # Web dashboard HTML/CSS/JS
├── login_page.py           # Web login page HTML/CSS/JS
├── debug_api.py            # API debug tool (downloads logs, decodes alerts)
├── Start_Owlet_Logger.bat  # Windows batch launcher
├── requirements.txt        # Python dependencies
└── BUILDING.md             # Instructions for creating .exe
```

## Configuration

Edit `config.py`:

| Setting | Default | Description |
|---------|---------|-------------|
| `UPDATE_INTERVAL` | `2` | Seconds between data fetches |
| `LOG_FILE` | `owlet_data_log.csv` | CSV output path |
| `HOST` | `0.0.0.0` | Server bind address (web mode) |
| `PORT` | `8000` | Server port (web mode) |

## Vitals Color Ranges

**Heart Rate (BPM):**
| Range | Color | Meaning |
|-------|-------|---------|
| 100–160 | Green | Normal |
| 90–99 / 161–180 | Yellow | Alert |
| <90 / >180 | Red | Critical |

**Oxygen Saturation (SpO2):**
| Range | Color | Meaning |
|-------|-------|---------|
| ≥95% | Blue | Normal |
| 90–94% | Yellow | Low |
| <90% | Red | Very Low |

## CSV Data Columns

Each row in `owlet_data_log.csv` contains:

`timestamp_log`, `lag_seconds`, `hr`, `ox`, `oxta`, `mv`, `mvb`, `rsi`, `ss`, `sc`, `bat`, `btt`, `chg`, `onm`, `bso`, `bp`, `mrs`, `hw`, `st`, `srf`

## Building a Standalone .exe

See [BUILDING.md](BUILDING.md) for instructions on creating a portable Windows executable using PyInstaller.

## Dependencies

- [pyowletapi](https://github.com/ryanbdclark/pyowletapi) — Owlet cloud API client
- [FastAPI](https://fastapi.tiangolo.com/) + [Uvicorn](https://www.uvicorn.org/) — Web server (web mode)
- [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) — Modern desktop GUI (desktop mode)

## License

MIT — see [LICENSE](LICENSE) for details.
