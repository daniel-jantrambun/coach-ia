"""Synchronisation incrémentale depuis Garmin Connect (bibliothèque non officielle `garminconnect`).

Les FIT originaux sont téléchargés dans `<fit_dir>/garmin/`, puis importés comme n'importe quel FIT :
un seul chemin d'import, et le dédoublonnage par contenu évite les doublons avec l'export complet.
"""

from pathlib import Path

from garminconnect import Garmin

from coach.ingest.fit_files import import_directory


def sync(conn, fit_dir: Path, email: str, password: str, token_dir: Path, limit: int = 50) -> tuple[int, int]:
    client = Garmin(email, password)
    # Les jetons OAuth sont réutilisés entre deux runs : on évite de se reconnecter (et le MFA) à chaque cron.
    client.login(str(token_dir) if token_dir.exists() else None)
    token_dir.mkdir(parents=True, exist_ok=True)
    client.garth.dump(str(token_dir))

    target = fit_dir / "garmin"
    target.mkdir(parents=True, exist_ok=True)
    for activity in client.get_activities(0, limit):
        path = target / f"{activity['activityId']}.zip"
        if path.exists():
            continue
        data = client.download_activity(
            activity["activityId"], dl_fmt=Garmin.ActivityDownloadFormat.ORIGINAL
        )
        path.write_bytes(data)
    return import_directory(conn, target)
