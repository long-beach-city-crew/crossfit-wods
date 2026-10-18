# CrossFit WOD Tracker

A personal tracker for the 2017 CompTrain Open Athletes workouts. The app uses FastAPI, server-rendered Jinja2 templates, and SQLite.

## Requirements

- Python 3.14 or newer (see `requires-python` in `pyproject.toml`)
- Windows or Linux for local development, Linux for the server

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

On Linux, the same steps are:

```sh
python3.14 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m uvicorn app.main:app --reload
```

## Run on a Linux server

These instructions run Uvicorn as a `systemd` service bound to `127.0.0.1:8000`, behind a reverse proxy (Caddy, nginx, …) that serves HTTPS to the Internet. Never expose Uvicorn's port directly.

### Install the app

Install Python 3.14 and its `venv` support using your Linux distribution's package manager or another trusted Python installation method. The exact package names vary by distribution. Place the project files on the server in `/opt/crossfit-wods`; create a fresh Linux virtual environment rather than copying the Windows `.venv`.

Create a service account and prepare the app directory. Run these commands as an administrator, adjusting the project path if needed:

```sh
sudo useradd --system -m --shell /usr/sbin/nologin crossfit
mkdir -p /app
cd /app
git clone https://github.com/long-beach-city-crew/crossfit-wods/.git
sudo python3.14 -m venv .venv
sudo .venv/bin/python -m pip install -r requirements.txt
```

The service account needs read and execute access to the app files and virtual environment. The `instance` directory must be writable by the service account because the app stores its SQLite database there.

### Create the session key

Keep the session-signing key outside the project, in a file only root can read:

```sh
python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(32))" | sudo tee /etc/crossfit-wods.env >/dev/null
sudo chmod 600 /etc/crossfit-wods.env
```

The same file holds the other settings (see [Configuration](#configuration)). Add `SESSION_HTTPS_ONLY=1` to it:

```sh
echo 'SESSION_HTTPS_ONLY=1' | sudo tee -a /etc/crossfit-wods.env >/dev/null
```

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
EnvironmentFile=/etc/crossfit-wods.env
ExecStart=/opt/crossfit-wods/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips=127.0.0.1
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

`--proxy-headers` lets the app see that visitors arrive over HTTPS through the proxy. Set `--forwarded-allow-ips` to the proxy's IP address; `127.0.0.1` fits a proxy on the same machine.

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

The home page redirects unauthenticated visitors to `/login`. Create your own account at `/register` before the site is reachable from the Internet: while there are no accounts, anyone can create the first one.

Point the reverse proxy at `http://127.0.0.1:8000`.

### Deploy

Pushing to `main` runs the GitHub Actions workflow (`.github/workflows/main.yml`): tests first, then the deploy step. Pull requests run the tests only.

Useful service commands:

```sh
sudo systemctl restart crossfit-wods
sudo systemctl stop crossfit-wods
sudo journalctl -u crossfit-wods -f
```

## Configuration

Settings are environment variables. On the server they live in `/etc/crossfit-wods.env`; restart the service after changing them.

| Variable | Default | Meaning |
| --- | --- | --- |
| `SECRET_KEY` | generated into `instance/secret_key` | Signs session cookies. Keep it private and stable: changing it logs everyone out. |
| `SESSION_HTTPS_ONLY` | off | `1` sends the session cookie over HTTPS only. Set it in production. |
| `ALLOW_REGISTRATION` | off | `1` lets new accounts register (the first account can always register). |
| `MAX_USERS` | `10` | Registration closes once this many accounts exist, even with `ALLOW_REGISTRATION=1`. |

### Adding a user

1. Add `ALLOW_REGISTRATION=1` to `/etc/crossfit-wods.env` and restart the service.
2. The new user registers at `/register`.
3. Remove the line and restart again.

While registration is closed, `/register` asks visitors to email aiden.takeda@proton.me for an account (`app/templates/register.html`).

## Data

- User accounts and workout progress are stored in `instance/app.db`. Back this file up regularly.
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

## Security

- Registration is closed except for the first account, or while `ALLOW_REGISTRATION=1` is set, and never beyond `MAX_USERS` accounts.
- Cross-site form posts are refused (CSRF), and every response carries a strict Content-Security-Policy and anti-framing headers. All scripts, including htmx, are served by the app itself.
- Five failed logins for one email within 15 minutes lock that email out until the window passes or the app restarts.
- After a form post the app redirects only to fixed pages (`/` or `/history`), never to a URL taken from the request.
- Keep `SECRET_KEY` private. Anyone holding it can forge a login for any user. Never commit `instance/`.
- Known limits: logging out does not revoke a stolen session cookie before it expires (14 days), and there is no password reset or two-factor login.
