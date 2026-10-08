"""Charge d'entraînement : TRIMP de Banister puis modèle fitness/fatigue (CTL / ATL / TSB).

C'est la base déterministe sur laquelle s'appuie le planificateur ; le modèle XGBoost (roadmap étape 3)
viendra affiner la prédiction de performance, pas remplacer ce calcul.
"""

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta

CTL_DAYS = 42  # "fitness" : charge chronique
ATL_DAYS = 7   # "fatigue" : charge aiguë


def trimp(duration_s: float, avg_hr: float | None, hr_rest: int, hr_max: int) -> float | None:
    """TRIMP de Banister (coefficients hommes : 0,64 et 1,92). None si pas de FC exploitable."""
    if not avg_hr or hr_max <= hr_rest:
        return None
    hrr = (avg_hr - hr_rest) / (hr_max - hr_rest)
    hrr = min(max(hrr, 0.0), 1.0)
    return duration_s / 60 * hrr * 0.64 * math.exp(1.92 * hrr)


@dataclass
class LoadPoint:
    day: date
    load: float
    ctl: float
    atl: float
    tsb: float  # forme du jour = CTL - ATL de la veille


def daily_loads(activities, hr_rest: int, hr_max: int) -> dict[date, float]:
    loads: dict[date, float] = defaultdict(float)
    for a in activities:
        value = trimp(a["duration_s"], a["avg_hr"], hr_rest, hr_max)
        if value is not None:
            loads[datetime.fromisoformat(a["start_time"]).date()] += value
    return loads


def fitness_series(loads: dict[date, float], until: date | None = None) -> list[LoadPoint]:
    if not loads:
        return []
    day, end = min(loads), until or max(loads)
    ctl = atl = 0.0
    series = []
    while day <= end:
        tsb = ctl - atl
        load = loads.get(day, 0.0)
        ctl += (load - ctl) / CTL_DAYS
        atl += (load - atl) / ATL_DAYS
        series.append(LoadPoint(day, round(load, 1), round(ctl, 1), round(atl, 1), round(tsb, 1)))
        day += timedelta(days=1)
    return series


def recent_weekly_km(activities, sport: str, today: date, weeks: int = 4) -> float:
    """Volume hebdomadaire moyen (km) des `weeks` dernières semaines pour un sport donné."""
    start = today - timedelta(weeks=weeks)
    total_m = sum(
        a["distance_m"] or 0
        for a in activities
        if a["sport"] == sport and start <= datetime.fromisoformat(a["start_time"]).date() < today
    )
    return round(total_m / 1000 / weeks, 1)
