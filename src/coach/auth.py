"""Comptes et sessions. Pas d'inscription libre : les comptes sont créés par l'admin (`coach add-user`)."""

import hashlib
import hmac
import secrets
import time
from datetime import UTC, datetime, timedelta

# scrypt (stdlib) : n=2^14, r=8, p=1 → ~16 Mo de RAM et quelques dizaines de ms par vérification.
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**14, 8, 1
SESSION_DAYS = 30
MIN_PASSWORD_LENGTH = 10

# Anti force brute, en mémoire (un seul process) : 5 échecs → 15 min de blocage pour ce nom d'utilisateur.
MAX_FAILURES, LOCKOUT_S = 5, 15 * 60
_failures: dict[str, list[float]] = {}


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    _, n, r, p, salt, digest = stored.split("$")
    candidate = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p))
    return hmac.compare_digest(candidate.hex(), digest)


def validate_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Le mot de passe doit faire au moins {MIN_PASSWORD_LENGTH} caractères")


def create_user(conn, username: str, password: str, display_name: str | None = None) -> int:
    validate_password(password)
    cur = conn.execute(
        "INSERT INTO users (username, password_hash, display_name) VALUES (?, ?, ?)",
        (username, hash_password(password), display_name or username),
    )
    conn.commit()
    return cur.lastrowid


def set_password(conn, username: str, password: str) -> None:
    validate_password(password)
    cur = conn.execute("UPDATE users SET password_hash = ? WHERE username = ?", (hash_password(password), username))
    if cur.rowcount == 0:
        raise KeyError(username)
    # Changer de mot de passe déconnecte toutes les sessions existantes.
    conn.execute("DELETE FROM sessions WHERE user_id = (SELECT id FROM users WHERE username = ?)", (username,))
    conn.commit()


def _locked(username: str) -> bool:
    now = time.monotonic()
    recent = [t for t in _failures.get(username.lower(), []) if now - t < LOCKOUT_S]
    _failures[username.lower()] = recent
    return len(recent) >= MAX_FAILURES


def authenticate(conn, username: str, password: str) -> dict | None:
    if _locked(username):
        return None
    row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if row is None or not verify_password(password, row["password_hash"]):
        _failures.setdefault(username.lower(), []).append(time.monotonic())
        return None
    _failures.pop(username.lower(), None)
    return dict(row)


def user_for_id(conn, user_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(conn, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    expires = datetime.now(UTC) + timedelta(days=SESSION_DAYS)
    conn.execute("DELETE FROM sessions WHERE expires_at < ?", (datetime.now(UTC).isoformat(),))
    conn.execute(
        "INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
        (_token_hash(token), user_id, expires.isoformat()),
    )
    conn.commit()
    return token


def user_for_session(conn, token: str) -> dict | None:
    row = conn.execute(
        "SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token_hash = ? AND s.expires_at > ?",
        (_token_hash(token), datetime.now(UTC).isoformat()),
    ).fetchone()
    return dict(row) if row else None


def delete_session(conn, token: str) -> None:
    conn.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))
    conn.commit()
