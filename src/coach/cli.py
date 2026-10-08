import argparse
import json
import os
from datetime import date
from pathlib import Path

from coach import service
from coach.config import load_settings
from coach.db import connect
from coach.planner import Goal


def _parse_time(value: str) -> int:
    """"1:45:00" ou "45:00" → secondes."""
    seconds = 0
    for part in value.split(":"):
        seconds = seconds * 60 + int(part)
    return seconds


def main() -> None:
    parser = argparse.ArgumentParser(prog="coach")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("import-fit", help="Importe les FIT (ou .zip de FIT) d'un dossier")
    p.add_argument("path", type=Path, nargs="?")

    p = sub.add_parser("sync-garmin", help="Télécharge les dernières activités Garmin Connect")
    p.add_argument("--limit", type=int, default=50)

    p = sub.add_parser("plan", help="Génère un plan vers un objectif")
    p.add_argument("--distance", type=float, required=True, help="km, ex. 21.1")
    p.add_argument("--target", type=_parse_time, required=True, help="ex. 1:45:00")
    p.add_argument("--race-date", type=date.fromisoformat, required=True)
    p.add_argument("--runs", type=int, default=4)

    p = sub.add_parser("narrate", help="Fait rédiger un plan par le LLM local")
    p.add_argument("plan_id", type=int)
    p.add_argument("--week", type=int, action="append", help="index de semaine (0 = première)")

    args = parser.parse_args()
    settings = load_settings()
    conn = connect(settings.db_path)

    if args.command == "import-fit":
        from coach.ingest.fit_files import import_directory

        imported, skipped = import_directory(conn, args.path or settings.fit_dir)
        print(f"{imported} activités importées, {skipped} fichiers ignorés")
    elif args.command == "sync-garmin":
        from coach.ingest.garmin import sync

        imported, skipped = sync(
            conn, settings.fit_dir, os.environ["GARMIN_EMAIL"], os.environ["GARMIN_PASSWORD"],
            settings.data_dir / "garmin-tokens", args.limit,
        )
        print(f"{imported} activités importées, {skipped} fichiers ignorés")
    elif args.command == "plan":
        goal = Goal(args.distance, args.target, args.race_date, args.runs)
        plan_id, plan = service.create_plan(conn, goal, date.today())
        for w in plan["weeks"]:
            kinds = ", ".join(f"{s['kind']} {s['distance_km']}" for s in w["sessions"])
            print(f"S{w['index'] + 1:>2} {w['start']} {w['phase']:<6}{' (décharge)' if w['deload'] else '':<11}"
                  f"{w['volume_km']:>5} km  {kinds}")
        for warning in plan["warnings"]:
            print("⚠", warning)
        print(f"Plan #{plan_id} enregistré")
    elif args.command == "narrate":
        count = service.narrate_plan(conn, settings, args.plan_id, args.week)
        plan = service.get_plan(conn, args.plan_id)
        print(json.dumps([w["text"] for w in plan["weeks"] if w["text"]], ensure_ascii=False, indent=2))
        print(f"{count} semaine(s) rédigée(s)")


if __name__ == "__main__":
    main()
