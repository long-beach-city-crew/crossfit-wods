"""FastAPI app: email/password login, next workout, workout page, history."""

import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app import db
from app.content import WODS, WODS_BY_ID, Wod
from app.security import hash_password, secret_key, verify_password

APP_DIR = Path(__file__).resolve().parent
MIN_PASSWORD_LENGTH = 8


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init()
    yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=secret_key(), same_site="lax")
app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")
templates = Jinja2Templates(directory=APP_DIR / "templates")

Db = Annotated[sqlite3.Connection, Depends(db.get_db)]


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
    safe_url = url if url.startswith("/") and not url.startswith("//") else "/"
    return RedirectResponse(safe_url, status_code=303)


def log_in(request: Request, user_id: int) -> None:
    request.session.clear()
    request.session["user_id"] = user_id


# --- auth -----------------------------------------------------------------


@app.get("/register")
def register_form(request: Request):
    return templates.TemplateResponse(request, "register.html")


@app.post("/register")
def register(
    request: Request,
    conn: Db,
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
    password_confirm: Annotated[str, Form()],
):
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
    user = db.user_by_email(conn, email)
    if user is None or not verify_password(password, user["password_hash"]):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Wrong email or password.", "email": email},
            status_code=400,
        )
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
    # Only local paths, so the form field cannot redirect off-site.
    return redirect(next if next.startswith("/") and not next.startswith("//") else "/")


@app.get("/history")
def history(request: Request, conn: Db, user: User):
    done = db.done_wods(conn, user["id"])
    past = [(w, done[w.id]) for w in reversed(WODS) if w.id in done]
    return templates.TemplateResponse(request, "history.html", {"user": user, "past": past})
