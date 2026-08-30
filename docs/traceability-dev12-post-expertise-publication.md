# Dev.12 — expertise puis publication

Date : 30/08/2026

## Besoin fonctionnel confirmé

Le critère de réussite du profil horaire est au minimum l'équivalence avec le Pyscript historique : Python/App calcule les faits, l'agent LLM réalise l'expertise, puis le rapport expert est publié. Lorsque l'agent historique Google était indisponible, le Pyscript ne produisait que quelques chiffres : ce comportement confirme que l'expertise appartenait bien au LLM et non au code déterministe.

La réponse courte ne doit jamais être produite avant l'expertise. Contrat retenu : **1 calcul App → 1 expertise LLM → 2 restitutions du même résultat** : synthèse courte Assist + rapport complet Home Assistant.

## Architecture dev.12

1. `AnalyseThermique`
   - calcule uniquement le dossier déterministe ;
   - ne publie plus de notification brute ;
   - renvoie un `analysis_id` lié à la dernière analyse ;
   - pour `current_h2`, demande ensuite une expertise unique puis `PublierRapportThermique`.

2. `PublierRapportThermique`
   - exige le même `analysis_id` ;
   - reçoit dans un seul appel la synthèse courte et toutes les sections issues de la même expertise ;
   - refuse un rapport qui ne correspond pas à la dernière analyse ;
   - publie le rapport complet via `persistent_notification.create` ;
   - mémorise exactement le rapport expert ;
   - renvoie `short_response`, utilisé ensuite comme réponse Assist.

3. `DernierRapportThermique`
   - sert uniquement aux demandes « plus de détails » ;
   - restitue le dernier rapport expert mémorisé ;
   - aucun nouveau calcul, aucune nouvelle expertise, aucune nouvelle notification.

## Structure minimale du rapport expert horaire

Référence éditoriale : rapport horaire Pyscript validé terrain.

- Situation
- Évolution par rapport à l'heure précédente
- Énergie Daikin
- Explications prudentes
- Conseil pour les 2 à 4 prochaines heures
  - Volets
  - Aération
  - Daikin
  - À venir H+4
- Points de vigilance
- Conclusion avec statut NORMAL / VIGILANCE / ALERTE

La qualité minimale demandée est « au moins équivalente au rapport horaire historique Pyscript rédigé par l'agent », tout en conservant les garde-fous plus récents : 0 %=volet fermé / 100 %=ouvert, RH seule insuffisante pour l'aération, extérieur non causal seul, température Daikin = microclimat terrasse, H+4 seul horizon prospectif, distinction Fait / Observation / Hypothèse / Incertitude.

## Gouvernance

- App toujours déterministe pour les données et calculs ; aucune expertise métier codée dans l'App.
- Le LLM ne recalcule aucun chiffre.
- Seul write HA : restitution via `persistent_notification.create` ; aucune commande d'équipement.
- Aucun changement Home Assistant pendant le développement dev.12.
- Aucun changement Investigator / Élise Why / Maison Élise / HA-MCP Server.
- Version : `0.1.0-dev.12`.
