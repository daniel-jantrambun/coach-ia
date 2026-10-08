"""Opérations partagées entre l'API et la CLI."""

import json
from dataclasses import asdict
from datetime import date

from coach.config import Settings
from coach.llm import narrate_week
from coach.load import recent_weekly_km
from coach.planner import Goal, build_plan, validate_plan


class InvalidPlan(Exception):
    pass


def activities(conn, limit: int | None = None) -> list[dict]:
    sql = "SELECT * FROM activities ORDER BY start_time DESC"
    rows = conn.execute(sql + (" LIMIT ?" if limit else ""), (limit,) if limit else ()).fetchall()
    return [dict(r) for r in rows]


def create_plan(conn, goal: Goal, today: date) -> tuple[int, dict]:
    current = recent_weekly_km(activities(conn), goal.sport, today)
    plan = build_plan(goal, current, start=today)
    errors = validate_plan(plan)
    if errors:
        raise InvalidPlan("; ".join(errors))
    plan_dict = json.loads(json.dumps(plan.to_dict(), default=str))
    cur = conn.execute(
        "INSERT INTO plans (goal_json, plan_json) VALUES (?, ?)",
        (json.dumps(asdict(goal), default=str), json.dumps(plan_dict)),
    )
    conn.commit()
    return cur.lastrowid, plan_dict


def get_plan(conn, plan_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM plans WHERE id = ?", (plan_id,)).fetchone()
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


def narrate_plan(conn, settings: Settings, plan_id: int, weeks: list[int] | None = None) -> int:
    """Fait rédiger les semaines demandées (toutes par défaut). Renvoie le nombre de semaines rédigées."""
    plan = get_plan(conn, plan_id)
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
