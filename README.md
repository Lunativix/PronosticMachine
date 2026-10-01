# Sportwise AI

Outil d'analyse statistique du football. Les probabilités sont des estimations. Elles ne garantissent aucun résultat.

## Prérequis

- Python 3.12
- Node.js 20+
- Docker, uniquement si vous voulez PostgreSQL

Sans Docker, la base locale est SQLite (`data/sportwise.db`).

## Démarrage

```powershell
cd C:\Users\DENREE\Desktop\PronosticMachine
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
copy .env.example .env
$env:PYTHONPATH = "backend"
.\.venv\Scripts\python.exe -m alembic -c backend\alembic.ini upgrade head
```

Les commandes Alembic se lancent depuis `backend` si vous préférez :

```powershell
cd backend
$env:PYTHONPATH = "."
..\.venv\Scripts\python.exe -m alembic upgrade head
```

Backend :

```powershell
cd backend
$env:PYTHONPATH = "."
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Frontend :

```powershell
cd frontend
npm install
npm run dev
```

API : http://127.0.0.1:8000/docs  
Dashboard : http://localhost:5173

PostgreSQL :

```powershell
docker compose up -d
```

Le service backend du compose utilise `DATABASE_URL=postgresql+psycopg://sportwise:sportwise@db:5432/sportwise`.

## Pipeline

Les fichiers dans `data/synthetic` sont réservés aux tests. Ils ne représentent pas une performance sportive réelle.

```powershell
.\.venv\Scripts\python.exe scripts\generate_test_data.py
.\.venv\Scripts\python.exe scripts\import_data.py data\synthetic\football_matches.csv --synthetic
.\.venv\Scripts\python.exe scripts\train_models.py
.\.venv\Scripts\python.exe scripts\run_backtest.py
```

Import réel, format canonique ou export football-data.co.uk :

```powershell
.\.venv\Scripts\python.exe scripts\import_data.py data\raw\votre_fichier.csv
```

## CLI

Depuis `backend` avec `PYTHONPATH=.` :

```powershell
..\.venv\Scripts\python.exe -m app.cli data import ..\data\raw\matches.csv
..\.venv\Scripts\python.exe -m app.cli data validate ..\data\raw\matches.csv
..\.venv\Scripts\python.exe -m app.cli features build
..\.venv\Scripts\python.exe -m app.cli model train
..\.venv\Scripts\python.exe -m app.cli model evaluate
..\.venv\Scripts\python.exe -m app.cli backtest run
..\.venv\Scripts\python.exe -m app.cli prediction generate
..\.venv\Scripts\python.exe -m app.cli dashboard
```

## Sources externes

Sans clé, le système reste sur les fichiers importés.

- `API_KEY` : API-Football (`https://v3.football.api-sports.io`)
- `ODDS_API_KEY` : The Odds API
- `DATA_PROVIDER=api_football` active l'adaptateur fixtures
- `ODDS_PROVIDER` sélectionne la source de cotes

Aucune clé n'est écrite dans le code. Les secrets ne sont pas journalisés.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests -q
```

## Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md)
- [DATA_MODEL.md](DATA_MODEL.md)
- [MODELING.md](MODELING.md)
- [BACKTESTING.md](BACKTESTING.md)
- [API.md](API.md)

## Limites

- Docker n'est pas installé sur la machine de développement actuelle. Les fichiers Compose sont prêts.
- La V1 ne modélise que le football 1X2. Les autres sports passent par `SportAdapter`.
- LightGBM et Polars ne sont pas utilisés : pandas et XGBoost couvrent le volume V1.
- Les features de marché sont calculées et affichées. Par défaut elles n'entrent pas dans le modèle, pour éviter un edge circulaire avec la même cote. `USE_MARKET_FEATURES_IN_MODEL` est réservé à une extension.
- SHAP peut échouer sur un arbre incompatible. Le champ `explanation_method` passe alors à `native_poisson` ou `unavailable`, sans texte inventé.
