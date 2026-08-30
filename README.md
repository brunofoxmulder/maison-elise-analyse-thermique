# Maison Élise — Analyse thermique

App HAOS de lecture seule dédiée à l’analyse thermique de Maison Cognitive.

Architecture : Google Sheets → moteur déterministe → JSON structuré → façade MCP native Home Assistant → agent conversationnel.

## État courant

- baseline terrain validée : `0.1.0-dev.7` ;
- développement en cours : `0.1.0-dev.8`, profil H−2 ;
- H−2 = dernière heure analysée en priorité, heure précédente comme référence immédiate ;
- météo H+4 lue depuis Home Assistant via `weather.get_forecasts`, facultative et non bloquante ;
- prompt expert versionné : `docs/h2-expert-prompt-v1.md`.

## Principes de sécurité et de gouvernance

- aucune commande d’équipement ;
- calculs numériques effectués par l’App, pas par le LLM ;
- température extérieure Daikin = microclimat terrasse uniquement, jamais référence météo ni preuve de difficulté compresseur ;
- l’accès `homeassistant_api` de dev.8 est utilisé uniquement pour la lecture de la météo et doit rester explicitement tracé/revu ;
- les profils horaire, hebdomadaire et mensuel sont des produits distincts.

Voir `docs/h2-expertise-contract-v1.md` pour le contrat complet.
