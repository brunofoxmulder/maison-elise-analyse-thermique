# Traçabilité dev.8 — expertise H−2

## Cap validé

Expression de besoin : analyser en profondeur la dernière heure, la comparer à l’heure précédente, expliquer prudemment puis conseiller pour les 2 à 4 prochaines heures.

Architecture : App déterministe → dossier JSON riche → IA avec prompt métier versionné. L’App ne devient pas l’intelligence et ne commande aucun équipement.

## Baseline

- dev.7 terrain PASS ;
- main de départ : `bb6d80b4cdf77b699cf89fa20c825f4088c031ec` ;
- branche : `dev8-h2-expertise-contract` ;
- PR : #7 draft.

## Décisions dev.8

### D-8.1 — dernière heure prioritaire

L’heure H−1→maintenant est le sujet. H−2→H−1 est la référence immédiate. Rejet d’une simple moyenne globale sur deux heures.

### D-8.2 — consigne active

Évaluer la température par rapport à la consigne réellement active et signaler ses transitions. Une moyenne quotidienne de consigne ne constitue pas une cible.

### D-8.3 — hygrométrie et aération

Fournir humidité relative, humidité absolue et point de rosée. « Plus frais dehors » ne déclenche pas automatiquement un conseil d’aération. L’aération peut renouveler l’air, aider thermiquement ou hygrométriquement, ou au contraire être défavorable. Le conseil appartient à l’IA.

### D-8.4 — température extérieure Daikin

Réintroduite uniquement comme microclimat terrasse. Jamais référence météo. Jamais preuve isolée que le compresseur peine, force ou surconsomme.

### D-8.5 — énergie horaire

`Cool_energy_derniere_heure` et `Heat_energy_derniere_heure` sont des observations horaires répétées dans le Sheet ; prendre la dernière observation disponible, ne jamais sommer les répétitions à cinq minutes.

### D-8.6 — météo H+4

Source : Home Assistant natif, entité configurable via `weather_entity`, action `weather.get_forecasts` en mode hourly via l’API Core interne. `weather.dammarie_les_lys` reste uniquement la valeur par défaut historique issue des Pyscripts.

Motif : réutiliser la source météo déjà gouvernée par Home Assistant, sans fournisseur parallèle.

La météo est optionnelle/non bloquante. Une analyse historique ne reçoit pas la météo actuelle comme si elle représentait le passé. Le vent extérieur est un contexte, pas une preuve de courant d’air intérieur.

### D-8.7 — nouvelle frontière de permission

`homeassistant_api: true` est nécessaire pour que l’App lise la prévision via le Core. Cela élargit techniquement la surface d’accès du conteneur. Le code dev.8 n’utilise que `weather.get_forecasts` et la lecture de l’état météo pour les unités. Cette permission doit rester explicitement revue à chaque version ; elle ne justifie aucun service d’action domotique.

### D-8.8 — prompt versionné

Prompt : `h2-expert-v1`, stocké dans `docs/h2-expert-prompt-v1.md`.

Règles : chiffres déterministes = source de vérité ; pas de recalcul LLM ; Fait/Observation/Hypothèse/Incertitude ; statut NORMAL/VIGILANCE/ALERTE ; conseils Volets/Aération/Daikin ; raisonnement été/hiver ; météo H+4 prospective seulement.

### D-8.9 — transport réel du prompt par le MCP natif HA

Découverte pendant la revue pré-merge : Home Assistant Core 2026.8.3 construit l’API LLM MCP avec un prompt générique et les tools retournés par `list_tools()`. Il reprend `tool.description`, mais ne retransmet pas les `instructions` du serveur MCP à l’agent conversationnel.

Risque : un prompt expert stocké uniquement en Markdown ou dans `FastMCP(instructions=...)` peut être correct en documentation mais ne jamais influencer Assist/Mistral.

Correction : les règles H−2 indispensables sont désormais dupliquées de façon compacte et versionnée dans la `description` de `AnalyseThermique`, dans `expertise_h2.analysis_contract` et dans les `interpretation_rule` des blocs. Le prompt long reste la source documentaire de référence ; le contrat compact est la couche réellement transportée vers le LLM.

Un test MCP vérifie que la description exposée par `list_tools()` contient les règles essentielles. Toute évolution future du prompt doit vérifier les deux couches : documentation longue + contrat runtime.

### D-8.10 — bornes horaires H−2 fidèles au Pyscript V5

Découverte pendant la revue pré-merge : la première implémentation dev.8 réutilisait les périodes génériques demi-ouvertes `[start, end)` pour chacun des deux blocs H−2. À une cadence de cinq minutes, cela pouvait donner 12 points et une variation mesurée sur 55 minutes.

Retour au code validé `Analyse_horaire_v5.py` : le Pyscript fixe `fin` au dernier relevé réel, calcule `milieu = fin - 1 h`, puis inclut les deux bornes de chaque heure (`debut <= ts <= milieu` et `milieu <= ts <= fin`). Le point H−1 est donc partagé. Une heure complète contient 13 points et 12 intervalles de cinq minutes = 60 minutes.

Correction dev.8 : cette sémantique est restaurée **uniquement pour `expertise_h2`**, sans changer les périodes arbitraires du moteur. H−2 s’ancre sur le dernier relevé réellement disponible à ou avant la fin demandée. `data_window` expose le dernier relevé, le retard par rapport à la fin demandée, la présence du point H−1 partagé et les nombres de relevés par heure. Si le dernier relevé a plus de 15 minutes de retard, le contrat impose de signaler une incertitude de fraîcheur.

Tests ajoutés : 25 points H−2, 13 points par heure, 60 minutes de couverture et de cooling par heure, variation réellement calculée sur 60 minutes, partage du point H−1, et cas de fin demandée 20 minutes après le dernier relevé.

## Corrections de cohérence découvertes pendant la dev

1. `config.yaml` était déjà passé en `0.1.0-dev.8`, mais `app/api.py` et le `Dockerfile` étaient restés en dev.7. Les deux ont été alignés sur dev.8 avant toute tentative de merge ou déploiement.
2. La documentation météo mentionnait encore `weather.dammarie_les_lys` comme source fixe alors que la dev.8 rend déjà `weather_entity` configurable. La documentation a été alignée : cette entité n’est qu’une valeur par défaut.
3. Le prompt expert était initialement versionné mais pas garanti d’être visible par Assist/Mistral à travers le MCP natif. Revue du code officiel HA 2026.8.3 puis correction D-8.9 avant merge.
4. Le premier découpage H−2 perdait une borne de chaque heure par rapport au Pyscript validé. Relecture du code historique puis correction D-8.10 avant merge.

## Diffusion future

- l’adresse mail historique issue des Pyscripts n’est jamais publiée ni codée en dur dans GitHub ;
- pour hebdo/mensuel, privilégier une cible de notification/mail Home Assistant configurable ;
- l’ancien `notify.maison_cognitive` / SMTP reste une référence historique à réévaluer selon les règles Home Assistant au moment du branchement de la diffusion.

## Hors périmètre

- aucune installation/mise à jour Home Assistant pendant le développement ;
- aucun appel Mistral de validation pendant les tests unitaires ;
- aucune notification/mail ;
- aucun profil hebdomadaire ou mensuel ;
- aucune modification d’Investigator, Élise Why, Maison Élise ou HA-MCP Server.

## Règle de reprise

Si une évolution future dégrade le résultat ou complexifie l’architecture, revenir à ce document, au contrat `h2-expertise-contract-v1` et au dernier SHA/PR terrain validé. Une mauvaise direction doit être documentée, pas effacée silencieusement.
