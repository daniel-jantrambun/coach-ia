"""Planificateur multisport sans objectif chiffré : on part de ce que la personne fait déjà (analyse par sport)
et de ce qu'elle veut améliorer, pour construire un bloc de 4 semaines (3 de charge + 1 de décharge).

Le bloc suivant est recalculé à partir des activités réellement faites. Comme pour le planificateur course,
tout est déterministe : le LLM ne fait que rédiger, et `validate_block` vérifie les garde-fous avant
l'enregistrement.
"""

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta

from coach.sports import BIKE, GYM, PLANNED, RUN, SWIM

AXES = {
    RUN: ("maintien", "endurance", "vitesse"),
    BIKE: ("maintien", "endurance", "vitesse"),
    SWIM: ("maintien", "endurance", "vitesse", "technique"),
    GYM: ("maintien", "force"),
}
SPORT_LABELS = {RUN: "course", BIKE: "vélo", SWIM: "natation", GYM: "salle"}

BLOCK_WEEKS = 4
# Volume des semaines de charge, relatif à la 1re semaine, selon l'axe d'amélioration du sport.
LOAD_FACTORS = {
    "maintien": (1.0, 1.0, 1.0),
    "endurance": (1.0, 1.08, 1.16),
    "vitesse": (1.0, 1.04, 1.08),
    "technique": (1.0, 1.04, 1.08),
    "force": (1.0, 1.05, 1.10),
}
DELOAD_FACTOR = 0.7
MAX_WEEKLY_INCREASE = 0.10
MAX_HARD_PER_WEEK = 2       # séances intenses, tous sports confondus
MAX_SESSIONS_PER_DAY = 2
MIN_SESSION_MIN = {RUN: 30, BIKE: 45, SWIM: 30, GYM: 30}
AVG_SESSION_CAP_MIN = {RUN: 75, BIKE: 120, SWIM: 60, GYM: 60}
MAX_SESSIONS = {RUN: 6, BIKE: 5, SWIM: 4, GYM: 4}
LONG_SHARE = {RUN: 0.35, BIKE: 0.40, SWIM: 0.40}
LONG_CAP_MIN = {RUN: 150, BIKE: 300, SWIM: 90}
GYM_FOCUS = {"force": ["lower", "upper", "full_body", "core"], "maintien": ["full_body", "core", "lower", "upper"]}

# Jours préférés (0 = lundi) : sorties longues le week-end, intensité mardi/jeudi, repos plutôt le vendredi.
LONG_DAYS = {RUN: [6, 5], BIKE: [5, 6], SWIM: [5, 6, 2]}
HARD_DAYS = [1, 3, 4, 2, 0, 5, 6]
GYM_DAYS = [0, 2, 3, 5, 1, 4, 6]
EASY_DAYS = [2, 0, 3, 5, 6, 1, 4]


@dataclass(frozen=True)
class Preferences:
    focus: dict[str, str]          # sport → axe d'amélioration ; un sport absent n'est pas planifié
    sessions_per_week: int = 5

    def __post_init__(self):
        if not self.focus:
            raise ValueError("Choisissez au moins un sport à planifier")
        for sport, axis in self.focus.items():
            if sport not in AXES:
                raise ValueError(f"Sport inconnu : {sport}")
            if axis not in AXES[sport]:
                raise ValueError(f"Axe « {axis} » impossible pour {SPORT_LABELS[sport]} ({', '.join(AXES[sport])})")
        if self.sessions_per_week < len(self.focus):
            raise ValueError(f"Il faut au moins {len(self.focus)} séances par semaine pour {len(self.focus)} sports")


@dataclass
class Session:
    date: date
    sport: str                     # run | bike | swim | gym
    kind: str                      # easy | long | tempo | intervals | strides | technique | strength
    duration_min: int
    hard: bool = False
    distance_km: float | None = None
    pace_s_per_km: int | None = None       # course
    pace_s_per_100m: int | None = None     # natation
    hr_low: int | None = None              # vélo
    hr_high: int | None = None
    reps: int | None = None
    rep_m: int | None = None
    rep_s: int | None = None
    recovery_s: int | None = None
    focus: str | None = None               # salle : lower | upper | full_body | core


@dataclass
class Week:
    index: int
    start: date
    deload: bool
    minutes: int
    minutes_by_sport: dict[str, int]
    sessions: list[Session] = field(default_factory=list)


@dataclass
class Block:
    preferences: Preferences
    number: int
    sessions_per_sport: dict[str, int]
    baseline_minutes: dict[str, int]
    references: dict
    weeks: list[Week]
    warnings: list[str]
    mode: str = "multisport"

    def to_dict(self) -> dict:
        return asdict(self)


def _round5(x: float) -> int:
    return int(5 * round(x / 5))


def _floor5(x: float) -> int:
    return int(5 * (x // 5))


def _next_monday(d: date) -> date:
    return d + timedelta(days=(7 - d.weekday()) % 7)


def allocate_sessions(prefs: Preferences, current: dict[str, float]) -> dict[str, int]:
    """Séances par sport : on part de la fréquence actuelle, 2 minimum pour un sport à améliorer,
    puis on ajuste au total demandé (on retire d'abord aux sports en maintien, on ajoute aux sports à améliorer)."""
    sports = [s for s in PLANNED if s in prefs.focus]
    improving = lambda s: prefs.focus[s] != "maintien"
    counts = {}
    for s in sports:
        n = max(1, round(current.get(s, 0)))
        counts[s] = min(max(n, 2) if improving(s) else n, MAX_SESSIONS[s])
    while sum(counts.values()) > prefs.sessions_per_week:
        s = max((s for s in sports if counts[s] > 1), key=lambda s: (not improving(s), counts[s], -sports.index(s)))
        counts[s] -= 1
    while sum(counts.values()) < prefs.sessions_per_week:
        candidates = [s for s in sports if counts[s] < MAX_SESSIONS[s]]
        if not candidates:
            break
        counts[min(candidates, key=lambda s: (not improving(s), counts[s], sports.index(s)))] += 1
    return counts


def _has_long(sport: str, axis: str, n: int) -> bool:
    return sport in LONG_SHARE and n >= 2 and (axis == "endurance" or n >= 3)


def allocate_hard(prefs: Preferences, counts: dict[str, int]) -> dict[str, list[str]]:
    """Séances intenses par sport (2 max au total) : d'abord les sports « vitesse », puis une séance au seuil
    pour un sport d'endurance fréquent. Chaque sport garde au moins une séance facile."""
    hard: dict[str, list[str]] = {s: [] for s in counts}
    room = lambda s: counts[s] - _has_long(s, prefs.focus[s], counts[s]) - len(hard[s]) - 1
    budget = MAX_HARD_PER_WEEK
    speed = [s for s in counts if prefs.focus[s] == "vitesse"]
    for _ in range(2):
        for s in speed:
            if budget and room(s) > 0:
                hard[s].append("intervals" if not hard[s] else "tempo")
                budget -= 1
    for s in counts:
        if budget and prefs.focus[s] == "endurance" and s in (RUN, BIKE) and counts[s] >= 3 and room(s) > 0:
            hard[s].append("tempo")
            budget -= 1
    return hard


def _kinds(sport: str, axis: str, n: int, hard: list[str], deload: bool) -> list[str]:
    if sport == GYM:
        return ["strength"] * n
    kinds = ["long"] if _has_long(sport, axis, n) else []
    if deload:
        # Décharge : pas d'intensité, quelques lignes droites pour garder de la vivacité en course.
        kinds += ["strides"] if sport == RUN and hard else []
    else:
        kinds += hard
    if sport == SWIM and axis == "technique":
        kinds.append("technique")
    return kinds + ["easy"] * (n - len(kinds))


def _split(sport: str, kinds: list[str], minutes: int, long_min: float = 0) -> list[int]:
    """Répartit les minutes de la semaine entre les séances, par tranches de 5 min : la somme est exacte.

    La sortie longue reste nettement plus longue que les autres, et jamais plus courte qu'une séance habituelle
    (`long_min`), tant que les autres séances gardent leur durée minimale."""
    units = minutes // 5
    durations = [0] * len(kinds)
    if "long" in kinds and len(kinds) > 1:
        i = kinds.index("long")
        share = max(LONG_SHARE[sport], 1.5 / (len(kinds) + 0.5))
        others_min = min(MIN_SESSION_MIN[sport] // 5, units // len(kinds))
        wanted = max(round(units * share), round(long_min / 5))
        durations[i] = max(min(wanted, LONG_CAP_MIN[sport] // 5, units - (len(kinds) - 1) * others_min), 1)
        units -= durations[i]
    others = [i for i, k in enumerate(kinds) if durations[i] == 0]
    share, rest = divmod(units, len(others))
    for j, i in enumerate(others):
        durations[i] = share + (1 if j < rest else 0)
    return [5 * d for d in durations]


def _session(sport: str, kind: str, minutes: int, day: date, refs: dict, gym_focus: str | None) -> Session:
    s = Session(day, sport, kind, minutes, hard=kind in ("intervals", "tempo"))
    seconds = minutes * 60
    if sport == RUN:
        p = refs["run_paces"]
        s.pace_s_per_km = p["long"] if kind == "long" else p.get(kind, p["easy"])
        distance = seconds / s.pace_s_per_km
        if kind == "intervals":
            s.reps = min(max((seconds - 1500) // (p["intervals"] + 90), 3), 8)
            s.rep_m, s.recovery_s = 1000, 90
            distance = s.reps + max(seconds - s.reps * p["intervals"], 0) / p["easy"]
        elif kind == "tempo":
            s.reps, s.recovery_s = 2, 120
            s.rep_s = min(max(round(minutes * 0.2), 8), 20) * 60
            distance = 2 * s.rep_s / p["tempo"] + max(seconds - 2 * s.rep_s, 0) / p["easy"]
        elif kind == "strides":
            s.reps, s.rep_m, s.recovery_s = 6, 100, 60
        s.distance_km = round(distance, 1)
    elif sport == BIKE:
        zones = refs["hr_zones"]
        zone = {"intervals": "seuil", "tempo": "tempo"}.get(kind, "endurance")
        s.hr_low, s.hr_high = zones[zone]
        if kind == "intervals":
            s.reps, s.rep_s, s.recovery_s = min(max((minutes - 30) // 8, 3), 6), 300, 180
        elif kind == "tempo":
            s.reps, s.recovery_s = 2, 300
            s.rep_s = min(max(round(minutes * 0.15), 10), 20) * 60
    elif sport == SWIM:
        base = refs["swim_pace_s_per_100m"]
        s.pace_s_per_100m = {"intervals": base - 8, "long": base + 5, "technique": base + 10}.get(kind, base)
        # Le fractionné compte ses récupérations : distance à l'allure habituelle, sinon à l'allure de la séance.
        meters = max(round(seconds / (base if kind == "intervals" else s.pace_s_per_100m)), 2) * 100
        s.distance_km = meters / 1000
        if kind == "intervals":
            s.reps, s.rep_m, s.recovery_s = min(max(round(meters * 0.4 / 100), 6), 16), 100, 20
        elif kind == "technique":
            s.reps, s.rep_m, s.recovery_s = 8, 50, 20
    else:
        s.focus = gym_focus
    return s


def _assign_days(drafts: list[dict]) -> list[int]:
    """Place les séances dans la semaine : sorties longues, puis intensité (jamais deux jours de suite),
    puis salle, puis le reste. Une séance par jour tant qu'on peut garder un jour de repos."""
    per_day = 1 if len(drafts) <= 6 else MAX_SESSIONS_PER_DAY
    placed: dict[int, list[int]] = defaultdict(list)

    def fits(i: int, d: int, strict: bool) -> bool:
        if len(placed[d]) >= per_day or any(drafts[j]["sport"] == drafts[i]["sport"] for j in placed[d]):
            return False
        if drafts[i]["hard"]:
            around = [j for x in (d - 1, d, d + 1) for j in placed.get(x, [])]
            if any(drafts[j]["hard"] for j in around):
                return False
            # Si possible, pas d'intensité la veille ou le lendemain d'une sortie longue.
            if strict and any(drafts[j]["kind"] == "long" for j in around):
                return False
        return True

    def priority(i: int) -> int:
        d = drafts[i]
        return 0 if d["kind"] == "long" else 1 if d["hard"] else 2 if d["sport"] == GYM else 3

    days = [0] * len(drafts)
    for i in sorted(range(len(drafts)), key=lambda i: (priority(i), i)):
        d = drafts[i]
        prefs = (LONG_DAYS[d["sport"]] if d["kind"] == "long" else HARD_DAYS if d["hard"]
                 else GYM_DAYS if d["sport"] == GYM else EASY_DAYS)
        day = None
        for strict in (True, False):
            # Parmi les jours possibles, le moins rempli d'abord (on ne double une journée qu'en dernier).
            candidates = [x for x in prefs if fits(i, x, strict)]
            if candidates:
                day = min(candidates, key=lambda x: (len(placed[x]), prefs.index(x)))
                break
        if day is None:  # semaine très chargée : le jour le moins rempli
            day = min(range(7), key=lambda x: (len(placed[x]), x))
        days[i] = day
        placed[day].append(i)
    return days


def build_block(prefs: Preferences, analysis: dict, today: date, number: int = 1) -> Block:
    sports = [s for s in PLANNED if s in prefs.focus]
    profile = analysis["sports"]
    refs = analysis["references"]
    warnings: list[str] = []

    counts = allocate_sessions(prefs, {s: profile[s]["recent_sessions_per_week"] for s in sports if s in profile})
    for s in sports:
        if prefs.focus[s] != "maintien" and counts[s] < 2:
            warnings.append(f"Une seule séance de {SPORT_LABELS[s]} par semaine : progression limitée. "
                            "Ajoutez une séance par semaine si vous le pouvez.")
    hard = allocate_hard(prefs, counts)
    if any(prefs.focus[s] == "vitesse" and not hard[s] for s in sports):
        warnings.append("Pas assez de séances pour travailler la vitesse partout (2 séances intenses max par "
                        "semaine, tous sports confondus).")

    # Minutes par sport et par semaine : +10 % max d'une semaine à l'autre pour chaque sport, donc au total.
    # Les séances ajoutées par rapport aux habitudes s'ajoutent au volume actuel (durée minimale chacune).
    baseline = {s: profile.get(s, {}).get("baseline_minutes", 0) for s in sports}
    habit = {s: max(round(profile[s]["recent_sessions_per_week"]), 1) if s in profile else 0 for s in sports}
    usual = {s: baseline[s] / habit[s] if habit[s] else 0 for s in sports}  # durée d'une séance habituelle
    minutes: dict[str, list[int]] = {}
    for s in sports:
        floor, cap = counts[s] * MIN_SESSION_MIN[s], counts[s] * AVG_SESSION_CAP_MIN[s]
        added = max(counts[s] - habit[s], 0) * MIN_SESSION_MIN[s] if habit[s] else 0
        first = _round5(min(max(baseline[s] + added, floor), cap))
        weeks = [first]
        for factor in LOAD_FACTORS[prefs.focus[s]][1:]:
            weeks.append(_floor5(min(first * factor, weeks[-1] * (1 + MAX_WEEKLY_INCREASE))))
        weeks.append(max(_floor5(first * DELOAD_FACTOR), 5 * counts[s]))
        minutes[s] = weeks
        if baseline[s] == 0:
            warnings.append(f"Pas de {SPORT_LABELS[s]} ces dernières semaines : le bloc démarre doucement "
                            f"({first} min/semaine).")

    history = sum(baseline.values())
    first_total = sum(m[0] for m in minutes.values())
    if not profile:
        warnings.append("Aucune activité sur les 8 dernières semaines : importez vos données pour un plan adapté.")
    elif history and first_total > history * (1 + MAX_WEEKLY_INCREASE) + 30:
        warnings.append(f"Le bloc démarre à {first_total} min/semaine contre ~{history} ces dernières semaines : "
                        "ajoutez les nouvelles séances progressivement et écoutez vos sensations.")

    start = _next_monday(today)
    block_weeks = []
    for k in range(BLOCK_WEEKS):
        deload = k == BLOCK_WEEKS - 1
        drafts = []
        for s in sports:
            kinds = _kinds(s, prefs.focus[s], counts[s], hard[s], deload)
            focus_cycle = GYM_FOCUS[prefs.focus[s]] if s == GYM else []
            long_min = usual[s] * (DELOAD_FACTOR if deload else 1)
            for j, (kind, mins) in enumerate(zip(kinds, _split(s, kinds, minutes[s][k], long_min), strict=True)):
                drafts.append({"sport": s, "kind": kind, "minutes": mins, "hard": kind in ("intervals", "tempo"),
                               "focus": focus_cycle[j % len(focus_cycle)] if focus_cycle else None})
        week_start = start + timedelta(weeks=k)
        sessions = [
            _session(d["sport"], d["kind"], d["minutes"], week_start + timedelta(days=day), refs, d["focus"])
            for d, day in zip(drafts, _assign_days(drafts), strict=True)
        ]
        sessions.sort(key=lambda x: (x.date, PLANNED.index(x.sport)))
        by_sport = {s: minutes[s][k] for s in sports}
        block_weeks.append(Week(k, week_start, deload, sum(by_sport.values()), by_sport, sessions))

    return Block(prefs, number, counts, baseline, refs, block_weeks, warnings)


def validate_block(block: Block) -> list[str]:
    """Garde-fous. Renvoie la liste des violations (vide = bloc valide)."""
    errors = []
    max_so_far = None
    for w in block.weeks:
        label = f"Semaine {w.index + 1}"
        total = sum(s.duration_min for s in w.sessions)
        if total != w.minutes:
            errors.append(f"{label} : séances ({total} min) ≠ volume prévu ({w.minutes} min)")
        hard = sorted(s.date for s in w.sessions if s.hard)
        if len(hard) > MAX_HARD_PER_WEEK:
            errors.append(f"{label} : {len(hard)} séances intenses (max {MAX_HARD_PER_WEEK})")
        if any((b - a).days < 2 for a, b in zip(hard, hard[1:], strict=False)):
            errors.append(f"{label} : deux séances intenses à moins de 48 h")
        if w.sessions and max(Counter(s.date for s in w.sessions).values()) > MAX_SESSIONS_PER_DAY:
            errors.append(f"{label} : plus de {MAX_SESSIONS_PER_DAY} séances le même jour")
        if max_so_far is not None:
            if w.deload and w.minutes >= max_so_far:
                errors.append(f"{label} : la décharge ({w.minutes} min) n'allège pas la charge")
            elif not w.deload and w.minutes > max_so_far * (1 + MAX_WEEKLY_INCREASE):
                errors.append(f"{label} : {w.minutes} min dépasse +10 % du maximum ({max_so_far} min)")
        max_so_far = max(max_so_far or 0, w.minutes)
    if not block.weeks or not block.weeks[-1].deload:
        errors.append("Le bloc doit se terminer par une semaine de décharge")
    return errors
