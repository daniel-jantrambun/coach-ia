"""Rédaction des séances par un LLM 3B local (Ollama ou llama.cpp server, API compatible OpenAI).

Le LLM reçoit une semaine du plan en JSON et renvoie du texte : il ne calcule rien et ne modifie aucun
chiffre. On l'appelle semaine par semaine : sur le J4125 (sans AVX), l'évaluation d'un long prompt est
le vrai goulot, bien plus que la génération.
"""

import json

import httpx

SYSTEM_PROMPT = (
    "Tu es un coach de course à pied. On te donne une semaine d'entraînement en JSON, déjà calculée. "
    "Rédige en français, pour chaque séance, 1 à 2 phrases claires : contenu, allure en min/km, objectif. "
    "N'invente aucune séance et ne change aucun chiffre (distance, allure, répétitions). "
    "Termine par une phrase sur l'objectif de la semaine (phase, décharge éventuelle)."
)


def _format_pace(seconds_per_km: int) -> str:
    return f"{seconds_per_km // 60}:{seconds_per_km % 60:02d}/km"


def week_prompt(week: dict) -> str:
    compact = {
        "semaine": week["index"] + 1,
        "phase": week["phase"],
        "decharge": week["deload"],
        "volume_km": week["volume_km"],
        "seances": [
            {
                "date": str(s["date"]),
                "type": s["kind"],
                "distance_km": s["distance_km"],
                "allure": _format_pace(s["pace_s_per_km"]),
                **({"repetitions": f"{s['reps']}x{s['rep_m']}m, récup {s['recovery_s']}s"} if s["reps"] else {}),
            }
            for s in week["sessions"]
        ],
    }
    return json.dumps(compact, ensure_ascii=False)


def narrate_week(week: dict, base_url: str, model: str, timeout_s: float) -> str:
    response = httpx.post(
        f"{base_url.rstrip('/')}/v1/chat/completions",
        json={
            "model": model,
            "temperature": 0.3,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": week_prompt(week)},
            ],
        },
        timeout=timeout_s,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"].strip()
