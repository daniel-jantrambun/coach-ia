"""Opérations partagées entre l'API et la CLI. Tout est filtré par utilisateur."""

import json
from dataclasses import asdict
from datetime import date

from coach.config import Settings
from coach.llm import narrate_week
from coach.load import daily_loads, fitness_series, recent_weekly_km
from coach.planner import Goal, build_plan, validate_plan


class InvalidPlan(Exception):
    pass


def activities(conn, user_id: int, limit: int | None = None) -> list[dict]:
    sql = "SELECT * FROM activities WHERE user_id = ? ORDER BY start_time DESC"
    params: tuple = (user_id,)
    if limit:
        sql += " LIMIT ?"
        params += (limit,)
    return [dict(r) for r in conn.execute(sql, params)]


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


def list_plans(conn, user_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT id, created_at, goal_json FROM plans WHERE user_id = ? ORDER BY id DESC", (user_id,)
    )
    return [{"id": r["id"], "created_at": r["created_at"], "goal": json.loads(r["goal_json"])} for r in rows]


def get_plan(conn, user_id: int, plan_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM plans WHERE id = ? AND user_id = ?", (plan_id, user_id)).fetchone()
    if row is None:
        return None
    texts = {
        r["week"]: r["text"]
        for r in conn.execute("SELECT week, text FROM plan_texts WHERE plan_id = ?", (plan_id,))
    }
    plan = json.loads(row["plan_json"])
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
        text = narrate_week(week, settings.llm_base_url, settings.llm_model, settings.llm_timeout_s)
        conn.execute(
            "INSERT OR REPLACE INTO plan_texts (plan_id, week, text, model) VALUES (?, ?, ?, ?)",
            (plan_id, week["index"], text, settings.llm_model),
        )
        conn.commit()
        done += 1
    return done
