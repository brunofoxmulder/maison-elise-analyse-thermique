# Maison Élise — Analyse thermique

Dépôt public de distribution de l'App Home Assistant OS de validation parallèle.

## Périmètre

- moteur thermique déterministe en lecture seule ;
- lecture de l'onglet Google Sheets `Confort thermique` ;
- API `/health`, `/analyse` et `/analyse/natural` ;
- aucune commande Home Assistant ;
- démarrage manuel ;
- architecture `amd64` uniquement pour cette phase de test.

Le contrat de formulation LLM du dépôt privé Maison Cognitive n'est pas nécessaire au benchmark HAOS et n'est volontairement pas distribué ici. Cette App sert d'abord à valider le moteur déterministe contre les données réelles.

## Installation

Ajouter ce dépôt dans le Store des Apps Home Assistant :

`https://github.com/brunofoxmulder/maison-elise-analyse-thermique`

Puis installer **Maison Élise — Analyse thermique**.

Avant le premier démarrage, renseigner dans la configuration de l'App :

- `service_account_file` : chemin local du fichier de compte de service Google déjà présent dans Home Assistant ;
- `spreadsheet_id` : identifiant du classeur contenant `Confort thermique` ;
- `worksheet_name` : `Confort thermique` ;
- `timezone` : `Europe/Paris`.

L'App monte la configuration Home Assistant en lecture seule et n'écrit pas dans Home Assistant.
