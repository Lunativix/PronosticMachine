# API

OpenAPI : `GET /docs`.

Toutes les réponses utiles portent le texte : « Les probabilités sont des estimations statistiques et ne garantissent aucun résultat. »

## Lecture

- `GET /health`
- `GET /matches`
- `GET /matches/{id}`
- `GET /matches/{id}/prediction`
- `GET /matches/{id}/value`
- `GET /predictions`
- `GET /opportunities?state=&min_edge=&min_ev=&min_quality=`
- `GET /odds?match_id=`
- `GET /backtests`
- `GET /backtests/{id}`
- `GET /models`
- `GET /models/{id}`
- `GET /analytics/performance`
- `GET /quality`

## Écriture

- `POST /data/import` fichier CSV ou JSON, ou `path` à l'intérieur du projet
- `POST /data/sync` corps `{ "competitions": ["E0", "F1"], "season": "2526" }`
- `GET /data/sources`

## Fixtures à venir

- `GET /fixtures/upcoming?days=14&competition=&status=`
- `POST /fixtures/sync?days=14`
- `GET /fixtures/sync/status`

`FIXTURE_PROVIDER=espn` interroge le calendrier public ESPN, sans clé, pour les compétitions de `backend/app/fixtures/competitions.yaml`. `FIXTURE_PROVIDER=api_football` exige `API_KEY`. Sans provider configuré, la synchronisation renvoie une erreur et n'insère aucun match.

Un job interne relance la synchronisation toutes les `FIXTURE_SYNC_INTERVAL_MINUTES` minutes, puis lance `analyze_upcoming_matches`.

## Bet Analyzer

- `GET /analysis/upcoming` dernières analyses des matchs J+14
- `GET /analysis/combinations` combinés PRUDENT, VALUE et ÉQUILIBRÉ du même passage
- `GET /analysis/performance` calibration, Brier, ROI, yield et drawdown sur les analyses déjà résolues
- `POST /analysis/run` ou `sportwise analysis run`

La confiance (0–100) mesure la robustesse du signal, pas la probabilité de gain. Les cotes ne sont utilisées que si elles sont déjà stockées. Deux sélections de matchs différents utilisent le produit des probabilités. Deux sélections du même match utilisent la probabilité jointe de la matrice de scores, ou `correlation_status=UNKNOWN` si cette matrice est absente. Les anciennes analyses ne sont pas supprimées. Les alertes restent non délivrées tant qu'aucun canal n'est configuré.

`POST /data/sync` télécharge les résultats réels publiés par football-data.co.uk (Premier League `E0`, Ligue 1 `F1`, Liga `SP1`, Serie A `I1`, Bundesliga `D1`, et les autres codes de `GET /data/sources`). Aucune clé n'est requise. Si la saison demandée n'est pas encore publiée, la saison précédente est utilisée.

`API_KEY` reste l'accès optionnel à API-Football. `ODDS_API_KEY` reste l'accès optionnel à The Odds API.

- `POST /data/validate?path=`
- `POST /models/train`
- `POST /backtests/run` corps `{ "staking": "FRACTIONAL_KELLY", "window_mode": "expanding" }`
- `POST /predictions/generate` corps `{ "match_ids": null }`
- `POST /odds/updates` corps `{ "match_id", "bookmaker", "market", "selection", "price", "captured_at", "action" }`

`action` vaut `upsert` ou `remove`. `remove` ajoute une ligne `removed` et conserve les cotations précédentes.

Les chemins d'import doivent rester sous la racine du projet. Les extensions acceptées sont `.csv` et `.json`.
