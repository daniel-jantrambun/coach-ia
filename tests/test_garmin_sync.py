import dataclasses
import io
import zipfile

import pytest
from fastapi.testclient import TestClient
from garminconnect.exceptions import GarminConnectTooManyRequestsError

from coach import auth
from coach.api import create_app
from coach.config import load_settings
from coach.db import connect, upsert_activity
from coach.ingest import garmin
from coach.ingest.fit_files import import_directory

PASSWORD = "correct horse battery"


def fake_zip(activity_id: int) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr(f"{activity_id}_ACTIVITY.fit", b"pas un vrai FIT")  # ignoré à l'import, peu importe ici
    return out.getvalue()


class FakeGarmin:
    """Garmin Connect simulé : `total` activités, éventuellement un refus 429 après `fail_after` téléchargements."""

    ActivityDownloadFormat = garmin.Garmin.ActivityDownloadFormat
    total = 230
    fail_after: int | None = None
    downloads = 0
    pages: list[tuple[int, int]] = []

    class client:
        @staticmethod
        def dumps():
            return '{"di_token": "abc"}'

    def login(self, tokenstore):
        pass

    def get_activities(self, start, limit):
        FakeGarmin.pages.append((start, limit))
        return [{"activityId": i} for i in range(start, min(start + limit, self.total))]

    def download_activity(self, activity_id, dl_fmt):
        if FakeGarmin.fail_after is not None and FakeGarmin.downloads >= FakeGarmin.fail_after:
            raise GarminConnectTooManyRequestsError("429")
        FakeGarmin.downloads += 1
        return fake_zip(activity_id)


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setattr(garmin, "Garmin", FakeGarmin)
    monkeypatch.setattr(garmin, "FULL_SYNC_DELAY_S", 0)
    FakeGarmin.total, FakeGarmin.fail_after, FakeGarmin.downloads, FakeGarmin.pages = 230, None, 0, []
    return dataclasses.replace(load_settings(), data_dir=tmp_path, db_path=tmp_path / "coach.sqlite",
                               fit_dir=tmp_path / "fit", secret_key="phrase secrète de test")


@pytest.fixture
def user_id(settings):
    conn = connect(settings.db_path)
    uid = auth.create_user(conn, "alice", PASSWORD)
    garmin._save_tokens(conn, uid, FakeGarmin(), settings.secret_key)
    auth._failures.clear()
    conn.close()
    return uid


def garmin_files(settings, uid):
    return sorted(p.name for p in (settings.fit_dir / str(uid) / "garmin").iterdir())


def test_full_sync_pages_through_history_and_resumes(settings, user_id):
    conn = connect(settings.db_path)
    progress = garmin.SyncProgress()
    garmin.sync(conn, user_id, settings.fit_dir, settings.secret_key, full=True, progress=progress)
    assert FakeGarmin.pages == [(0, 100), (100, 100), (200, 100)]
    assert (progress.phase, progress.found, progress.downloaded) == ("termine", 230, 230)
    assert len(garmin_files(settings, user_id)) == 230

    # Rien de nouveau : on ne retélécharge rien.
    progress = garmin.SyncProgress()
    garmin.sync(conn, user_id, settings.fit_dir, settings.secret_key, full=True, progress=progress)
    assert (progress.to_download, FakeGarmin.downloads) == (0, 230)


def test_rate_limit_keeps_downloads_and_explains(settings, user_id):
    conn = connect(settings.db_path)
    FakeGarmin.fail_after = 5
    progress = garmin.SyncProgress()
    with pytest.raises(garmin.GarminError, match="reprendra où elle s'est arrêtée"):
        garmin.sync(conn, user_id, settings.fit_dir, settings.secret_key, full=True, progress=progress)
    assert progress.phase == "erreur" and progress.downloaded == 5
    assert len(garmin_files(settings, user_id)) == 5 and not any(n.endswith(".part") for n in garmin_files(
        settings, user_id))
    assert "limite les requêtes" in garmin.status(conn, user_id)["last_error"]

    FakeGarmin.fail_after = None
    progress = garmin.SyncProgress()
    garmin.sync(conn, user_id, settings.fit_dir, settings.secret_key, full=True, progress=progress)
    assert progress.to_download == 225 and garmin.status(conn, user_id)["last_error"] is None


def test_import_only_new_skips_known_files(tmp_path, settings, user_id):
    conn = connect(settings.db_path)
    (tmp_path / "a.zip").write_bytes(fake_zip(1))
    upsert_activity(conn, {"user_id": user_id, "id": "fit:x", "source": "fit", "sport": "running",
                           "start_time": "2026-10-01T07:00:00+00:00", "duration_s": 60,
                           "file_path": f"{tmp_path / 'a.zip'}!1_ACTIVITY.fit"})
    (tmp_path / "b.zip").write_bytes(fake_zip(2))
    assert import_directory(conn, user_id, tmp_path, only_new=True) == (0, 1)  # seul b.zip est relu
    assert import_directory(conn, user_id, tmp_path) == (0, 2)


def test_sync_all_endpoint(settings, user_id):
    client = TestClient(create_app(settings))
    client.post("/api/login", json={"username": "alice", "password": PASSWORD})
    assert client.get("/api/me/garmin/sync-all").json() == {"phase": None, "running": False}
    FakeGarmin.total = 12
    started = client.post("/api/me/garmin/sync-all")
    assert started.status_code == 202 and started.json()["running"]
    # TestClient exécute la tâche de fond avant de rendre la main.
    status = client.get("/api/me/garmin/sync-all").json()
    assert (status["phase"], status["found"], status["downloaded"], status["running"]) == ("termine", 12, 12, False)

    conn = connect(settings.db_path)
    auth.create_user(conn, "bob", PASSWORD)
    bob = TestClient(create_app(settings))
    bob.post("/api/login", json={"username": "bob", "password": PASSWORD})
    assert bob.post("/api/me/garmin/sync-all").status_code == 400  # pas de compte Garmin
