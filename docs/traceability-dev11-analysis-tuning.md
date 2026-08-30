# Dev.11 — réglages d’analyse + notification Home Assistant

## Origine terrain — 30/08/2026

Après dev.10, le client MCP natif Home Assistant a été rechargé et « Analyse heure » a de nouveau appelé correctement `AnalyseThermique`.

Deux écarts ergonomiques/métier ont été observés :

1. la réponse courte a cité 115 min de refroidissement, valeur issue de l’agrégat des deux heures, alors que la dernière heure est le sujet principal ;
2. la synthèse a conseillé de « maintenir les volets fermés » alors que le détail identifiait correctement les volets à 100 % = ouverts.

Bruno a aussi précisé que « notification » signifie **notification persistante dans Home Assistant**, pas push téléphone.

## Décisions dev.11

- Le moteur thermique et les calculs H−2 ne sont pas modifiés.
- Ajout d’un bloc déterministe `assist_brief_facts` : seule source factuelle autorisée pour la réponse Assist courte quand il est présent.
- `assist_brief_facts` ne contient que les métriques de la dernière heure ; l’heure précédente n’apparaît que comme référence de tendance/comparaison.
- Les agrégats top-level sur deux heures sont interdits dans la synthèse courte.
- Convention volet explicitée dans le brief : 0 % = fermé, 100 % = ouvert ; état textuel calculé (`closed`, `open`, `partially_open`).
- Une recommandation volets n’est permise que si les faits d’exposition solaire effective la justifient ; aucune recommandation n’est obligatoire.
- Température extérieure = contexte, pas cause certaine du fonctionnement Daikin.
- L’humidité relative seule ne justifie ni aération ni déshumidification ; utiliser aussi température et humidité absolue.
- `forecast_h4` reste le seul horizon prospectif du profil horaire.
- Le rapport détaillé est publié automatiquement via `persistent_notification.create` dans Home Assistant.
- Identifiant stable : `maison_elise_analyse_thermique`, afin de mettre à jour une notification courante au lieu d’empiler des rapports.
- L’ancien champ `notification_service` est conservé provisoirement dans le schéma HAOS pour compatibilité de mise à jour, mais dev.11 ne l’utilise plus.
- « donne-moi le détail », « donne plus de détails » et « détaille » réutilisent la dernière analyse ; aucune notification supplémentaire.

## Sécurité / périmètre

- App déterministe ; aucune commande d’équipement.
- Seul service HA appelé pour la restitution : `persistent_notification.create`.
- Aucun changement Investigator, Élise Why, Maison Élise ou HA-MCP Server.
- Aucun changement Home Assistant effectué pendant le développement de dev.11.

## Validation attendue

1. CI complète ;
2. revue du schéma MCP et de `assist_brief_facts` ;
3. après validation Bruno et merge : mise à jour HAOS ;
4. rechargement du client MCP natif Home Assistant après la mise à jour du tool ;
5. recette terrain : `Analyse heure` → synthèse courte cohérente + notification persistante HA → `Donne plus de détails` sans nouveau calcul/notification.
