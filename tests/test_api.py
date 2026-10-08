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


def test_first_account_becomes_admin_only_once(settings):
    client = TestClient(create_app(settings))
    assert client.get("/api/setup").json() == {"needs_setup": True}
    response = client.post("/api/setup", json={"username": "papa", "password": PASSWORD, "display_name": "Papa"})
    assert response.status_code == 201 and response.json()["is_admin"] is True
    assert client.get("/api/me").status_code == 200  # connecté directement
    assert client.get("/api/setup").json() == {"needs_setup": False}
    other = TestClient(create_app(settings))
    assert other.post("/api/setup", json={"username": "intrus", "password": PASSWORD}).status_code == 409


def test_setup_rejects_weak_password_and_bad_username(settings):
    client = TestClient(create_app(settings))
    assert client.post("/api/setup", json={"username": "papa", "password": "court"}).status_code == 422
    assert client.post("/api/setup", json={"username": "a b", "password": PASSWORD}).status_code == 422
    assert client.get("/api/setup").json() == {"needs_setup": True}


def test_admin_manages_accounts(settings, conn):
    auth.create_user(conn, "root", PASSWORD, is_admin=True)
    admin, alice = client_for(settings, "root"), client_for(settings, "alice")

    assert alice.get("/api/admin/users").status_code == 403
    assert alice.post("/api/admin/users", json={"username": "x", "password": PASSWORD}).status_code == 403

    created = admin.post("/api/admin/users", json={"username": "zoe", "password": PASSWORD, "display_name": "Zoé"})
    assert created.status_code == 201
    assert admin.post("/api/admin/users", json={"username": "ZOE", "password": PASSWORD}).status_code == 409
    assert {u["username"] for u in admin.get("/api/admin/users").json()} == {"alice", "bob", "root", "zoe"}

    # Réinitialisation : l'ancienne session d'alice est fermée, le nouveau mot de passe fonctionne.
    alice_id = auth.authenticate(conn, "alice", PASSWORD)["id"]
    assert admin.post(f"/api/admin/users/{alice_id}/password", json={"new_password": "nouveau secret"}
                      ).status_code == 204
    assert alice.get("/api/me").status_code == 401
    assert auth.authenticate(conn, "alice", "nouveau secret") is not None


def test_delete_account_removes_its_data(settings, conn):
    auth.create_user(conn, "root", PASSWORD, is_admin=True)
    admin, bob = client_for(settings, "root"), client_for(settings, "bob")
    bob.post("/api/plans", json=GOAL)
    bob_id = bob.get("/api/me").json()["id"]
    (settings.fit_dir / str(bob_id)).mkdir(parents=True)

    assert admin.delete(f"/api/admin/users/{bob_id}").status_code == 204
    assert bob.get("/api/me").status_code == 401
    assert conn.execute("SELECT COUNT(*) FROM plans WHERE user_id = ?", (bob_id,)).fetchone()[0] == 0
    assert not (settings.fit_dir / str(bob_id)).exists()
    assert admin.delete(f"/api/admin/users/{bob_id}").status_code == 404


def test_admin_cannot_delete_self_or_last_admin(settings, conn):
    root_id = auth.create_user(conn, "root", PASSWORD, is_admin=True)
    admin = client_for(settings, "root")
    assert admin.delete(f"/api/admin/users/{root_id}").status_code == 409
    other_id = admin.post("/api/admin/users", json={"username": "maman", "password": PASSWORD, "is_admin": True}
                          ).json()["id"]
    # Deux admins : l'un peut supprimer l'autre, mais le dernier restant est protégé.
    assert admin.delete(f"/api/admin/users/{other_id}").status_code == 204
    with pytest.raises(auth.AccountError):
        auth.delete_user(conn, root_id, acting_user_id=-1)


def test_migration_makes_oldest_account_admin(tmp_path):
    import sqlite3

    db_path = tmp_path / "old.sqlite"
    old = sqlite3.connect(db_path)
    old.executescript(
        "CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL UNIQUE COLLATE NOCASE,"
        " password_hash TEXT NOT NULL, display_name TEXT NOT NULL, hr_rest INTEGER NOT NULL DEFAULT 50,"
        " hr_max INTEGER NOT NULL DEFAULT 185, created_at TEXT NOT NULL DEFAULT (datetime('now')));"
        "INSERT INTO users (username, password_hash, display_name) VALUES ('premier', 'x', 'P'), ('second', 'x', 'S');"
    )
    old.commit()
    old.close()
    conn = connect(db_path)
    assert [tuple(r) for r in conn.execute("SELECT username, is_admin FROM users ORDER BY id")] == [
        ("premier", 1), ("second", 0)]


def test_garmin_errors_include_library_warnings():
    import logging

    with garmin._diagnostics() as warnings:
        logging.getLogger("garminconnect.client").warning("DI token exchange failed (%s)", "HTTP 403")
        logging.getLogger("garminconnect.client").warning("DI token exchange failed (%s)", "HTTP 403")
    error = garmin._error("Connexion Garmin refusée", Exception("JWT_WEB cookie not set"), warnings)
    assert str(error) == ("Connexion Garmin refusée : JWT_WEB cookie not set "
                          "(détails : DI token exchange failed (HTTP 403))")
