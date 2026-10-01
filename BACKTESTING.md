# Backtesting

Le moteur est chronologique.

À chaque match terminé :

1. Les matchs d'entraînement ont un coup d'envoi strictement antérieur.
2. Le mode `expanding` garde tout le passé. Le mode `rolling` garde `rolling_days`.
3. Le modèle Dixon-Coles est réestimé lorsque `MODEL_RETRAIN_DAYS` est dépassé.
4. Les cotes utilisées sont celles capturées avant le coup d'envoi.
5. Un stake n'est simulé que si l'état est `SIGNAL`.
6. La bankroll est mise à jour, puis un snapshot est enregistré.

Le split aléatoire n'existe pas dans ce moteur.

## Mise

`FIXED_STAKE`, `PERCENT_BANKROLL`, `KELLY`, `FRACTIONAL_KELLY`.

La fraction de Kelly est multipliée par `KELLY_FRACTION` (0.25 par défaut) puis plafonnée par `MAX_STAKE_PERCENT` (0.02). Le stake ne dépasse jamais la bankroll.

Slippage et commission réduisent la cote nette : `1 + (cote - 1) * (1 - slippage) * (1 - commission)`.

## Métriques

- profit : somme des PnL
- yield : profit / mises
- ROI : profit / bankroll initiale
- taux de réussite, cote moyenne, cote médiane, EV moyenne
- drawdown maximum sur la courbe de bankroll
- volatilité des rendements par pari
- ratio de type Sharpe : moyenne / écart-type des rendements, fois racine du nombre de paris. Ce n'est pas un Sharpe financier.
- profit factor, plus longue série gagnante et perdante
- yield du benchmark « toujours domicile » et « toujours le favori de cote »

Les regroupements couvrent saison, compétition, marché, modèle, bookmaker, tranche de cote et tranche d'edge.

## Benchmark

Le benchmark mise 1 unité sur chaque match coté, indépendamment du filtre. Il sert de comparaison, pas d'objectif de gain.
