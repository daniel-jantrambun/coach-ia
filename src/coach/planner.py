"""Planificateur 100 % déterministe : objectif + volume actuel → plan semaine par semaine.

Tous les chiffres (volumes, allures, répétitions) sont calculés ici. Le LLM ne fait que les rédiger,
et `validate_plan` vérifie les garde-fous avant qu'un plan soit enregistré.
"""

from dataclasses import asdict, dataclass, field
from datetime import date, timedelta

MAX_WEEKLY_INCREASE = 0.10   # +10 % de volume max par rapport au plus gros volume déjà planifié
DELOAD_EVERY = 4             # 1 semaine de décharge toutes les 4
DELOAD_FACTOR = 0.75
MIN_WEEKLY_KM = 10.0

# Volume de pointe visé selon la distance (km/semaine), plafonné ensuite par la règle des +10 %.
PEAK_KM_BY_DISTANCE = [(5, 30.0), (10, 40.0), (21.1, 50.0), (42.2, 70.0)]
LONG_RUN_CAP_KM = [(5, 12.0), (10, 16.0), (21.1, 22.0), (42.2, 32.0)]

# Jours d'entraînement (0 = lundi) selon le nombre de sorties par semaine : qualité mardi, sortie longue dimanche.
DAY_LAYOUTS = {3: [1, 3, 6], 4: [1, 2, 4, 6], 5: [0, 1, 3, 4, 6], 6: [0, 1, 2, 3, 4, 6]}
QUALITY_DAY, LONG_DAY = 1, 6


@dataclass(frozen=True)
class Goal:
    distance_km: float
    target_time_s: int
    race_date: date
    runs_per_week: int = 4
    sport: str = "running"

    @property
    def race_pace_s(self) -> float:
        return self.target_time_s / self.distance_km


@dataclass
class Session:
    date: date
    kind: str                  # easy | long | tempo | intervals | strides | race
    distance_km: float
    pace_s_per_km: int
    reps: int | None = None
    rep_m: int | None = None
    recovery_s: int | None = None


@dataclass
class Week:
    index: int
    start: date
    phase: str                 # base | build | taper | race
    volume_km: float
    deload: bool = False
    sessions: list[Session] = field(default_factory=list)


@dataclass
class Plan:
    goal: Goal
    current_weekly_km: float
    weeks: list[Week]
    paces: dict[str, int]
    warnings: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


def _lookup(table: list[tuple[float, float]], distance_km: float) -> float:
    for threshold, value in table:
        if distance_km <= threshold:
            return value
    return table[-1][1]


def riegel_time_s(goal: Goal, distance_km: float) -> float:
    """Temps équivalent sur une autre distance (formule de Riegel, exposant 1,06)."""
    return goal.target_time_s * (distance_km / goal.distance_km) ** 1.06


def training_paces(goal: Goal) -> dict[str, int]:
    pace = lambda d: riegel_time_s(goal, d) / d
    return {
        "easy": round(pace(42.195) * 1.12),
        "long": round(pace(42.195) * 1.08),
        "tempo": round(pace(15)),       # ~ allure seuil (≈ 1 h de course)
        "intervals": round(pace(5)),
        "race": round(goal.race_pace_s),
    }


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _next_monday(d: date) -> date:
    return d if d.weekday() == 0 else _monday(d) + timedelta(weeks=1)


def build_plan(goal: Goal, current_weekly_km: float, start: date) -> Plan:
    if goal.runs_per_week not in DAY_LAYOUTS:
        raise ValueError(f"runs_per_week doit être entre {min(DAY_LAYOUTS)} et {max(DAY_LAYOUTS)}")
    first_monday = _next_monday(start)
    race_monday = _monday(goal.race_date)
    total_weeks = (race_monday - first_monday).days // 7 + 1
    if total_weeks < 3:
        raise ValueError("Il faut au moins 3 semaines avant la course")

    warnings: list[str] = []
    if current_weekly_km == 0:
        warnings.append("Aucune activité sur les 4 dernières semaines : importez vos données (coach import-fit).")
    taper_weeks = 2 if goal.distance_km > 30 else 1
    build_weeks = total_weeks - taper_weeks - 1
    recommended_peak = _lookup(PEAK_KM_BY_DISTANCE, goal.distance_km)
    if build_weeks < 6:
        warnings.append(f"Seulement {build_weeks} semaines de préparation : plan court, progression limitée.")

    paces = training_paces(goal)
    weeks: list[Week] = []

    # Phase de construction : +10 % max, décharge toutes les 4 semaines.
    loaded = max(current_weekly_km, MIN_WEEKLY_KM)
    peak = max(loaded, recommended_peak)
    for i in range(build_weeks):
        deload = (i + 1) % DELOAD_EVERY == 0
        if deload:
            volume = loaded * DELOAD_FACTOR
        else:
            volume = loaded if i == 0 else min(loaded * (1 + MAX_WEEKLY_INCREASE), peak)
            loaded = volume
        phase = "base" if i < build_weeks * 0.4 else "build"
        weeks.append(Week(i, first_monday + timedelta(weeks=i), phase, round(volume, 1), deload))

    reached_peak = max((w.volume_km for w in weeks), default=loaded)
    if reached_peak < recommended_peak * 0.9:
        warnings.append(
            f"Volume de pointe atteint {reached_peak:.0f} km/sem, en dessous des ~{recommended_peak:.0f} "
            "recommandés pour cette distance (progression bridée à +10 %/semaine)."
        )

    # Affûtage : 70 % puis 55 % du volume de pointe (une seule semaine à 65 % hors marathon).
    for j, factor in enumerate([0.7, 0.55] if taper_weeks == 2 else [0.65]):
        i = build_weeks + j
        weeks.append(Week(i, first_monday + timedelta(weeks=i), "taper", round(reached_peak * factor, 1)))

    weeks.append(Week(total_weeks - 1, race_monday, "race", 0.0))

    for week in weeks:
        week.sessions = (
            _race_week_sessions(goal, week, paces) if week.phase == "race" else _week_sessions(goal, week, paces)
        )
        week.volume_km = round(sum(s.distance_km for s in week.sessions), 1)

    return Plan(goal, round(current_weekly_km, 1), weeks, paces, warnings)


def _week_sessions(goal: Goal, week: Week, paces: dict[str, int]) -> list[Session]:
    """Répartit le volume cible de la semaine entre les séances : la somme reste égale au volume."""
    days = DAY_LAYOUTS[goal.runs_per_week]
    volume = week.volume_km
    on = lambda day: week.start + timedelta(days=day)

    long_km = min(volume * 0.3, _lookup(LONG_RUN_CAP_KM, goal.distance_km))
    hard = week.phase in ("build", "taper") and not week.deload
    # Séance de qualité le mardi ; la 2e (seuil) le premier jour d'entraînement à partir du jeudi.
    tempo_day = next(d for d in days if d >= 3) if hard and week.phase == "build" and len(days) >= 4 else None
    interval_km = volume * 0.2 if hard else 0.0
    tempo_km = volume * 0.18 if tempo_day is not None else 0.0
    easy_days = [d for d in days if d not in (LONG_DAY, tempo_day) and not (hard and d == QUALITY_DAY)]
    easy_km = (volume - long_km - interval_km - tempo_km) / len(easy_days)

    sessions = []
    for day in days:
        if day == LONG_DAY:
            sessions.append(Session(on(day), "long", round(long_km, 1), paces["long"]))
        elif hard and day == QUALITY_DAY:
            # ~ la moitié de la séance à allure 5 km, le reste en échauffement/retour au calme/récup.
            sessions.append(Session(on(day), "intervals", round(interval_km, 1), paces["intervals"],
                                    reps=max(3, round(interval_km / 2)), rep_m=1000, recovery_s=90))
        elif day == tempo_day:
            sessions.append(Session(on(day), "tempo", round(tempo_km, 1), paces["tempo"]))
        elif day == QUALITY_DAY:
            # Phase de base ou décharge : pas d'intensité lourde, footing + lignes droites.
            sessions.append(Session(on(day), "strides", round(easy_km, 1), paces["easy"],
                                    reps=6, rep_m=100, recovery_s=60))
        else:
            sessions.append(Session(on(day), "easy", round(easy_km, 1), paces["easy"]))
    return sessions


def _race_week_sessions(goal: Goal, week: Week, paces: dict[str, int]) -> list[Session]:
    race_day = goal.race_date.weekday()
    # Footings courts avant la course, jamais la veille.
    easy_days = [d for d in DAY_LAYOUTS[goal.runs_per_week] if d < race_day - 1][:3]
    sessions = [
        Session(week.start + timedelta(days=d), "strides" if k == 0 else "easy", 6.0, paces["easy"],
                **({"reps": 4, "rep_m": 200, "recovery_s": 60} if k == 0 else {}))
        for k, d in enumerate(easy_days)
    ]
    sessions.append(Session(goal.race_date, "race", goal.distance_km, paces["race"]))
    return sessions


def validate_plan(plan: Plan) -> list[str]:
    """Garde-fous. Renvoie la liste des violations (vide = plan valide)."""
    errors = []
    training = [w for w in plan.weeks if w.phase != "race"]
    max_so_far = max(plan.current_weekly_km, MIN_WEEKLY_KM)
    weeks_since_deload = 0
    for w in training:
        if w.volume_km > max_so_far * (1 + MAX_WEEKLY_INCREASE) + 0.5:
            errors.append(f"Semaine {w.index + 1} : {w.volume_km} km dépasse +10 % du maximum ({max_so_far} km)")
        max_so_far = max(max_so_far, w.volume_km)
        weeks_since_deload = 0 if (w.deload or w.phase == "taper") else weeks_since_deload + 1
        if weeks_since_deload >= DELOAD_EVERY:
            errors.append(f"Semaine {w.index + 1} : {DELOAD_EVERY} semaines de charge sans décharge")
        hard = sum(1 for s in w.sessions if s.kind in ("intervals", "tempo"))
        if hard > 2:
            errors.append(f"Semaine {w.index + 1} : {hard} séances intenses (max 2)")
    return errors
