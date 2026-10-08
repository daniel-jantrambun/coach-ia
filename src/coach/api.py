import shutil
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Annotated

from fastapi import BackgroundTasks, Cookie, Depends, FastAPI, HTTPException, Response, UploadFile
from pydantic import BaseModel, Field

from coach import auth, service
from coach.config import Settings, load_settings
from coach.db import connect
from coach.ingest import garmin
from coach.ingest.fit_files import import_directory
from coach.planner import Goal

SESSION_COOKIE = "coach_session"


class LoginIn(BaseModel):
    username: str
    password: str


class ProfileIn(BaseModel):
    display_name: str | None = None
    hr_rest: int | None = Field(default=None, ge=30, le=100)
    hr_max: int | None = Field(default=None, ge=120, le=230)


class PasswordIn(BaseModel):
    current_password: str
    new_password: str


class GarminLoginIn(BaseModel):
    email: str
    password: str


class GarminMfaIn(BaseModel):
    code: str


class GoalIn(BaseModel):
    distance_km: float = Field(gt=0, le=100)
    target_time_s: int = Field(gt=0)
    race_date: date
    runs_per_week: int = Field(default=4, ge=3, le=6)


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(title="Coach IA")

    def db():
        # SQLite : une connexion par requête, simple et suffisant pour une famille.
        conn = connect(settings.db_path)
        try:
            yield conn
        finally:
            conn.close()

    Conn = Annotated[object, Depends(db)]

    def current_user(conn: Conn, coach_session: Annotated[str | None, Cookie()] = None) -> dict:
        user = auth.user_for_session(conn, coach_session) if coach_session else None
        if user is None:
            raise HTTPException(401, "Non connecté")
        return user

    User = Annotated[dict, Depends(current_user)]

    def public_user(user: dict) -> dict:
        return {k: user[k] for k in ("id", "username", "display_name", "hr_rest", "hr_max")}

    @app.get("/health")
    def health():
        return {"status": "ok"}

    # --- Comptes ---------------------------------------------------------------------------------------------

    @app.post("/login")
    def login(body: LoginIn, response: Response, conn: Conn):
        user = auth.authenticate(conn, body.username, body.password)
        if user is None:
            raise HTTPException(401, "Identifiants invalides")
        response.set_cookie(
            SESSION_COOKIE, auth.create_session(conn, user["id"]), max_age=auth.SESSION_DAYS * 86400,
            httponly=True, samesite="lax", secure=settings.cookie_secure,
        )
        return public_user(user)

    @app.post("/logout", status_code=204)
    def logout(response: Response, conn: Conn, coach_session: Annotated[str | None, Cookie()] = None):
        if coach_session:
            auth.delete_session(conn, coach_session)
        response.delete_cookie(SESSION_COOKIE)

    @app.get("/me")
    def me(user: User):
        return public_user(user)

    @app.patch("/me")
    def update_me(body: ProfileIn, user: User, conn: Conn):
        service.update_profile(conn, user["id"], **body.model_dump())
        return public_user(auth.user_for_id(conn, user["id"]))

    @app.post("/me/password", status_code=204)
    def change_password(body: PasswordIn, user: User, conn: Conn):
        if not auth.verify_password(body.current_password, user["password_hash"]):
            raise HTTPException(403, "Mot de passe actuel incorrect")
        try:
            auth.set_password(conn, user["username"], body.new_password)
        except ValueError as e:
            raise HTTPException(422, str(e)) from e

    # --- Garmin ----------------------------------------------------------------------------------------------

    @app.get("/me/garmin")
    def garmin_status(user: User, conn: Conn):
        return garmin.status(conn, user["id"])

    @app.post("/me/garmin")
    def garmin_connect(body: GarminLoginIn, user: User, conn: Conn):
        """Le mot de passe Garmin sert uniquement à obtenir des jetons ; il n'est jamais stocké."""
        try:
            return {"status": garmin.start_login(conn, user["id"], body.email, body.password, settings.secret_key)}
        except garmin.GarminError as e:
            raise HTTPException(400, str(e)) from e

    @app.post("/me/garmin/mfa")
    def garmin_mfa(body: GarminMfaIn, user: User, conn: Conn):
        try:
            garmin.complete_mfa(conn, user["id"], body.code, settings.secret_key)
        except garmin.GarminError as e:
            raise HTTPException(400, str(e)) from e
        return {"status": "connected"}

    @app.delete("/me/garmin", status_code=204)
    def garmin_disconnect(user: User, conn: Conn):
        garmin.disconnect(conn, user["id"])

    @app.post("/me/garmin/sync")
    def garmin_sync(user: User, conn: Conn, limit: int = 50):
        try:
            imported, skipped = garmin.sync(conn, user["id"], settings.fit_dir, settings.secret_key, limit)
        except garmin.GarminError as e:
            raise HTTPException(502, str(e)) from e
        return {"imported": imported, "skipped": skipped}

    # --- Activités et charge ---------------------------------------------------------------------------------

    @app.get("/activities")
    def list_activities(user: User, conn: Conn, limit: int = 50):
        return service.activities(conn, user["id"], limit)

    @app.post("/activities/import")
    def import_file(file: UploadFile, user: User, conn: Conn):
        """Import d'un .fit, ou d'un .zip (export complet Garmin compris)."""
        name = Path(file.filename or "upload").name
        if not name.lower().endswith((".fit", ".zip")):
            raise HTTPException(422, "Fichier .fit ou .zip attendu")
        target = settings.fit_dir / str(user["id"]) / "uploads" / datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
        target.mkdir(parents=True)
        with (target / name).open("wb") as out:
            shutil.copyfileobj(file.file, out)
        imported, skipped = import_directory(conn, user["id"], target)
        return {"imported": imported, "skipped": skipped}

    @app.get("/load")
    def load(user: User, conn: Conn, days: int = 120):
        return service.load_series(conn, user, until=date.today())[-days:]

    # --- Plans -----------------------------------------------------------------------------------------------

    @app.get("/plans")
    def list_plans(user: User, conn: Conn):
        return service.list_plans(conn, user["id"])

    @app.post("/plans", status_code=201)
    def create_plan(goal: GoalIn, user: User, conn: Conn):
        try:
            plan_id, plan = service.create_plan(conn, user["id"], Goal(**goal.model_dump()), date.today())
        except (ValueError, service.InvalidPlan) as e:
            raise HTTPException(422, str(e)) from e
        return {"id": plan_id, **plan}

    @app.get("/plans/{plan_id}")
    def get_plan(plan_id: int, user: User, conn: Conn):
        plan = service.get_plan(conn, user["id"], plan_id)
        if plan is None:
            raise HTTPException(404)
        return plan

    @app.post("/plans/{plan_id}/narrate", status_code=202)
    def narrate(plan_id: int, user: User, conn: Conn, background: BackgroundTasks, weeks: list[int] | None = None):
        if service.get_plan(conn, user["id"], plan_id) is None:
            raise HTTPException(404)

        # 1 à 2 min par semaine sur le NAS : on rend la main tout de suite.
        def run():
            bg_conn = connect(settings.db_path)
            try:
                service.narrate_plan(bg_conn, settings, user["id"], plan_id, weeks)
            finally:
                bg_conn.close()

        background.add_task(run)
        return {"status": "en cours"}

    return app


app = create_app(load_settings())
