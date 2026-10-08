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

Multi-utilisateurs (famille), accessible uniquement via le réseau local ou le WireGuard du NAS : l'app n'est pas
exposée sur Internet.

Origine : conversation Le Chat « Utilisation de données sportives pour modèles d'AI » (oct. 2026),
résumée et revue dans [docs/architecture.md](docs/architecture.md).

## État d'avancement (roadmap)

| # | Étape | État |
|---|-------|------|
| 1 | Import des activités (FIT Garmin, sync Garmin Connect) → SQLite | ✅ code prêt, à tester sur les vraies données |
| 2 | Exploration : charge hebdo, CTL/ATL/TSB | ✅ écran Activités (forme / fatigue) |
| 3 | Modèle v1 : prédiction de performance (XGBoost) | ⏳ |
| 4 | Planificateur v1 déterministe + garde-fous | ✅ course à pied |
| 5 | Rédaction des séances par le LLM 3B | ✅ code prêt, à tester sur le NAS |
| 6 | Feedback (RPE) → ajustement du plan | ⏳ |
| 7 | Détection de fatigue, recalibrage mensuel | ⏳ |

## Interface web

React + Vite + TypeScript + Tailwind dans [web/](web/), servie par FastAPI (un seul conteneur). Pensée pour le
téléphone, en clair/sombre selon le réglage de l'appareil :

- **Mon plan** : objectif, allures, semaines dépliables (semaine en cours mise en avant), rédaction par le LLM.
- **Activités** : fraîcheur du jour, courbes forme/fatigue, import de fichiers, synchro Garmin.
- **Profil** : FC repos/max, connexion du compte Garmin (MFA compris), mot de passe.

L'API est sous `/api` (docs : `/api/docs`).

## Comptes et Garmin

- **Pas d'inscription libre** : les comptes sont créés par l'admin (`coach add-user`). Mots de passe hachés
  (scrypt), sessions par cookie HttpOnly (30 jours), blocage 15 min après 5 échecs.
- **Garmin sans stocker le mot de passe** : chacun connecte son compte depuis l'app (`POST /me/garmin`, puis
  `/me/garmin/mfa` si le MFA est actif). Le mot de passe Garmin sert une seule fois à obtenir des jetons ; seuls
  ces jetons sont stockés, chiffrés avec `COACH_SECRET_KEY`. Quand ils expirent, la synchro le signale
  (`last_error`) et la personne se reconnecte.
- **Sans Garmin** : import d'un `.fit` ou de l'export complet Garmin (`.zip`) via `POST /activities/import`.
- Les données de chacun (activités, plans, FC repos/max) sont isolées par utilisateur.

## Développement local

```bash
python3.14 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
```

```bash
.venv/bin/coach add-user benjamin --name Benjamin
# Importer l'export complet Garmin ("Exporter vos données", le .zip tel quel)
.venv/bin/coach import-fit --user benjamin ~/Downloads/garmin-export
# Générer un plan : semi en 1h45, 4 sorties/semaine
.venv/bin/coach plan --user benjamin --distance 21.1 --target 1:45:00 --race-date 2027-02-07 --runs 4
# Faire rédiger la 1re semaine par le LLM (Ollama local : ollama pull qwen2.5:3b)
.venv/bin/coach narrate --user benjamin 1 --week 0
# API (docs sur http://localhost:8000/api/docs)
.venv/bin/uvicorn coach.api:app --reload
```

```bash
# Interface web en dev (http://localhost:5173, /api relayé vers :8000)
cd web && npm install && npm run dev
npm run lint && npm run build
```

## Déploiement sur le NAS

Deux conteneurs ([compose.yaml](compose.yaml)) : `app` (FastAPI + front, SQLite dans `./data`) et `llm` (Ollama,
3 Go de RAM max). Le NAS n'accède pas aux registres Docker : c'est la CI qui télécharge et transfère les images
via WireGuard, comme pour `cv-bd`.

### Workflows GitHub Actions

- **Test, build Docker image and deploy it on Synology** (à chaque push) : tests Python + lint/build du front, puis
  sur `main` : image `ghcr.io/daniel-jantrambun/coach-ia`, transfert au NAS, `docker load`, copie du
  `compose.yaml` (image épinglée sur le commit), `docker compose up -d`, vérification de `/api/health`.
  Le déploiement est ignoré tant que la variable `JUPITER_IP` n'est pas configurée.
- **Install Ollama on Synology** (manuel) : télécharge l'image Ollama et le modèle sur le runner, les installe sur
  le NAS. À lancer avant le premier déploiement, puis pour changer de version ou de modèle.

Secrets et variables du dépôt (Settings → Secrets and variables → Actions), les mêmes que pour `cv-bd` :

| Nom | Type | Contenu |
|---|---|---|
| `WG_CONFIG` | secret | config WireGuard du runner |
| `CI_GITHUB_PWD` | secret | mot de passe de l'utilisateur SSH du NAS |
| `JUPITER_USER` | variable | utilisateur SSH du NAS |
| `JUPITER_IP` | variable | IP du NAS dans le WireGuard |

### Première installation

1. Sur le NAS : créer `/volume1/docker/coach-ia/` et y placer le `.env` (`COACH_SECRET_KEY`, voir
   [.env.example](.env.example)), lisible par root uniquement (`chmod 600`).
2. Lancer le workflow **Install Ollama on Synology**.
3. Relancer le workflow de déploiement (ou pousser sur `main`).
4. Créer les comptes :

   ```bash
   cd /volume1/docker/coach-ia && sudo docker compose exec app coach add-user benjamin --name Benjamin
   ```

L'app est alors sur `http://<ip-du-nas>:8000`, depuis le réseau local ou le WireGuard.

Synchro Garmin nocturne de tous les comptes connectés : tâche planifiée DSM (Panneau de configuration →
Planificateur de tâches, en root) :

```bash
cd /volume1/docker/coach-ia && /usr/local/bin/docker compose exec -T app coach sync-garmin --all
```

Sauvegarder `data/coach.sqlite` (Hyper Backup) et `COACH_SECRET_KEY` séparément.

## Configuration

Voir [.env.example](.env.example) : clé de chiffrement des jetons Garmin, cookie sécurisé, modèle LLM.
FC de repos / FC max (pour le TRIMP) : réglage par utilisateur (`PATCH /me`).
