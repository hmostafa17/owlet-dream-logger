# Building a Standalone Executable

Create a portable `.exe` so you can run Owlet Dream Logger without a Python installation.

## Prerequisites

```bash
pip install pyinstaller
```

## Build

```bash
pyinstaller --onefile --noconsole --name "OwletDreamLogger" launcher.py
```

| Flag | Purpose |
|------|---------|
| `--onefile` | Single portable `.exe` |
| `--noconsole` | No console window (remove to see logs) |
| `--name` | Output filename |
| `--icon=path.ico` | Optional app icon |

The executable will be in `dist/OwletDreamLogger.exe`.

## Debug Build

To see console output for troubleshooting:

```bash
pyinstaller --onefile --name "OwletDreamLogger" launcher.py
```

## Notes

- The `.exe` is 50–100 MB (bundles Python + dependencies)
- First launch may be slow while Windows Defender scans it
- Rebuild after any code changes
- For day-to-day use, running `python main.py` or the batch file is simpler

## Troubleshooting

| Problem | Solution |
|---------|----------|
| App doesn't start | Run from terminal to see errors |
| Firewall warning | Allow through Windows Firewall |
| Missing modules | Reinstall deps before building: `pip install -r requirements.txt` |
