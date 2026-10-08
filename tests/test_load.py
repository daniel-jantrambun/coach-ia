from datetime import date

from coach.load import daily_loads, fitness_series, recent_weekly_km, trimp


def activity(day: str, km: float, hr: float | None = 150, sport: str = "running"):
    return {"start_time": f"{day}T07:00:00+00:00", "duration_s": km * 330, "distance_m": km * 1000,
            "avg_hr": hr, "sport": sport}


def test_trimp_grows_with_intensity():
    assert trimp(3600, 170, 50, 185) > trimp(3600, 140, 50, 185) > 0
    assert trimp(3600, None, 50, 185) is None


def test_fitness_series_fills_rest_days():
    loads = daily_loads([activity("2026-09-01", 10), activity("2026-09-05", 12)], 50, 185)
    series = fitness_series(loads, until=date(2026, 9, 10))
    assert len(series) == 10
    assert series[1].load == 0 and series[1].atl < series[0].atl + series[0].load
    # Après un entraînement la fatigue (ATL) monte plus vite que la forme (CTL) : TSB négatif le lendemain.
    assert series[1].tsb < 0


def test_recent_weekly_km_filters_sport_and_window():
    acts = [activity("2026-09-28", 20), activity("2026-10-05", 20), activity("2026-10-06", 40, sport="cycling"),
            activity("2026-08-01", 100)]
    assert recent_weekly_km(acts, "running", date(2026, 10, 8)) == 10.0
