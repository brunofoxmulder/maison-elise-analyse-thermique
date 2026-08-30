# Contrat d’expertise H−2 — v1

## Expression de besoin

Le profil H−2 répond à la question opérationnelle suivante :

> Que s’est-il passé pendant la dernière heure, est-ce mieux ou moins bien que pendant l’heure précédente, et que faut-il surveiller ou conseiller pour les prochaines heures ?

La dernière heure est toujours le sujet principal. L’heure précédente est une référence immédiate, pas une période équivalente à résumer au même niveau.

## Frontière d’architecture

L’App reste déterministe, en lecture seule et non prescriptive. Elle récupère, nettoie, calcule, compare et structure les faits. Elle ne décide pas qu’il faut ouvrir, fermer, chauffer ou refroidir.

L’IA reçoit les faits structurés et, avec son prompt métier versionné `h2-expert-v1`, produit l’explication et le conseil. Elle ne recalcule pas les chiffres et ne transforme pas une corrélation en causalité certaine.

## Données et indicateurs remis à l’IA pour chaque heure

- analyse thermique existante complète ;
- faits thermiques prioritaires existants ;
- tendance de température intérieure : début, fin, variation et vitesse ;
- suivi de la consigne réellement active : niveaux, transitions, écart intérieur−consigne et temps dans une bande descriptive de ±0,5 °C ;
- propriétés hygrométriques dérivées : humidité absolue et point de rosée intérieur/extérieur ;
- énergie froid et chauffage « dernière heure » comme observations, sans sommer les répétitions à cinq minutes ;
- température extérieure Daikin comme microclimat terrasse, avec écart à la température extérieure fiable ;
- tous les contextes déjà calculés : HVAC, fréquence compresseur, ouvrants, soleil effectif, lux et volets.

## Règles métier fermes du contrat

1. Une moyenne de consigne sur 24 h n’est jamais une cible thermique. La température est jugée par rapport à la consigne réellement active et les changements de consigne doivent être explicités.
2. « Plus frais dehors » ne signifie pas automatiquement « il faut aérer ». La température, la teneur en eau de l’air, les ouvrants et le contexte Daikin doivent être considérés ensemble.
3. L’humidité relative seule ne permet pas de juger l’intérêt hygrométrique d’une aération. L’App fournit donc aussi l’humidité absolue et le point de rosée.
4. La température extérieure fiable reste l’unique référence météorologique observée.
5. La température extérieure Daikin décrit seulement le microclimat du groupe sur la terrasse. Elle ne prouve jamais, à elle seule, que le compresseur peine, force, est inefficace ou consomme davantage.
6. Les valeurs `Cool_energy_derniere_heure` et `Heat_energy_derniere_heure` sont des observations horaires ; elles ne doivent pas être additionnées à chaque relevé de cinq minutes.
7. L’App ne commande aucun équipement. Le conseil appartient à l’IA et doit rester prudent.

## Structure JSON `expertise_h2`

Pour une période demandée d’environ deux heures, le service ajoute :

- `profile = h2_last_hour_vs_previous_hour`
- `primary_period` = dernière heure
- `reference_period` = heure précédente
- `last_hour`
- `previous_hour`
- `comparison`
- `forecast_h4`
- `analysis_contract`

Chaque bloc horaire contient l’analyse existante et les enrichissements H−2. La comparaison fournit les deltas déterministes utiles sans produire de conclusion causale.

`analysis_contract` identifie également `prompt_version = h2-expert-v1`, rappelle que `expertise_h2` est la matière principale pour une réponse H−2 et que le `analysis` de premier niveau reste seulement l’agrégat historique des deux heures. Il contient aussi les règles de preuve, de lecture du compresseur, de prudence sur déshumidification/modulation et le format de réponse attendu : NORMAL/VIGILANCE/ALERTE, situation, évolution, explications prudentes, conseil 2–4 h, vigilance, conclusion, avec conseils Volets / Aération / Daikin.

## Météo H+4 — décision d’architecture

La prévision horaire H+4 provient de l’entité Home Assistant configurée dans l’App via `weather_entity`, par l’action native `weather.get_forecasts` appelée via l’API Core interne de Home Assistant. La valeur par défaut historique est `weather.dammarie_les_lys`, mais elle n’est pas une constante métier imposée.

Décision : ne pas créer de fournisseur météo parallèle ni recopier la logique météo dans l’App.

L’App HAOS déclare `homeassistant_api: true` et utilise le `SUPERVISOR_TOKEN` fourni par Home Assistant. Le code de dev.8 n’appelle qu’une action de lecture : `weather.get_forecasts`, ainsi que la lecture de l’état de l’entité météo pour ses unités.

**Point de sécurité à conserver dans la traçabilité :** l’autorisation `homeassistant_api` élargit techniquement la surface d’accès de l’App au Core Home Assistant, même si l’implémentation actuelle n’utilise que la météo en lecture. Cette permission doit être revue à chaque évolution et ne justifie aucun ajout d’action domotique.

La météo H+4 est facultative et non bloquante :

- si Home Assistant ou l’entité météo ne répond pas, l’analyse H−2 reste disponible ;
- l’indisponibilité est exposée dans `forecast_h4.available=false` ;
- aucune valeur manquante n’est inventée ;
- une demande H−2 historique ne reçoit pas la météo actuelle comme si elle représentait le passé ;
- le vent extérieur est seulement un contexte de potentiel d’aération, jamais une preuve de courant d’air dans le logement.

## Prompt expert et transport MCP natif

Le prompt de référence est versionné dans `docs/h2-expert-prompt-v1.md`.

Il conserve les principes historiques du Pyscript horaire et du référentiel métier clim, mais ajoute explicitement les règles validées le 30/08/2026 : consigne active, humidité absolue/point de rosée, distinction renouvellement d’air / stratégie thermique, aération pouvant aider le Daikin sans être automatiquement optimale, raisonnement été/hiver et microclimat terrasse non causal.

**Découverte de revue pré-merge :** dans Home Assistant 2026.8.3, l’intégration MCP native expose au LLM un prompt générique côté HA et la `description` des tools ; les `instructions` renvoyées lors de l’initialisation du serveur MCP ne sont pas reprises dans l’API LLM. Par conséquent, le fichier Markdown ne suffit pas à garantir le comportement terrain.

Décision dev.8 : les règles indispensables du prompt sont aussi rendues visibles à Assist/Mistral dans la `description` du tool `AnalyseThermique` et dans `analysis_contract` / les `interpretation_rule` du JSON. Le prompt long reste la source documentaire versionnée ; le contrat compact est celui effectivement transporté jusqu’au LLM par le chemin natif HA.

## Critère de recette dev.8 H−2

Le JSON doit permettre à l’IA de répondre sans invention à :

1. que s’est-il passé pendant la dernière heure ?
2. est-ce mieux, moins bien ou stable par rapport à l’heure précédente ?
3. la température évolue-t-elle de façon cohérente avec la consigne active ?
4. que montrent ensemble température, hygrométrie, HVAC, fréquence et énergie ?
5. les ouvrants, le soleil et les volets apportent-ils un contexte pertinent ?
6. la météo H+4 change-t-elle le conseil pour les prochaines heures ?
7. quelles conclusions sont des faits, observations, hypothèses ou incertitudes ?

Le LLM n’a pas à refaire les calculs.

## Hors périmètre de dev.8

- envoi de notification ou mail ;
- commandes d’équipement ;
- profils hebdomadaire et mensuel ;
- apprentissage automatique de l’efficacité de l’aération ;
- modification d’Investigator, Élise Why, Maison Élise ou HA-MCP Server.

## Traçabilité

Baseline : dev.7 terrain PASS, main `bb6d80b4cdf77b699cf89fa20c825f4088c031ec`.

Branche : `dev8-h2-expertise-contract` — PR #7 draft.

Origines fonctionnelles : Pyscript `Analyse_horaire_v5.py` V5.0.5 A+, référentiel `/config/prompts/referentiel_metier_clim.txt`, échanges et décisions du 30/08/2026.

Toute modification future du contrat H−2 ou du prompt doit être versionnée et accompagnée du motif de changement, afin de pouvoir revenir au dernier cap validé si une évolution se révèle mauvaise.
