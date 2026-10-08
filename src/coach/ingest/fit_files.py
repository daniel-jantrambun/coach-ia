"""Import de fichiers FIT : export complet Garmin ("Exporter vos données"), garminexport ou sync Garmin.

On ne garde que le résumé de chaque activité (message `session`) ; les streams seconde par seconde
restent dans les fichiers bruts et seront exploités plus tard (dérive FC/allure, détection de fatigue).
"""

import hashlib
import io
import zipfile
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import fitdecode


def parse_fit(data: bytes) -> dict | None:
    """Résumé de la première session d'un fichier FIT, ou None si le fichier n'en contient pas."""
    with fitdecode.FitReader(io.BytesIO(data), check_crc=fitdecode.CrcCheck.DISABLED) as fit:
        for frame in fit:
            if frame.frame_type == fitdecode.FIT_FRAME_DATA and frame.name == "session":
                return _session_to_activity(frame)
    return None


def _field(frame, name):
    return frame.get_value(name, fallback=None) if frame.has_field(name) else None


def _session_to_activity(frame) -> dict | None:
    start = _field(frame, "start_time")
    duration = _field(frame, "total_timer_time") or _field(frame, "total_elapsed_time")
    if not isinstance(start, datetime) or not duration:
        return None
    if start.tzinfo is None:
        start = start.replace(tzinfo=UTC)
    sport = _field(frame, "sport")
    return {
        "sport": str(sport).lower() if sport is not None else "generic",
        "start_time": start.astimezone(UTC).isoformat(),
        "duration_s": float(duration),
        "distance_m": _field(frame, "total_distance"),
        "elevation_gain_m": _field(frame, "total_ascent"),
        "avg_hr": _field(frame, "avg_heart_rate"),
        "max_hr": _field(frame, "max_heart_rate"),
        "avg_power": _field(frame, "avg_power"),
    }


def _iter_zip(archive: zipfile.ZipFile, location: str) -> Iterator[tuple[str, bytes]]:
    # L'export complet Garmin contient des zip dans le zip (DI-Connect-Uploaded-Files/UploadedFiles_*.zip).
    for name in archive.namelist():
        lower = name.lower()
        if lower.endswith(".fit"):
            yield f"{location}!{name}", archive.read(name)
        elif lower.endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(archive.read(name))) as inner:
                yield from _iter_zip(inner, f"{location}!{name}")


def iter_fit_payloads(root: Path) -> Iterator[tuple[str, bytes]]:
    """Parcourt un dossier et renvoie (chemin, contenu) pour chaque .fit, y compris dans les .zip."""
    for path in sorted(root.rglob("*")):
        suffix = path.suffix.lower()
        if suffix == ".fit":
            yield str(path), path.read_bytes()
        elif suffix == ".zip":
            with zipfile.ZipFile(path) as archive:
                yield from _iter_zip(archive, str(path))


def import_directory(conn, user_id: int, root: Path) -> tuple[int, int]:
    """Importe tous les FIT d'un dossier pour un utilisateur. Renvoie (importés, ignorés)."""
    from coach.db import upsert_activity

    imported = skipped = 0
    for location, payload in iter_fit_payloads(root):
        try:
            activity = parse_fit(payload)
        except fitdecode.FitError:
            activity = None
        if activity is None:
            skipped += 1
            continue
        # Identifiant stable basé sur le contenu : réimporter le même fichier ne crée pas de doublon.
        activity["id"] = "fit:" + hashlib.sha1(payload).hexdigest()[:16]
        activity["user_id"] = user_id
        activity["source"] = "fit"
        activity["file_path"] = location
        upsert_activity(conn, activity)
        imported += 1
    conn.commit()
    return imported, skipped
