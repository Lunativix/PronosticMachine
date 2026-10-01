# Modèle de données

Chaque fait importé porte `source`, `imported_at`, `quality` et `source_priority` lorsqu'il vient d'une source externe.

## Identité d'un match

Unicité : compétition, coup d'envoi, domicile, extérieur, source.

Champs : identifiant, compétition, saison, date, équipes, score, statut, source, horodatage d'import.

## Cotes

Table `odds`, une ligne par bookmaker, marché, sélection, horodatage et statut (`active` ou `removed`).

L'ouverture est la première cote active avant le coup d'envoi. La fermeture est la dernière. Aucun update n'efface l'historique.

## Autres tables

`sports`, `competitions`, `seasons`, `teams`, `team_aliases`, `players`, `matches`, `match_events`, `team_statistics`, `player_statistics`, `injuries`, `bookmakers`, `features`, `model_versions`, `predictions`, `prediction_probabilities`, `bet_opportunities`, `alerts`, `backtest_runs`, `backtest_results`, `bankroll_snapshots`, `data_quality_reports`.

## Import

CSV canonique : `competition`, `season`, `kickoff`, `home_team`, `away_team`, scores, stats optionnelles, `odds_home`, `odds_draw`, `odds_away`.

CSV football-data.co.uk : `Div`, `Date`, `HomeTeam`, `AwayTeam`, `FTHG`, `FTAG`, tirs, cartons, cotes `B365*`, `PS*`, `Avg*`.

JSON : liste `matches`, plus `players`, `injuries`, `events` si présents.

## Qualité

`records_total`, `records_valid`, `records_invalid`, `missing_values`, `duplicates`, `future_leakage`, `warnings`, `errors`.

Les lignes invalides ne sont pas insérées et restent dans le rapport. Les stats impossibles sont vidées et signalées. Une cote horodatée après le coup d'envoi est retirée des features pré-match.
