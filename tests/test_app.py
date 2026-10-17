import pytest
from fastapi.testclient import TestClient

from app import db, main
from app.content import WODS
from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(main, "login_failures", {})
    with TestClient(app) as c:
        yield c


def register(client, email="me@example.com", password="secret123"):
    return client.post(
        "/register",
        data={"email": email, "password": password, "password_confirm": password},
    )


def test_content_loaded():
    assert len(WODS) == 371
    assert WODS[0].id == "W01/1-monday"
    assert all(w.desc_html for w in WODS)


def test_pages_require_login(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"


def test_register_login_logout(client):
    assert register(client).url.path == "/"
    assert register(client).status_code == 403  # registration closes after the first account
    client.post("/logout")
    assert client.post("/login", data={"email": "me@example.com", "password": "wrong-pass"}).status_code == 400
    r = client.post("/login", data={"email": "ME@example.com ", "password": "secret123"})
    assert r.url.path == "/" and "W01 – Monday" in r.text


def card(html, kind):
    """Title of the home card with the given kind, or None."""
    marker = f'wod-card {kind}"'
    if marker not in html:
        return None
    return html.split(marker, 1)[1].split("<h2>", 1)[1].split("</h2>", 1)[0]


def test_home_shows_previous_current_next(client):
    register(client)
    r = client.get("/")
    assert card(r.text, "previous") is None
    assert card(r.text, "current") == "W01 – Monday"
    assert card(r.text, "next") == "W01 – Tuesday"

    client.post("/wod/W01/1-monday", data={"done": "true"})
    r = client.get("/")
    assert card(r.text, "previous") == "W01 – Monday"
    assert card(r.text, "current") == "W01 – Tuesday"
    assert card(r.text, "next") == "W01 – Wednesday"


def test_mark_done_advances_and_unmark_from_history(client):
    register(client)
    page = client.get("/wod/W01/1-monday").text
    assert 'id="desc"' in page and ">Done</button>" in page

    r = client.post("/wod/W01/1-monday", data={"done": "true"})
    assert r.url.path == "/" and card(r.text, "current") == "W01 – Tuesday" and "1 of 371" in r.text
    assert "Mark not done" in client.get("/wod/W01/1-monday").text

    assert "W01 – Monday" in client.get("/history").text

    r = client.post("/wod/W01/1-monday", data={"next": "/history"})
    assert r.url.path == "/history" and "Nothing marked as done yet." in r.text
    assert "W01 – Monday" in client.get("/").text


def test_registration_closed_after_first_user(client, monkeypatch):
    register(client)
    client.post("/logout")
    assert "Registration is closed." in client.get("/register").text
    assert register(client, "b@example.com").status_code == 403
    monkeypatch.setenv("ALLOW_REGISTRATION", "1")
    assert register(client, "me@example.com").status_code == 400  # duplicate email
    assert register(client, "b@example.com").url.path == "/"


def test_registration_capped_at_max_users(client, monkeypatch):
    monkeypatch.setenv("ALLOW_REGISTRATION", "1")
    monkeypatch.setattr(main, "MAX_USERS", 2)
    assert register(client, "a@example.com").url.path == "/"
    assert register(client, "b@example.com").url.path == "/"
    assert register(client, "c@example.com").status_code == 403


def test_login_throttled_after_repeated_failures(client):
    register(client)
    client.post("/logout")
    for _ in range(main.MAX_LOGIN_FAILURES):
        assert client.post("/login", data={"email": "me@example.com", "password": "wrong-pass"}).status_code == 400
    r = client.post("/login", data={"email": "me@example.com", "password": "secret123"})
    assert r.status_code == 429


def test_cross_site_post_refused(client):
    register(client)
    form = {"done": "true"}
    assert client.post("/wod/W01/1-monday", data=form, headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert client.post("/wod/W01/1-monday", data=form, headers={"Origin": "https://evil.example"}).status_code == 403
    assert "0 of 371" in client.get("/").text
    r = client.post("/wod/W01/1-monday", data=form, headers={"Sec-Fetch-Site": "same-origin"})
    assert "1 of 371" in r.text


def test_security_headers(client):
    r = client.get("/login")
    assert r.headers["x-frame-options"] == "DENY"
    assert "default-src 'self'" in r.headers["content-security-policy"]


def test_progress_is_per_user(client, monkeypatch):
    monkeypatch.setenv("ALLOW_REGISTRATION", "1")
    register(client, "a@example.com")
    client.post("/wod/W01/1-monday", data={"done": "true"})
    client.post("/logout")
    register(client, "b@example.com")
    assert "0 of 371" in client.get("/").text


def test_unknown_wod_and_offsite_redirect(client):
    register(client)
    assert client.get("/wod/W99/1-monday").status_code == 404
    r = client.post("/wod/W01/1-monday", data={"done": "true", "next": "//evil.example"}, follow_redirects=False)
    assert r.headers["location"] == "/"
