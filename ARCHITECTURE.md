# Architecture

Sportwise AI sépare les données, les features, les modèles, l'analyse de value, le backtest, l'API et le dashboard.

```
import -> validation -> tables -> features as-of T -> modèles -> calibration
       -> probabilités -> cotes -> edge / EV -> filtre -> alerte interne
       -> walk-forward -> bankroll -> API -> React
```

## Décisions

- SQLAlchemy 2 synchrone. `DATABASE_URL` choisit SQLite ou PostgreSQL.
- Les providers (`csv`, `json`, API-Football, The Odds API) normalisent des lignes. Le ML ne lit que les tables.
- Les cotes sont un journal. Une nouvelle cote insère une ligne. La fermeture est la dernière cote dont l'horodatage est inférieur ou égal au coup d'envoi.
- Les modèles sont versionnés dans `model_versions` et dans `data/models/{cle}/{version}/`. Une nouvelle version ne remplace pas le fichier précédent.
- Seuls les artefacts marqués `sportwise_artifact` sont rechargés.
- Les états possibles sont `INSUFFICIENT_DATA`, `LOW_CONFIDENCE`, `NO_SIGNAL`, `SIGNAL`.
- Les alertes externes restent inactives tant que `DISCORD_WEBHOOK_URL`, `TELEGRAM_BOT_TOKEN` ou `SMTP_URL` est vide.

## Packages

- `app/data` : providers et qualité
- `app/features` : features causales football
- `app/ml` : Dixon-Coles, logistique, XGBoost, ensemble, calibration
- `app/betting` : marge, EV, Kelly, qualité du signal
- `app/backtesting` : walk-forward et métriques
- `app/api` : FastAPI
- `frontend` : six pages

## Extension sport

`SportAdapter` expose le code sport et le marché. `FootballAdapter` est la seule implémentation V1.
