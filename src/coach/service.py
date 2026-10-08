"""Opérations partagées entre l'API et la CLI. Tout est filtré par utilisateur."""

import json
from dataclasses import asdict
from datetime import date

from coach.activity import detail as fit_detail
from coach.config import Settings
from coach.llm import narrate_week
from coach.load import daily_loads, fitness_series, recent_weekly_km
from coach.multisport import Preferences, build_block, validate_block
from coach.planner import Goal, build_plan, validate_plan
from coach.sports import analyze, category, category_stats


class InvalidPlan(Exception):
    pass


def activities(conn, user_id: int, limit: int | None = None) -> list[dict]:
    sql = "SELECT * FROM activities WHERE user_id = ? ORDER BY start_time DESC"
    params: tuple = (user_id,)
    if limit:
        sql += " LIMIT ?"
        params += (limit,)
    return [dict(r) for r in conn.execute(sql, params)]


def activities_with_category(conn, user_id: int, cat: str | None = None, limit: int | None = None) -> list[dict]:
    rows = [{**a, "category": category(a["sport"], a.get("sub_sport"))} for a in activities(conn, user_id)]
    if cat:
        rows = [a for a in rows if a["category"] == cat]
    return rows[:limit] if limit else rows


def activity_detail(conn, user: dict, activity_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM activities WHERE user_id = ? AND id = ?", (user["id"], activity_id)).fetchone()
    if row is None:
        return None
    a = dict(row)
    cat = category(a["sport"], a.get("sub_sport"))
    a.pop("file_path")  # chemin sur le NAS : inutile côté interface
    return {**a, "category": cat, **fit_detail(dict(row), cat, user["hr_rest"], user["hr_max"])}


def stats(conn, user: dict, today: date, weeks: int) -> dict:
    return {"weeks": weeks, "categories": category_stats(activities(conn, user["id"]), today, weeks)}


def load_series(conn, user: dict, until: date) -> list:
    loads = daily_loads(activities(conn, user["id"]), user["hr_rest"], user["hr_max"])
    return fitness_series(loads, until=until)


def update_profile(conn, user_id: int, **fields) -> None:
    allowed = {k: v for k, v in fields.items() if k in ("display_name", "hr_rest", "hr_max") and v is not None}
    if allowed:
        assignments = ", ".join(f"{k} = :{k}" for k in allowed)
        conn.execute(f"UPDATE users SET {assignments} WHERE id = :id", {**allowed, "id": user_id})
        conn.commit()


def create_plan(conn, user_id: int, goal: Goal, today: date) -> tuple[int, dict]:
    current = recent_weekly_km(activities(conn, user_id), goal.sport, today)
    plan = build_plan(goal, current, start=today)
    errors = validate_plan(plan)
    if errors:
        raise InvalidPlan("; ".join(errors))
    plan_dict = json.loads(json.dumps(plan.to_dict(), default=str))
    cur = conn.execute(
        "INSERT INTO plans (user_id, goal_json, plan_json) VALUES (?, ?, ?)",
        (user_id, json.dumps(asdict(goal), default=str), json.dumps(plan_dict)),
    )
    conn.commit()
    return cur.lastrowid, plan_dict


def analysis(conn, user: dict, today: date) -> dict:
    """Ce que la personne fait, sport par sport, sur les 8 dernières semaines."""
    return analyze(activities(conn, user["id"]), today, user["hr_rest"], user["hr_max"])


def create_block(conn, user: dict, prefs: Preferences, today: date) -> tuple[int, dict]:
    """Bloc multisport de 4 semaines, recalculé à partir des activités réelles à chaque nouveau bloc."""
    # Numéro à la suite du dernier bloc (pas du nombre de blocs : un bloc peut avoir été supprimé).
    previous = conn.execute(
        "SELECT MAX(json_extract(goal_json, '$.block')) FROM plans WHERE user_id = ?"
        " AND json_extract(goal_json, '$.mode') = 'multisport'",
        (user["id"],),
    ).fetchone()[0] or 0
    block = build_block(prefs, analysis(conn, user, today), today, number=previous + 1)
    errors = validate_block(block)
    if errors:
        raise InvalidPlan("; ".join(errors))
    plan_dict = json.loads(json.dumps(block.to_dict(), default=str))
    goal = {"mode": "multisport", **asdict(prefs), "block": block.number, "start": str(block.weeks[0].start)}
    cur = conn.execute(
        "INSERT INTO plans (user_id, goal_json, plan_json) VALUES (?, ?, ?)",
        (user["id"], json.dumps(goal), json.dumps(plan_dict)),
    )
    conn.commit()
    return cur.lastrowid, plan_dict


def list_plans(conn, user_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT id, created_at, goal_json FROM plans WHERE user_id = ? ORDER BY id DESC", (user_id,)
    )
    # Les plans antérieurs au multisport n'ont pas de mode : ce sont des plans course.
    return [{"id": r["id"], "created_at": r["created_at"], "goal": {"mode": "race", **json.loads(r["goal_json"])}}
            for r in rows]


def delete_plan(conn, user_id: int, plan_id: int) -> bool:
    """Supprime un plan et ses textes rédigés (cascade). False si le plan n'existe pas pour cet utilisateur."""
    deleted = conn.execute("DELETE FROM plans WHERE id = ? AND user_id = ?", (plan_id, user_id)).rowcount
    conn.commit()
    return deleted > 0


def get_plan(conn, user_id: int, plan_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM plans WHERE id = ? AND user_id = ?", (plan_id, user_id)).fetchone()
    if row is None:
        return None
    texts = {
        r["week"]: r["text"]
        for r in conn.execute("SELECT week, text FROM plan_texts WHERE plan_id = ?", (plan_id,))
    }
    plan = {"mode": "race", **json.loads(row["plan_json"])}
    plan["goal"] = {"mode": plan["mode"], **json.loads(row["goal_json"])}
    for week in plan["weeks"]:
        week["text"] = texts.get(week["index"])
    return {"id": row["id"], "created_at": row["created_at"], **plan}


def narrate_plan(conn, settings: Settings, user_id: int, plan_id: int, weeks: list[int] | None = None) -> int:
    """Fait rédiger les semaines demandées (toutes par défaut). Renvoie le nombre de semaines rédigées."""
    plan = get_plan(conn, user_id, plan_id)
    if plan is None:
        raise KeyError(plan_id)
    done = 0
    for week in plan["weeks"]:
        if weeks is not None and week["index"] not in weeks:
            continue
        text = narrate_week(week, settings.llm_base_url, settings.llm_model, settings.llm_timeout_s,
                            multisport=plan["mode"] == "multisport")
        conn.execute(
            "INSERT OR REPLACE INTO plan_texts (plan_id, week, text, model) VALUES (?, ?, ?, ?)",
            (plan_id, week["index"], text, settings.llm_model),
        )
        conn.commit()
        done += 1
    return done
