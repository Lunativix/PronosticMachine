# Modélisation

Une bonne prédiction est une probabilité calibrée hors échantillon, pas un taux de réussite isolé.

## Features

À l'instant T, seules les rencontres strictement antérieures existent. Le score du match courant n'entre pas dans `MODEL_FEATURE_COLUMNS`.

Fenêtres 5 et 10 : points, buts, différence, splits domicile et extérieur, tirs, tirs cadrés, possession, corners, cartons, xG si la colonne existe, repos, congestion, rang reconstruit, confrontations pondérées `exp(-jours/365)`, absences si elles ont été importées.

Une statistique absente reste nulle, avec un drapeau `has_xg`, `has_possession` ou `has_injuries`. Elle n'est pas inventée.

Les cotes du match sont stockées comme features de marché. Elles ne servent pas d'entrées au classifieur (`USE_MARKET_FEATURES_IN_MODEL=false`), afin que l'edge ne compare pas une cote à elle-même.

## Modèles

1. Dixon-Coles : attaque, défense, avantage domicile, `rho`, décroissance temporelle `xi=0.003`.
2. Régression logistique multinomiale, imputation médiane, standardisation.
3. XGBoost `multi:softprob`.
4. Ensemble : poids positifs sommant à 1, optimisés par log loss sur la fenêtre de validation. Si la fenêtre est trop courte, repli sur l'inverse du log loss de validation.

Découpage temporel 70 % / 15 % / 15 %. Pas de split aléatoire.

## Calibration

Platt si la validation a moins de 40 lignes, isotonic sinon. Les probabilités brutes et calibrées sont toutes les deux conservées.

Métriques : Brier multiclasse, log loss, ECE sur la confiance de la classe prédite.

## Incertitude

Si le club le plus court a moins de `MIN_HISTORY_MATCHES` matchs antérieurs, l'état est `INSUFFICIENT_DATA` et la distribution est rétractée vers le prior uniforme 1/3.

`confidence = 1 - H(p) / log(3)`.

## Qualité du signal

Score 0–100, pas une probabilité de gain.

- qualité des données 0.20
- profondeur d'historique `min(n, 30) / 30` 0.15
- calibration `1 - min(ECE, 1)`, ou 0.5 si l'ECE est inconnue 0.15
- accord des modèles, ou 0.5 si inconnu 0.10
- edge positif plafonné à 0.15 0.10
- EV positive plafonnée à 0.20 0.10
- qualité de marché (nombre de books et dispersion) 0.10
- confiance de la distribution 0.10

## Explications

Poisson : contributions d'attaque, de défense et d'avantage domicile issues des paramètres ajustés.

Logistique : coefficient fois valeur standardisée.

XGBoost : SHAP TreeExplainer. En cas d'échec, la méthode est `unavailable` et la liste est vide.

## Filtre

`EV = p * cote - 1`. Edge = probabilité modèle − probabilité marché après retrait de marge (Shin par défaut).

`SIGNAL` exige l'historique minimum, la confiance minimum, un edge ≥ `MIN_EDGE` et une EV ≥ `MIN_EV`.
