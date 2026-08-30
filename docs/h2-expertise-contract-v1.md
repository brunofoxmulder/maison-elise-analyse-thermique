# Contrat d’expertise H−2 — v1

## Expression de besoin

Le profil H−2 répond à la question opérationnelle suivante :

> Que s’est-il passé pendant la dernière heure, est-ce mieux ou moins bien que pendant l’heure précédente, et que faut-il surveiller ou conseiller pour les prochaines heures ?

La dernière heure est toujours le sujet principal. L’heure précédente est une référence immédiate, pas une période équivalente à résumer au même niveau.

## Frontière d’architecture

L’App reste déterministe, en lecture seule et non prescriptive. Elle récupère, nettoie, calcule, compare et structure les faits. Elle ne décide pas qu’il faut ouvrir, fermer, chauffer ou refroidir.

L’IA reçoit les faits structurés et, avec son prompt métier, produit l’explication et le conseil. Elle ne recalcule pas les chiffres et ne transforme pas une corrélation en causalité certaine.

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

## Structure JSON ajoutée

Pour une période demandée d’environ deux heures, le service ajoute `expertise_h2` :

- `profile = h2_last_hour_vs_previous_hour`
- `primary_period` = dernière heure
- `reference_period` = heure précédente
- `last_hour`
- `previous_hour`
- `comparison`
- `analysis_contract`

Chaque bloc horaire contient l’analyse existante et les enrichissements H−2. La comparaison fournit les deltas déterministes utiles sans produire de conclusion causale.

## Hors périmètre de cette première dev.8

La météo prévisionnelle H+4 n’est pas encore ajoutée à l’App. Elle constitue l’étape suivante du profil horaire, après validation de ce contrat sur les données déterministes existantes.

Les profils hebdomadaire et mensuel restent distincts et seront construits après validation du H−2.
