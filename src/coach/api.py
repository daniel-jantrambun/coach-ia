from datetime import date

from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel, Field

from coach import service
from coach.config import load_settings
from coach.db import connect
from coach.load import daily_loads, fitness_series
from coach.planner import Goal

settings = load_settings()
app = FastAPI(title="Coach IA")


def db():
    # SQLite : une connexion par requête, c'est simple et suffisant pour un seul utilisateur.
    return connect(settings.db_path)


class GoalIn(BaseModel):
    distance_km: float = Field(gt=0, le=100)
    target_time_s: int = Field(gt=0)
    race_date: date
    runs_per_week: int = Field(default=4, ge=3, le=6)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/activities")
def list_activities(limit: int = 50):
    with db() as conn:
        return service.activities(conn, limit)


@app.get("/load")
def load(days: int = 120):
    with db() as conn:
        series = fitness_series(daily_loads(service.activities(conn), settings.hr_rest, settings.hr_max),
                                until=date.today())
    return series[-days:]


@app.post("/plans", status_code=201)
def create_plan(goal: GoalIn):
    with db() as conn:
        try:
            plan_id, plan = service.create_plan(conn, Goal(**goal.model_dump()), date.today())
        except (ValueError, service.InvalidPlan) as e:
            raise HTTPException(422, str(e)) from e
    return {"id": plan_id, **plan}


@app.get("/plans/{plan_id}")
def get_plan(plan_id: int):
    with db() as conn:
        plan = service.get_plan(conn, plan_id)
    if plan is None:
        raise HTTPException(404)
    return plan


@app.post("/plans/{plan_id}/narrate", status_code=202)
def narrate(plan_id: int, background: BackgroundTasks, weeks: list[int] | None = None):
    with db() as conn:
        if service.get_plan(conn, plan_id) is None:
            raise HTTPException(404)

    # 1 à 2 min par semaine sur le NAS : on rend la main tout de suite.
    def run():
        with db() as conn:
            service.narrate_plan(conn, settings, plan_id, weeks)

    background.add_task(run)
    return {"status": "en cours"}
