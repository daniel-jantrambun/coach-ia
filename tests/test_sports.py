from datetime import date, timedelta

from coach.sports import BIKE, GYM, OTHER, RUN, SWIM, analyze, category, run_paces, swim_pace

TODAY = date(2026, 10, 8)


def activity(days_ago: int, sport: str, minutes: float, km: float | None = None, hr: float | None = None,
             sub_sport: str | None = None):
    day = TODAY - timedelta(days=days_ago)
    return {"start_time": f"{day}T07:00:00+00:00", "sport": sport, "sub_sport": sub_sport,
            "duration_s": minutes * 60, "distance_m": km * 1000 if km else None, "avg_hr": hr}


def test_categories():
    assert category("running") == RUN
    assert category("running", "treadmill") == RUN
    assert category("cycling", "indoor_cycling") == BIKE
    assert category("fitness_equipment", "indoor_cycling") == BIKE
    assert category("swimming", "lap_swimming") == SWIM
    assert category("training", "strength_training") == GYM
    assert category("training") == GYM
    assert category("training", "yoga") == OTHER
    assert category("hiking") == OTHER
    assert category("generic") == OTHER


def test_analyze_profiles_each_sport():
    acts = (
        [activity(d, "running", 50, 9, 145) for d in (1, 3, 6, 8, 10, 13, 15, 20, 22, 27)]
        + [activity(d, "cycling", 90, 30) for d in (2, 9, 16, 23, 30, 37, 44, 51)]
        + [activity(d, "training", 45, sub_sport="strength_training") for d in (4, 11)]
        + [activity(5, "hiking", 180, 12), activity(12, "hiking", 120, 8), activity(100, "swimming", 40, 1.5)]
    )
    result = analyze(acts, TODAY, 50, 185)

    assert set(result["sports"]) == {RUN, BIKE, GYM}  # natation trop ancienne : hors fenêtre
    run = result["sports"][RUN]
    assert run["sessions"] == 10 and run["recent_sessions_per_week"] == 2.5
    assert run["km_per_week"] == round(90 / 8, 1)
    assert run["trend"] == "nouveau"  # rien entre 4 et 8 semaines
    assert result["sports"][BIKE]["trend"] == "stable"
    assert result["sports"][GYM]["km_per_week"] is None
    assert result["others"] == [{"sport": "hiking", "sessions": 2, "minutes": 300}]
    assert result["references"]["hr_zones"]["endurance"] == [131, 147]


def test_baseline_ignores_a_deload_week():
    # Semaines de 150, 150, 150 puis 100 min (décharge) : la référence reste 150.
    acts = [activity(d, "running", 75, 13) for d in (22, 25, 15, 18, 8, 11)] + [activity(1, "running", 100, 17)]
    assert analyze(acts, TODAY, 50, 185)["sports"][RUN]["baseline_minutes"] == 150


def test_run_paces_from_heart_rate():
    # Plus on va vite, plus la FC monte : régression lue au seuil (85 % de FC de réserve).
    runs = [activity(d, "running", 50, km, hr) for d, km, hr in
            [(1, 8.0, 140), (3, 8.6, 148), (5, 9.2, 155), (7, 10.0, 165), (9, 8.3, 144)]]
    paces, source = run_paces(runs, 50, 185)
    assert source == "fc"
    assert paces["intervals"] < paces["tempo"] < paces["long"] < paces["easy"]
    # 85 % de FC de réserve ≈ 165 bpm, la FC de la sortie à 12 km/h (5:00/km).
    assert 290 < paces["tempo"] < 310


def test_run_paces_fallbacks():
    paces, source = run_paces([activity(1, "running", 60, 10)], 50, 185)
    assert source == "allure_moyenne" and paces["tempo"] == round(360 / 1.18)
    assert run_paces([], 50, 185)[1] == "defaut"
    # La marche (> 12 min/km) n'est pas une course.
    assert run_paces([activity(1, "running", 60, 4)], 50, 185)[1] == "defaut"


def test_swim_pace():
    assert swim_pace([activity(1, "swimming", 40, 2.0), activity(3, "swimming", 30, 1.0)]) == (150, "allure_moyenne")
    assert swim_pace([])[1] == "defaut"
