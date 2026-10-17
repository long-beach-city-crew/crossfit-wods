"""FastAPI app: email/password login, next workout, workout page, history."""

import os
import sqlite3
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.datastructures import URL
from starlette.middleware.sessions import SessionMiddleware

from app import db
from app.content import WODS, WODS_BY_ID, Wod
from app.security import DUMMY_HASH, hash_password, secret_key, verify_password

APP_DIR = Path(__file__).resolve().parent
MIN_PASSWORD_LENGTH = 8
MAX_USERS = int(os.environ.get("MAX_USERS", 10))
# Failed logins per email allowed within LOGIN_WINDOW seconds before that email is locked out.
MAX_LOGIN_FAILURES = 5
LOGIN_WINDOW = 15 * 60
SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'none'",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
}


def env_flag(name: str) -> bool:
    return os.environ.get(name, "").lower() in {"1", "true", "yes"}


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init()
    yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=secret_key(),
    same_site="lax",
    # Set SESSION_HTTPS_ONLY=1 when served over HTTPS so the cookie never travels in clear.
    https_only=env_flag("SESSION_HTTPS_ONLY"),
)
app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")
templates = Jinja2Templates(directory=APP_DIR / "templates")

Db = Annotated[sqlite3.Connection, Depends(db.get_db)]


@app.middleware("http")
async def protect(request: Request, call_next):
    # CSRF: browsers tag every request with Sec-Fetch-Site (older ones with Origin); refuse
    # state-changing requests that come from another site. Non-browser clients send neither.
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        site = request.headers.get("sec-fetch-site")
        origin = request.headers.get("origin")
        if site is not None:
            allowed = site in {"same-origin", "none"}
        elif origin is not None:
            allowed = origin == f"{request.url.scheme}://{request.url.netloc}"
        else:
            allowed = True
        if not allowed:
            return PlainTextResponse("Cross-site request refused", status_code=403)
    response = await call_next(request)
    for name, value in SECURITY_HEADERS.items():
        response.headers.setdefault(name, value)
    return response


def current_user(request: Request, conn: Db) -> sqlite3.Row:
    user_id = request.session.get("user_id")
    user = db.user_by_id(conn, user_id) if user_id else None
    if user is None:
        request.session.clear()
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return user


User = Annotated[sqlite3.Row, Depends(current_user)]


def get_wod(week: str, day: str) -> Wod:
    wod = WODS_BY_ID.get(f"{week}/{day}")
    if wod is None:
        raise HTTPException(status_code=404, detail="Workout not found")
    return wod


def redirect(url: str) -> RedirectResponse:
    normalized = url.replace("\\", "/")
    safe_url = normalized if normalized.startswith("/") and URL(normalized).is_relative_url else "/"
    return RedirectResponse(safe_url, status_code=303)


def registration_open(conn: sqlite3.Connection) -> bool:
    """The first account can always be created; more only with ALLOW_REGISTRATION=1, up to MAX_USERS."""
    count = db.user_count(conn)
    return count < MAX_USERS and (count == 0 or env_flag("ALLOW_REGISTRATION"))


# email -> monotonic times of recent failed logins (in memory: resets on restart).
login_failures: dict[str, list[float]] = {}


def recent_failures(email: str) -> int:
    cutoff = time.monotonic() - LOGIN_WINDOW
    failures = [t for t in login_failures.pop(email, []) if t > cutoff]
    if failures:
        login_failures[email] = failures
    return len(failures)


def log_in(request: Request, user_id: int) -> None:
    request.session.clear()
    request.session["user_id"] = user_id


# --- auth -----------------------------------------------------------------


@app.get("/register")
def register_form(request: Request, conn: Db):
    return templates.TemplateResponse(
        request, "register.html", {"closed": not registration_open(conn)}
    )


@app.post("/register")
def register(
    request: Request,
    conn: Db,
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
    password_confirm: Annotated[str, Form()],
):
    if not registration_open(conn):
        return templates.TemplateResponse(
            request, "register.html", {"closed": True}, status_code=403
        )
    email = email.strip().lower()
    error = None
    if "@" not in email:
        error = "Enter a valid email address."
    elif len(password) < MIN_PASSWORD_LENGTH:
        error = f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
    elif password != password_confirm:
        error = "Passwords do not match."
    else:
        user_id = db.create_user(conn, email, hash_password(password))
        if user_id is None:
            error = "An account with this email already exists."
    if error:
        return templates.TemplateResponse(
            request, "register.html", {"error": error, "email": email}, status_code=400
        )
    log_in(request, user_id)
    return redirect("/")


@app.get("/login")
def login_form(request: Request):
    return templates.TemplateResponse(request, "login.html")


@app.post("/login")
def login(
    request: Request,
    conn: Db,
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
):
    email = email.strip().lower()
    if recent_failures(email) >= MAX_LOGIN_FAILURES:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Too many failed attempts. Try again later.", "email": email},
            status_code=429,
        )
    user = db.user_by_email(conn, email)
    password_ok = verify_password(password, user["password_hash"] if user else DUMMY_HASH)
    if user is None or not password_ok:
        login_failures.setdefault(email, []).append(time.monotonic())
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Wrong email or password.", "email": email},
            status_code=400,
        )
    login_failures.pop(email, None)
    log_in(request, user["id"])
    return redirect("/")


@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return redirect("/login")


# --- workouts -------------------------------------------------------------


@app.get("/")
def home(request: Request, conn: Db, user: User):
    done = db.done_wods(conn, user["id"])
    # Current is the first workout not done; previous/next are its neighbours in program order.
    i = next((i for i, w in enumerate(WODS) if w.id not in done), len(WODS))
    return templates.TemplateResponse(
        request,
        "home.html",
        {
            "user": user,
            "previous": WODS[i - 1] if i > 0 else None,
            "current": WODS[i] if i < len(WODS) else None,
            "next": WODS[i + 1] if i + 1 < len(WODS) else None,
            "done_count": len(done),
            "total": len(WODS),
        },
    )


@app.get("/wod/{week}/{day}")
def wod_page(request: Request, conn: Db, user: User, wod: Annotated[Wod, Depends(get_wod)]):
    done = db.done_wods(conn, user["id"])
    return templates.TemplateResponse(
        request, "wod.html", {"user": user, "wod": wod, "done_at": done.get(wod.id)}
    )


@app.post("/wod/{week}/{day}")
def save_wod(
    conn: Db,
    user: User,
    wod: Annotated[Wod, Depends(get_wod)],
    done: Annotated[bool, Form()] = False,
    next: Annotated[str, Form()] = "/",
):
    db.set_done(conn, user["id"], wod.id, done)
    # Only local paths are allowed by redirect(), so the form field cannot redirect off-site.
    return redirect(next)


@app.get("/history")
def history(request: Request, conn: Db, user: User):
    done = db.done_wods(conn, user["id"])
    past = [(w, done[w.id]) for w in reversed(WODS) if w.id in done]
    return templates.TemplateResponse(request, "history.html", {"user": user, "past": past})
