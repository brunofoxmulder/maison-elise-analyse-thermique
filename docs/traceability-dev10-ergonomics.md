# Dev.10 — Ergonomie Assist et restitution

## Expression de besoin validée

Usage quotidien : la demande vocale **« Analyse heure »** doit suffire.

Réponse Assist courte, en quelques phrases et dans cet ordre :
1. constat ;
2. analyse prudente ;
3. préconisation ;
4. à venir, uniquement dans l’horizon réellement disponible.

Une notification détaillée est publiée automatiquement lorsque `notification_service` est configuré dans l’App. Le rapport de notification est une compilation déterministe des faits et ne remplace pas l’interprétation du LLM.

Après une analyse, **« donne-moi le détail »** doit développer oralement la même analyse. Le client doit réutiliser le résultat déjà présent ; si un nouvel appel MCP est nécessaire, `mode=last_result` restitue le cache sans recalcul et sans répéter la notification.

## Demandes particulières conservées

La simplification du raccourci ne réduit pas la souplesse des périodes :
- « aujourd’hui entre 13 h et 17 h » → `mode=relative_day`, `day=today`, heures locales ;
- « hier entre 8 h et 15 h » → `mode=relative_day`, `day=yesterday` ;
- date historique absolue → `mode=explicit` avec timestamps ISO 8601 ;
- comparaisons existantes restent disponibles.

Les mots `today` et `yesterday` sont résolus par l’horloge de l’App en `Europe/Paris`. Le LLM ne fabrique donc plus la date absolue pour ces périodes relatives.

## Corrections ergonomiques issues de la recette dev.9

- Convention volet explicitée dans le contrat : **0 % = fermé, 100 % = ouvert**.
- `forecast_h4` est le seul horizon prospectif fourni par le profil H−2 ; le LLM ne doit pas parler de « demain » ni d’un instant postérieur au dernier point H+4 sans demande explicite d’une autre prévision.
- La réponse courte ne doit pas exposer les termes internes `H−2`, `current_h2`, `expertise_h2` ni des titres Markdown.

## Notification Home Assistant

La destination est configurable via l’option App `notification_service` au format `notify.<service>`. Aucun service personnel n’est codé en dur dans le dépôt.

L’App appelle uniquement le domaine `notify` pour la restitution ; aucun service de commande d’équipement n’est ajouté. Les données thermiques et le moteur restent en lecture seule. Les appels répétés sur le même dernier relevé H−2 sont dédupliqués afin d’éviter les notifications en double.

## Périmètre hors dev.10

- pas de SMTP embarqué ;
- pas de modification Investigator, Élise Why, Maison Élise ou HA-MCP Server ;
- pas de commande d’équipement ;
- le rapport mail expert complet reste un chantier distinct.
