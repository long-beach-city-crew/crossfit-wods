# CrossFit WOD Tracker

A personal tracker for the 2017 CompTrain Open Athletes workouts. The app uses FastAPI, server-rendered Jinja2 templates, and SQLite.

## Requirements

- Python 3.14 or newer (see `requires-python` in `pyproject.toml`)
- Windows for the local instructions below, or Linux for the server instructions

## Run locally on Windows

Open PowerShell in the project directory:

```powershell
cd C:\path\to\crossfit-wods
```

Create a virtual environment and install the dependencies:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

If `.venv` already exists but is incomplete (for example, it has no `pyvenv.cfg`), remove that environment and recreate it before installing:

```powershell
Remove-Item -Recurse -Force .venv
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Start the development server:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000/register> to create an account. The server runs in the terminal; press **Ctrl+C** to stop it.

## Run on a Linux server

These instructions run Uvicorn as a `systemd` service bound to `127.0.0.1:8000`. This keeps the app off the public network interface; use an SSH tunnel to access it remotely. Do not expose this app directly to the public Internet (see [Security note](#security-note)).

### Install the app

Install Python 3.14 and its `venv` support using your Linux distribution's package manager or another trusted Python installation method. The exact package names vary by distribution. Place the project files on the server in `/opt/crossfit-wods`; create a fresh Linux virtual environment rather than copying the Windows `.venv`.

Create a service account and prepare the app directory. Run these commands as an administrator, adjusting the project path if needed:

```sh
sudo useradd --system --home-dir /opt/crossfit-wods --shell /usr/sbin/nologin crossfit-wods
sudo chown -R root:root /opt/crossfit-wods
sudo install -d -o crossfit-wods -g crossfit-wods /opt/crossfit-wods/instance
cd /opt/crossfit-wods
sudo python3.14 -m venv .venv
sudo .venv/bin/python -m pip install -r requirements.txt
```

The service account needs read and execute access to the app files and virtual environment. The `instance` directory must be writable by the service account because the app stores its SQLite database and, unless `SECRET_KEY` is configured, its generated session-signing key there.

### Create a systemd service

Create `/etc/systemd/system/crossfit-wods.service` with the following contents:

```ini
[Unit]
Description=CrossFit WOD Tracker
After=network.target

[Service]
Type=simple
User=crossfit-wods
Group=crossfit-wods
WorkingDirectory=/opt/crossfit-wods
ExecStart=/opt/crossfit-wods/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Enable and start the service:

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now crossfit-wods
sudo systemctl status crossfit-wods
```

Check that the app responds on the server:

```sh
curl -I http://127.0.0.1:8000/
```

The home page redirects unauthenticated visitors to `/login`; create the first account at `/register`.

To access the server privately from your computer, open an SSH tunnel:

```sh
ssh -L 8000:127.0.0.1:8000 your-user@your-server
```

While that SSH connection is open, visit <http://127.0.0.1:8000/register> in your local browser.

Useful service commands:

```sh
sudo systemctl restart crossfit-wods
sudo systemctl stop crossfit-wods
sudo journalctl -u crossfit-wods -f
```

## Data and configuration

- User accounts and workout progress are stored in `instance/app.db`. Back this file up regularly.
- The session-signing key is read from the `SECRET_KEY` environment variable, or generated once and saved as `instance/secret_key`. Keep the key stable and private: changing it logs out existing sessions. Back up `instance/secret_key` if you rely on the generated key.
- The app creates the `instance` directory and database on startup. On Linux, ensure the service user can write to that directory.
- Workout content is loaded from `data/` when the app starts. Restart the service after changing workout or description files.

## Tests

Run the test suite from the project directory:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

On Linux, use:

```sh
.venv/bin/python -m pytest -q
```

## Security note

- Only the first account can register. To allow more, start the app with `ALLOW_REGISTRATION=1`, register them, then restart without it.
- The app holds at most 10 accounts (`MAX_USERS` to change it); registration closes once that many exist, even with `ALLOW_REGISTRATION=1`.
- Cross-site form posts are refused (CSRF), and every response carries a strict Content-Security-Policy and anti-framing headers.
- Five failed logins for one email within 15 minutes lock that email out until the window passes or the app restarts.
- When serving over HTTPS, set `SESSION_HTTPS_ONLY=1` so the session cookie is never sent over plain HTTP, and run Uvicorn with `--proxy-headers` behind the reverse proxy.
- Keep `SECRET_KEY` (or `instance/secret_key`) private. Anyone holding it can forge a login for any user.

## test