from datetime import date, timedelta

import pytest

from coach.multisport import (
    MAX_HARD_PER_WEEK,
    Preferences,
    allocate_hard,
    allocate_sessions,
    build_block,
    validate_block,
)
from coach.sports import BIKE, GYM, RUN, SWIM, analyze

TODAY = date(2026, 10, 8)  # un jeudi : le bloc démarre le lundi 12
MONDAY = date(2026, 10, 12)


def profile(**sports) -> dict:
    """Analyse simulée : sport → (séances/semaine, minutes/semaine)."""
    refs = analyze([], TODAY, 50, 185)["references"]
    return {
        "sports": {s: {"recent_sessions_per_week": n, "baseline_minutes": m} for s, (n, m) in sports.items()},
        "references": refs,
    }


TRIATHLETE = profile(run=(3, 150), bike=(2, 180), swim=(2, 80), gym=(1, 45))


@pytest.mark.parametrize(
    "focus, sessions, analysis",
    [
        ({RUN: "vitesse", BIKE: "endurance", SWIM: "technique", GYM: "force"}, 8, TRIATHLETE),
        ({RUN: "endurance", BIKE: "endurance", SWIM: "vitesse", GYM: "maintien"}, 10, TRIATHLETE),
        ({RUN: "vitesse", BIKE: "vitesse", SWIM: "vitesse"}, 6, TRIATHLETE),
        ({RUN: "maintien", GYM: "force"}, 4, profile(run=(2, 80))),
        ({RUN: "endurance"}, 3, profile()),                       # aucun historique
        ({SWIM: "endurance", GYM: "force"}, 12, profile(swim=(3, 150), gym=(3, 180))),
        ({RUN: "vitesse", BIKE: "maintien", GYM: "maintien"}, 7, profile(run=(5, 300), bike=(1, 60), gym=(1, 30))),
    ],
)
def test_blocks_respect_guardrails(focus, sessions, analysis):
    block = build_block(Preferences(focus, sessions), analysis, TODAY)

    assert validate_block(block) == []
    assert [w.start for w in block.weeks] == [MONDAY + timedelta(weeks=k) for k in range(4)]
    assert [w.deload for w in block.weeks] == [False, False, False, True]
    for week in block.weeks:
        assert len(week.sessions) == sum(block.sessions_per_sport.values())
        assert {s.sport for s in week.sessions} == set(focus)
        assert all(week.start <= s.date < week.start + timedelta(days=7) for s in week.sessions)
        assert all(s.duration_min > 0 and s.duration_min % 5 == 0 for s in week.sessions)
    assert not any(s.hard for s in block.weeks[-1].sessions)  # décharge sans intensité


def test_allocation_follows_habits_and_requested_total():
    prefs = Preferences({RUN: "vitesse", BIKE: "maintien", GYM: "force"}, 6)
    assert allocate_sessions(prefs, {RUN: 3, BIKE: 3}) == {RUN: 3, BIKE: 1, GYM: 2}
    # Séances en plus : aux sports à améliorer d'abord.
    prefs = Preferences({RUN: "endurance", BIKE: "maintien"}, 6)
    assert allocate_sessions(prefs, {RUN: 2, BIKE: 1}) == {RUN: 5, BIKE: 1}


def test_at_most_two_hard_sessions_across_sports():
    prefs = Preferences({RUN: "vitesse", BIKE: "vitesse", SWIM: "vitesse"}, 9)
    hard = allocate_hard(prefs, {RUN: 3, BIKE: 3, SWIM: 3})
    assert sum(len(h) for h in hard.values()) == MAX_HARD_PER_WEEK
    assert hard[RUN] == ["intervals"] and hard[BIKE] == ["intervals"] and hard[SWIM] == []


def test_speed_week_has_intervals_and_endurance_gets_long():
    block = build_block(Preferences({RUN: "vitesse", BIKE: "endurance"}, 6), TRIATHLETE, TODAY)
    week = block.weeks[0]
    run_kinds = sorted(s.kind for s in week.sessions if s.sport == RUN)
    assert "intervals" in run_kinds and "long" in run_kinds
    bike_long = next(s for s in week.sessions if s.sport == BIKE and s.kind == "long")
    assert bike_long.date.weekday() == 5 and bike_long.hr_high is not None
    # Course vitesse en décharge : lignes droites à la place du fractionné.
    assert "strides" in {s.kind for s in block.weeks[-1].sessions if s.sport == RUN}


def test_endurance_progresses_maintenance_stays_flat():
    block = build_block(Preferences({RUN: "endurance", BIKE: "maintien"}, 5), TRIATHLETE, TODAY)
    run = [w.minutes_by_sport[RUN] for w in block.weeks]
    bike = [w.minutes_by_sport[BIKE] for w in block.weeks]
    assert run[0] < run[1] < run[2] and run[3] < run[0]
    assert bike[0] == bike[1] == bike[2] and bike[3] < bike[0]


def test_gym_sessions_are_type_and_duration_only():
    block = build_block(Preferences({GYM: "force"}, 3), profile(gym=(2, 90)), TODAY)
    gym = block.weeks[0].sessions
    assert [s.focus for s in gym] == ["lower", "upper", "full_body"]
    assert all(s.kind == "strength" and s.distance_km is None and s.reps is None for s in gym)


def test_swim_technique_and_paces():
    block = build_block(Preferences({SWIM: "technique"}, 2), profile(swim=(2, 80)), TODAY)
    kinds = {s.kind: s for s in block.weeks[0].sessions}
    assert set(kinds) == {"technique", "easy"}
    assert kinds["technique"].reps == 8 and kinds["technique"].rep_m == 50
    assert kinds["easy"].distance_km == 1.6  # 40 min à 2:30/100 m (allure par défaut)


def test_warnings_for_new_sport_and_thin_spread():
    block = build_block(Preferences({RUN: "vitesse", BIKE: "vitesse", SWIM: "endurance"}, 3), TRIATHLETE, TODAY)
    assert any("Une seule séance" in w for w in block.warnings)
    block = build_block(Preferences({RUN: "maintien", SWIM: "endurance"}, 4), profile(run=(3, 150)), TODAY)
    assert any("Pas de natation" in w for w in block.warnings)


def test_invalid_preferences():
    with pytest.raises(ValueError):
        Preferences({GYM: "vitesse"})
    with pytest.raises(ValueError):
        Preferences({"ski": "endurance"})
    with pytest.raises(ValueError):
        Preferences({RUN: "vitesse", BIKE: "vitesse", SWIM: "vitesse"}, 2)
    with pytest.raises(ValueError):
        Preferences({})


def test_validate_detects_violations():
    block = build_block(Preferences({RUN: "vitesse", BIKE: "vitesse"}, 6), TRIATHLETE, TODAY)
    week = block.weeks[1]
    hard = [s for s in week.sessions if s.hard]
    hard[1].date = hard[0].date + timedelta(days=1)
    week.sessions[0].duration_min += 60
    errors = validate_block(block)
    assert any("48 h" in e for e in errors)
    assert any("≠ volume prévu" in e for e in errors)


def test_extra_sessions_add_time_and_long_stays_usual_length():
    # Une sortie vélo de 2 h par semaine ; on en demande 3 pour l'endurance.
    block = build_block(Preferences({BIKE: "endurance"}, 3), profile(bike=(1, 120)), TODAY)
    week = block.weeks[0]
    long = next(s for s in week.sessions if s.kind == "long")
    assert long.duration_min >= 120
    assert week.minutes == 120 + 2 * 45
    assert any("Le bloc démarre" in w for w in block.warnings)


def test_swim_distance_matches_session_pace():
    block = build_block(Preferences({SWIM: "technique"}, 2), profile(swim=(2, 80)), TODAY)
    for s in block.weeks[0].sessions:
        assert abs(s.distance_km * 1000 / 100 * s.pace_s_per_100m - s.duration_min * 60) <= s.pace_s_per_100m
