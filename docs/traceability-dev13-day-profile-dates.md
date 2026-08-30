# Dev.13 — profil Jour et dates déterministes

Date : 30/08/2026

## Besoin fonctionnel

Étendre la chaîne validée dev.12 au profil Jour sans modifier le moteur horaire : **1 calcul App → 1 expertise LLM → 2 restitutions de la même expertise** (synthèse Assist + rapport complet en notification persistante Home Assistant).

Règles de date validées terrain :

- « Analyse jour » = journée locale en cours, de minuit à maintenant ;
- « hier » = journée civile précédente complète ;
- une date sans année, ex. « 20 août », utilise déterministiquement l'année locale en cours ;
- une année antérieure n'est utilisée que si l'utilisateur la dit explicitement ;
- les périodes historiques futures sont refusées ;
- une fenêtre intra-journée (ex. aujourd'hui 13 h–17 h) reste supportée sans être forcée dans le profil Jour complet.

## Compatibilité MCP

Pour éviter d'ajouter un quatrième outil et limiter le risque de découverte côté client MCP natif HA, le contrat conserve les trois outils dev.12 :

1. `AnalyseThermique`
2. `PublierRapportThermique`
3. `DernierRapportThermique`

Le mode MCP existant `relative_day` est étendu : le champ `day` accepte `today`, `yesterday`, `DD-MM`, `DD-MM-YYYY` ou `YYYY-MM-DD`. Lorsque `start_time` et `end_time` sont absents, il s'agit d'un profil Jour complet. L'absence d'année est donc conservée jusqu'à l'App : le LLM ne doit pas fabriquer une année.

## Deux températures demandées par jour

Le profil Jour expose un `setpoint_profiles` déterministe construit uniquement à partir de la colonne enregistrée `Consigne` et du `HVAC_mode` :

- séparation stricte froid (`cool`) / chauffage (`heat`) ;
- toutes les consignes observées sont conservées ;
- les deux consignes dominantes par durée sont mises en évidence lorsqu'elles existent ;
- pour chaque consigne : durée, plages horaires, température intérieure moyenne, écart moyen intérieur-consigne, erreur absolue moyenne, part du temps dans la bande descriptive ±0,5 °C et actions HVAC ;
- la bande ±0,5 °C reste une métrique descriptive de suivi, jamais un seuil de confort ;
- aucune consigne (19, 21 ou autre) n'est codée en dur.

## Rapport expert Jour

`PublierRapportThermique` reçoit deux paramètres optionnels supplémentaires :

- `profile=day` ;
- `setpoints` : section rédigée par le LLM à partir de `setpoint_profiles`.

La notification HA Jour est structurée au minimum : Situation / Consignes et suivi / Évolution de la journée / Énergie Daikin / Explications prudentes / Bilan et recommandations Volets-Aération-Daikin / Vigilance / Conclusion NORMAL|VIGILANCE|ALERTE.

Pour une journée historique terminée, le LLM ne doit pas inventer de préconisation pour aujourd'hui ni de météo future sauf demande explicite.

Les garde-fous dev.12 restent valables : convention volets 0 %=fermé / 100 %=ouvert, RH seule insuffisante pour l'aération, température Daikin terrasse = microclimat seulement, corrélation ≠ causalité.

## Gouvernance

- branche `dev13-day-profile-dates` depuis `main` dev.12 ;
- version `0.1.0-dev.13` ;
- même moteur thermique générique ; ajout d'un enrichissement déterministe de consignes ;
- même notification `persistent_notification.create` après expertise ;
- aucune commande d'équipement ;
- aucun changement Investigator / Élise Why / Maison Élise / HA-MCP Server ;
- aucun changement Home Assistant pendant le développement.
