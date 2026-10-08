# Architecture et décisions

Synthèse de la conversation Le Chat (canvas « Coach IA personnel — Architecture & Coûts »), avec les points
revus avant de démarrer.

## Décisions reprises telles quelles

- **Hébergement** : Synology DS720+ seul (Celeron J4125 4 cœurs, 6 Go RAM, 2 slots NVMe), accès par le
  réseau local ou le WireGuard existant (choix d'oct. 2026, plutôt que Tailscale ou Cloudflare Access).
  Cloudflare écarté : données de santé + GPS restent à la maison, et le Python tourne sans contrainte.
- **Pas de chat** : un outil de planification. Le plan est calculé par du code déterministe ; le LLM ne fait
  que rédiger les séances et justifier les ajustements, appelé à chaque recalcul de plan.
- **LLM** : 3B quantifié Q4 (Qwen 2.5 3B ou Llama 3.2 3B) via Ollama, ~2 Go de RAM, déchargé après inactivité.
  Un 7B est déconseillé tant que le NAS reste à 6 Go.
- **Garde-fous** : +10 % de volume par semaine max, 1 semaine de décharge toutes les 4, plafonds d'intensité.
- **Coût** : ~0 €/an (électricité ~10–15 €/an). Option : barrette 8 Go (~25 €) si un 7B devient utile.

## Points revus

1. **Une seule base SQLite, pas de PostgreSQL.** Un seul utilisateur, quelques milliers de lignes : un fichier
   SQLite (sur le volume NVMe si possible) suffit et retire un conteneur. Deux conteneurs au lieu de trois.

2. **Charge d'entraînement (CTL/ATL/TSB) avant XGBoost.** Le modèle fitness/fatigue de Banister (TRIMP à partir
   de la FC) est le standard du domaine, déterministe et explicable, et sert directement au planificateur
   (forme du jour, détection de surcharge). XGBoost (étape 3) arrive ensuite pour prédire la performance ; avec
   peu de courses officielles dans l'historique, la cible devra venir des meilleurs efforts (best efforts) sur
   les sorties, pas seulement des résultats de course.

3. **Import : privilégier l'export complet Garmin plutôt que l'API Strava.** L'API Strava est limitée à
   100 requêtes / 15 min et 1 000 / jour ; récupérer 1 000 activités avec leurs streams prend plusieurs jours.
   L'export « Exporter vos données » de Garmin donne tous les FIT d'un coup. La synchro quotidienne passe
   ensuite par `garminconnect` (non officiel : peut casser si Garmin durcit sa protection, comme pour
   `garminexport`).

4. **Le CPU du NAS est le vrai goulot pour le LLM.** Le J4125 n'a pas d'AVX/AVX2. Les « 3–6 tokens/s »
   annoncés sont optimistes, et surtout l'évaluation du prompt (un plan de 16 semaines en JSON) est lente.
   D'où : un appel par semaine avec un JSON compact, en tâche de fond, timeout de 10 min. Vérifier aussi que
   l'image `ollama/ollama` actuelle tourne bien sans AVX ; sinon basculer sur un `llama.cpp server` compilé
   sans AVX (même API OpenAI-compatible, il suffit de changer `COACH_LLM_BASE_URL`).

5. **Le LLM ne touche jamais aux chiffres, par construction.** Son texte est stocké à part (`plan_texts`), le
   plan JSON n'est jamais réécrit à partir de sa sortie.

6. **Multisport à venir.** Le planificateur v1 ne couvre que la course à pied. Si l'objectif est un triathlon,
   le modèle de charge (TRIMP) gère déjà tous les sports ; c'est la génération des séances qui devra évoluer.

## Planificateur v1

- Allures dérivées du temps visé par la formule de Riegel (exposant 1,06) : facile, sortie longue, seuil (~15 km),
  fractionné (~5 km), allure course.
- Phases : base (40 % des semaines de préparation, pas d'intensité lourde) → construction (fractionné + seuil)
  → affûtage (1 semaine, 2 pour le marathon) → semaine de course.
- Volume de départ = moyenne des 4 dernières semaines ; volume de pointe visé selon la distance
  (30 / 40 / 50 / 70 km pour 5 km / 10 km / semi / marathon), atteint seulement si la règle des +10 % le permet,
  sinon le plan l'indique dans `warnings`.
- `validate_plan` vérifie les garde-fous avant tout enregistrement.

## Multi-utilisateurs (famille)

- Comptes créés par l'admin, mot de passe scrypt, sessions côté serveur (seul le hash du jeton est en base).
- L'app reste privée (réseau local / WireGuard) : elle détient des jetons Garmin et des données de santé.
- Garmin n'a pas d'API officielle ouverte aux particuliers (Connect Developer Program réservé aux entreprises).
  On utilise `garminconnect` ≥ 0.3.5 (nouvelle connexion « app mobile » ; l'ancienne via `garth` est cassée
  depuis 2026, et < 0.3.5 a la CVE-2026-54447). Le mot de passe est échangé contre des jetons, chiffrés en base
  (Fernet, clé dérivée de `COACH_SECRET_KEY`) ; il n'est jamais stocké.
- Strava écarté : ses conditions d'API interdisent depuis fin 2024 l'usage des données dans des modèles d'IA.
- SQLite suffit : quelques utilisateurs, très peu d'écritures concurrentes (WAL + busy_timeout). PostgreSQL ne
  deviendrait utile que pour une app publique.
