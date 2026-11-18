# Lab Equipment Tracker
Run: `run.bat` (Windows) or `./run.sh` (Mac/Linux). Opens at http://127.0.0.1:8765
Share with the lab: `run.bat --lan`, then others open `http://<this-laptop-IP>:8765` (all views auto-sync via one database).
First login: admin / admin123 (forced change). Data lives in lab.db (back it up). Delete lab.db to re-import from data/equipment.xlsx.
Optional native window: `pip install pywebview`. Standalone exe: `pip install pyinstaller && pyinstaller --onefile --add-data "index.html;." --add-data "data;data" app.py`

## Desktop app
Run `install_windows.ps1` once (right-click > Run with PowerShell). Double-click **Lab Tracker** on the Desktop: starts the server silently and opens an app-style window. The server also auto-starts at Windows login. Stop it with `stop_server.bat`.

## Free remote access (Tailscale)
Private (recommended): install Tailscale on host + users' PCs (same tailnet), then on host: `tailscale serve --bg 8765` -> https://<host>.<tailnet>.ts.net
Public: `tailscale funnel --bg 8765` (needs Funnel + HTTPS enabled in the Tailscale admin console). Check `tailscale funnel status`; stop with `tailscale funnel reset`.

## Deploy on Railway (HTTPS, free)
1. Push this folder to a private GitHub repo.
2. railway.com > New Project > Deploy from GitHub repo (start command comes from `Procfile`).
3. Variables: `SECRET_KEY` (long random string), `ADMIN_PASSWORD` (initial admin password), `DATA_DIR=/data`.
4. Add a Volume to the service, mount path `/data` (without it, data resets on every deploy).
5. Settings > Networking > Generate Domain. Open the https URL, sign in as `admin`.

## Deploy on Railway (HTTPS)
1. Push this folder to a private GitHub repo.
2. railway.com > New Project > Deploy from GitHub repo (start command comes from `Procfile`).
3. Variables: `SECRET_KEY` (long random string), `ADMIN_PASSWORD` (initial admin password), `DATA_DIR=/data`.
4. Add a Volume to the service, mount path `/data` (without it, data resets on every deploy).
5. Settings > Networking > Generate Domain. Open the https URL, sign in as `admin`.
