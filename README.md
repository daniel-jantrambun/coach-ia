# Coach IA

Planificateur d'entraînement personnel, hébergé sur le Synology DS720+ :

```
Garmin (export FIT / Garmin Connect) ─▶ SQLite ─▶ charge d'entraînement (CTL/ATL/TSB)
                                                     │
                       objectif (distance, temps, date) ─▶ planificateur déterministe ─▶ garde-fous
                                                                                            │
                                                         LLM 3B local (Ollama) ◀── plan JSON, semaine par semaine
                                                                │
                                                     texte des séances (ne modifie aucun chiffre)
```

Pas de chat : l'outil génère un plan, le LLM ne fait que le rédiger. Coût : ~0 €/an (électricité).
Origine : conversation Le Chat « Utilisation de données sportives pour modèles d'AI » (oct. 2026),
résumée et revue dans [docs/architecture.md](docs/architecture.md).

## État d'avancement (roadmap)

| # | Étape | État |
|---|-------|------|
| 1 | Import des activités (FIT Garmin, sync Garmin Connect) → SQLite | ✅ code prêt, à tester sur les vraies données |
| 2 | Exploration : charge hebdo, CTL/ATL/TSB | 🟡 API `/load`, pas encore d'UI |
| 3 | Modèle v1 : prédiction de performance (XGBoost) | ⏳ |
| 4 | Planificateur v1 déterministe + garde-fous | ✅ course à pied |
| 5 | Rédaction des séances par le LLM 3B | ✅ code prêt, à tester sur le NAS |
| 6 | Feedback (RPE) → ajustement du plan | ⏳ |
| 7 | Détection de fatigue, recalibrage mensuel | ⏳ |

## Développement local

```bash
python3.14 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
```

```bash
# Importer l'export Garmin ("Exporter vos données" → dossier DI_CONNECT/DI-Connect-Uploaded-Files)
.venv/bin/coach import-fit ~/Downloads/garmin-export
# Générer un plan : semi en 1h45, 4 sorties/semaine
.venv/bin/coach plan --distance 21.1 --target 1:45:00 --race-date 2027-02-07 --runs 4
# Faire rédiger la 1re semaine par le LLM (Ollama local : ollama pull qwen2.5:3b)
.venv/bin/coach narrate 1 --week 0
# API (docs sur http://localhost:8000/docs)
.venv/bin/uvicorn coach.api:app --reload
```

## Déploiement sur le NAS

`compose.yaml` lance deux conteneurs : `app` (FastAPI + planificateur, SQLite dans `./data`) et `llm` (Ollama,
limité à 3 Go de RAM). Après le premier démarrage :

```bash
docker compose exec llm ollama pull qwen2.5:3b
docker compose exec app coach import-fit /data/fit
```

Accès distant via Tailscale. Le workflow GitHub Actions (build + WireGuard + `docker load`) reste à reprendre de
`cv-bd`.

## Configuration

Voir [.env.example](.env.example) : FC de repos / FC max (pour le TRIMP), modèle LLM, identifiants Garmin.
