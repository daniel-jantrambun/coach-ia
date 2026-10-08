import dataclasses
import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from coach import auth
from coach.api import create_app
from coach.config import load_settings
from coach.db import connect
from coach.ingest import garmin
from coach.ingest.fit_files import iter_fit_payloads

PASSWORD = "correct horse battery"
GOAL = {"distance_km": 10, "target_time_s": 2700, "race_date": "2027-03-07", "runs_per_week": 3}


@pytest.fixture
def settings(tmp_path):
    return dataclasses.replace(load_settings(), data_dir=tmp_path, db_path=tmp_path / "coach.sqlite",
                               fit_dir=tmp_path / "fit", secret_key="phrase secrète de test")


@pytest.fixture
def conn(settings):
    c = connect(settings.db_path)
    auth.create_user(c, "alice", PASSWORD)
    auth.create_user(c, "bob", PASSWORD)
    auth._failures.clear()
    yield c
    c.close()


def client_for(settings, username):
    client = TestClient(create_app(settings))
    assert client.post("/api/login", json={"username": username, "password": PASSWORD}).status_code == 200
    return client


def test_routes_require_login(settings, conn):
    client = TestClient(create_app(settings))
    for path in ("/api/me", "/api/activities", "/api/plans", "/api/load", "/api/me/garmin"):
        assert client.get(path).status_code == 401


def test_plans_are_isolated_between_users(settings, conn):
    alice, bob = client_for(settings, "alice"), client_for(settings, "bob")
    plan_id = alice.post("/api/plans", json=GOAL).json()["id"]
    assert alice.get(f"/api/plans/{plan_id}").status_code == 200
    assert bob.get(f"/api/plans/{plan_id}").status_code == 404
    assert bob.post(f"/api/plans/{plan_id}/narrate").status_code == 404
    assert bob.get("/api/plans").json() == []


def test_wrong_password_then_lockout(settings, conn):
    client = TestClient(create_app(settings))
    for _ in range(auth.MAX_FAILURES):
        assert client.post("/api/login", json={"username": "alice", "password": "nope"}).status_code == 401
    # Même le bon mot de passe est refusé pendant le blocage.
    assert client.post("/api/login", json={"username": "alice", "password": PASSWORD}).status_code == 401


def test_logout_and_password_change_end_sessions(settings, conn):
    client = client_for(settings, "alice")
    assert client.post("/api/me/password", json={"current_password": PASSWORD, "new_password": "un autre secret"}
                       ).status_code == 204
    assert client.get("/api/me").status_code == 401
    client = TestClient(create_app(settings))
    client.post("/api/login", json={"username": "alice", "password": "un autre secret"})
    client.post("/api/logout")
    assert client.get("/api/me").status_code == 401


def test_profile_update(settings, conn):
    client = client_for(settings, "alice")
    assert client.patch("/api/me", json={"hr_rest": 48, "hr_max": 190}).json()["hr_max"] == 190
    assert client.patch("/api/me", json={"hr_max": 400}).status_code == 422


def test_garmin_tokens_are_encrypted_and_never_the_password(settings, conn):
    class FakeClient:
        class client:
            @staticmethod
            def dumps():
                return '{"di_token": "abc", "di_refresh_token": "def"}'

    user_id = auth.authenticate(conn, "alice", PASSWORD)["id"]
    garmin._save_tokens(conn, user_id, FakeClient, settings.secret_key)
    stored = conn.execute("SELECT tokens_encrypted FROM garmin_accounts WHERE user_id = ?", (user_id,)).fetchone()[0]
    assert b"di_token" not in stored
    assert garmin._fernet(settings.secret_key).decrypt(stored).decode().startswith('{"di_token"')
    assert garmin.status(conn, user_id)["connected"]


def test_garmin_requires_secret_key(settings, conn):
    client = client_for(dataclasses.replace(settings, secret_key=None), "alice")
    response = client.post("/api/me/garmin", json={"email": "a@b.c", "password": "x"})
    assert response.status_code == 400 and "COACH_SECRET_KEY" in response.json()["detail"]


def test_nested_zip_from_garmin_export(tmp_path):
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as z:
        z.writestr("123_ACTIVITY.fit", b"fit-data")
    with zipfile.ZipFile(tmp_path / "export.zip", "w") as z:
        z.writestr("DI_CONNECT/DI-Connect-Uploaded-Files/UploadedFiles_0-_Part1.zip", inner.getvalue())
        z.writestr("DI_CONNECT/other.json", b"{}")
    assert [payload for _, payload in iter_fit_payloads(tmp_path)] == [b"fit-data"]


def test_serves_web_app_with_spa_fallback(settings, conn, tmp_path):
    web = tmp_path / "web"
    (web / "assets").mkdir(parents=True)
    (web / "index.html").write_text("<div id=root></div>")
    (web / "assets" / "app.js").write_text("console.log(1)")
    (tmp_path / "secret.txt").write_text("nope")
    client = TestClient(create_app(dataclasses.replace(settings, web_dir=web)))
    assert client.get("/assets/app.js").text == "console.log(1)"
    assert client.get("/plans/3").text == "<div id=root></div>"  # route du front
    assert client.get("/api/inconnu").status_code == 404
    assert "nope" not in client.get("/../secret.txt").text
