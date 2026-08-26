"""Moteur de décision coaching (User Model V2 -> stratégie déterministe).

Objectif : inverser le flux USER MODEL -> MISTRAL en USER MODEL -> MOTEUR DE
DÉCISION DÉTERMINISTE -> STRATÉGIE -> MISTRAL. Ce module ne fait AUCUN appel
IA : il combine les données structurées du profil (objectifs_v2, contexte_sportif,
disponibilites, niveau_effectif), l'historique et le calendrier en une décision
de coaching structurée (`DecisionCoaching`), traçable (chaque choix porte une
raison textuelle dans `raisons`).

Il ne duplique jamais la logique déjà présente ailleurs : il appelle
regles_seance.generer_recommandation (phase calendaire, type de séance, garde-
fous, ajustement de charge), duree_seance (contraintes de temps) et
user_model_v2 (objectifs hiérarchisés, disponibilités) plutôt que de
réimplémenter ces règles.

Fonction pure, indépendante de FastAPI/SQLAlchemy : prend des dicts en entrée,
retourne un dataclass. Ne lève jamais : à défaut de donnée, produit une
décision plus pauvre mais toujours exploitable (voir `DecisionCoaching`),
pour rester strictement additif au flux existant (main.py doit pouvoir
continuer sans lui en cas de souci).
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

import duree_seance
import regles_seance
import user_model_v2


@dataclass
class DecisionCoaching:
    """Sortie structurée du moteur de décision, injectée dans le prompt Mistral
    comme "stratégie de coaching" avant que Mistral ne concrétise la séance.

    - objectifs_prioritaires : thèmes V2 triés par rang (le plus prioritaire d'abord).
    - qualites_prioritaires : qualités physiques/priorités liées au poste/sport
      (regles_seance.obtenir_priorites_poste), jamais hardcodées football.
    - type_seance_recommande : type de séance déterminé par le moteur de règles
      (regles_seance.generer_recommandation), déjà arbitré phase calendaire >
      gabarit programme > heuristique de repli.
    - focus : phrase courte de synthèse (objectif principal + type de séance),
      utile comme titre de section dans le prompt.
    - niveau_effectif : sous-ensemble pertinent du niveau effectif par qualité
      physique (déclaré recalibré par l'observé, voir user_model_v2).
    - contraintes : liste de contraintes concrètes à respecter (temps dispo,
      matériel, zones à exclure, intensité max) — jamais des suggestions.
    - ajustements : ajustements relatifs de charge/volume (%) par rapport à la
      dernière séance de ce type (regles_seance.calculer_ajustement_charge).
    - raisons : traçabilité complète (pourquoi ce type de séance, cet
      ajustement, ces contraintes) — utile en debug et à injecter telle quelle
      dans le prompt pour que Mistral comprenne le contexte sans le réinventer.
    - recommandation_brute : la recommandation regles_seance.generer_recommandation
      complète (non retravaillée), conservée pour les appelants qui en ont
      encore besoin telle quelle (rétro-compatibilité du flux existant).
    """

    objectifs_prioritaires: list[str] = field(default_factory=list)
    qualites_prioritaires: list[str] = field(default_factory=list)
    type_seance_recommande: str = "force"
    focus: str = ""
    niveau_effectif: dict[str, float] = field(default_factory=dict)
    contraintes: list[str] = field(default_factory=list)
    ajustements: dict[str, float] = field(default_factory=dict)
    raisons: list[str] = field(default_factory=list)
    recommandation_brute: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "objectifs_prioritaires": self.objectifs_prioritaires,
            "qualites_prioritaires": self.qualites_prioritaires,
            "type_seance_recommande": self.type_seance_recommande,
            "focus": self.focus,
            "niveau_effectif": self.niveau_effectif,
            "contraintes": self.contraintes,
            "ajustements": self.ajustements,
            "raisons": self.raisons,
        }


def _objectifs_prioritaires(profil: dict[str, Any]) -> list[str]:
    """Thèmes V2 triés par rang (1 = priorité principale). Ne réinterprète pas
    les poids/rangs : ils sont déjà calculés par user_model_v2.normaliser_objectifs
    en amont (validation du profil) ; ici on ne fait que trier/extraire."""
    objectifs_v2 = profil.get("objectifs_v2") or []
    themes = sorted(objectifs_v2, key=lambda o: o.get("rang", 99))
    return [o["theme"] for o in themes if o.get("theme")]


def _focus(objectifs_prioritaires: list[str], type_seance: str) -> str:
    if objectifs_prioritaires:
        return f"{objectifs_prioritaires[0]} via une séance de type {type_seance}"
    return f"séance de type {type_seance} (aucun objectif V2 déclaré, focus par défaut)"


def _contraintes(
    recommandation: dict[str, Any],
    disponibilites_jour_minutes: Optional[int],
    materiel: Optional[str],
) -> list[str]:
    contraintes: list[str] = []

    intensite_max = recommandation.get("intensite_max")
    if intensite_max:
        contraintes.append(f"intensité maximale autorisée : {intensite_max}")

    exclusions = recommandation.get("exclusions") or []
    if exclusions:
        contraintes.append("zones à exclure impérativement : " + ", ".join(exclusions))

    if disponibilites_jour_minutes is not None:
        contraintes.append(f"temps disponible aujourd'hui : {disponibilites_jour_minutes} min (séance déjà calibrée en conséquence)")

    if materiel:
        contraintes.append(f"matériel disponible : {materiel}")

    return contraintes


def construire_decision(
    profil: dict[str, Any],
    historique: dict[str, Any],
    etat_du_jour: dict[str, Any],
    type_seance_gabarit: Optional[str] = None,
    aujourdhui: Optional[date] = None,
    niveau_effectif: Optional[dict[str, float]] = None,
) -> DecisionCoaching:
    """Construit la décision de coaching structurée pour la séance du jour.

    Réutilise regles_seance.generer_recommandation pour tout ce qui est
    calendaire/historique/garde-fous (pas de duplication de cette logique).
    N'échoue jamais : une donnée manquante (profil incomplet, ancien format)
    produit simplement une décision plus pauvre (listes vides, valeurs par
    défaut), jamais une exception — la génération de séance existante doit
    pouvoir continuer même si l'appelant n'utilise pas cette décision.
    """
    aujourdhui = aujourdhui or date.today()

    try:
        recommandation = regles_seance.generer_recommandation(
            profil, historique, etat_du_jour, type_seance_gabarit=type_seance_gabarit, aujourdhui=aujourdhui
        )
    except Exception:
        # Filet de sécurité : le moteur de décision ne doit jamais faire
        # échouer la génération de séance existante. On retombe sur une
        # recommandation minimale neutre plutôt que de propager l'erreur.
        recommandation = {
            "phase_calendaire": "phase_normale",
            "intensite_max": "normale",
            "priorites_poste": [],
            "type_seance_suggere": type_seance_gabarit or "force",
            "ajustement_charge_pct": 0.0,
            "ajustement_volume_pct": 0.0,
            "raisons": ["Moteur de règles indisponible pour cette requête : décision de repli neutre."],
            "exclusions": [],
        }

    objectifs_prioritaires = _objectifs_prioritaires(profil)
    type_seance = recommandation.get("type_seance_suggere", "force")

    disponibilites = profil.get("disponibilites") or {}
    jour_abbrev = regles_seance.JOURS_SEMAINE_ABBREV[aujourdhui.weekday()]
    minutes_jour = user_model_v2.minutes_disponibles_jour(disponibilites, jour_abbrev)
    if minutes_jour is None:
        minutes_jour = duree_seance.parser_temps_dispo_minutes(etat_du_jour.get("temps_dispo"))

    raisons = list(recommandation.get("raisons") or [])
    if objectifs_prioritaires:
        raisons.append(
            "Objectif prioritaire déclaré : "
            + objectifs_prioritaires[0]
            + (f" (puis {', '.join(objectifs_prioritaires[1:])})" if len(objectifs_prioritaires) > 1 else "")
        )
    else:
        raisons.append("Aucun objectif V2 déclaré : aucune priorisation d'objectif appliquée.")

    return DecisionCoaching(
        objectifs_prioritaires=objectifs_prioritaires,
        qualites_prioritaires=list(recommandation.get("priorites_poste") or []),
        type_seance_recommande=type_seance,
        focus=_focus(objectifs_prioritaires, type_seance),
        niveau_effectif=niveau_effectif or {},
        contraintes=_contraintes(recommandation, minutes_jour, profil.get("materiel")),
        ajustements={
            "charge_pct": recommandation.get("ajustement_charge_pct", 0.0),
            "volume_pct": recommandation.get("ajustement_volume_pct", 0.0),
        },
        raisons=raisons,
        recommandation_brute=recommandation,
    )


def formater_section_prompt(decision: DecisionCoaching) -> str:
    """Formate la décision en section de prompt "STRATÉGIE DE COACHING", à
    injecter avant la consigne de génération concrète de la séance (voir
    main.py::_construire_prompt_generation). Texte uniquement descriptif/
    contraignant, jamais d'invitation à réinterpréter les choix ci-dessous."""
    objectifs_txt = ", ".join(decision.objectifs_prioritaires) or "aucun objectif V2 déclaré"
    qualites_txt = ", ".join(decision.qualites_prioritaires) or "aucune priorité spécifique"
    contraintes_txt = "\n".join(f"- {c}" for c in decision.contraintes) or "- aucune contrainte particulière"
    raisons_txt = "; ".join(decision.raisons) or "aucune"
    niveau_txt = ", ".join(f"{q} : {v}" for q, v in decision.niveau_effectif.items()) or "non disponible"

    return f"""STRATÉGIE DE COACHING (décidée par le moteur de décision déterministe, à respecter
impérativement — Mistral concrétise cette stratégie, il ne la redéfinit pas)
- Objectifs prioritaires (ordre décroissant) : {objectifs_txt}
- Qualités physiques prioritaires : {qualites_txt}
- Type de séance recommandé : {decision.type_seance_recommande}
- Focus de la séance : {decision.focus}
- Niveau effectif par qualité : {niveau_txt}
- Contraintes à respecter :
{contraintes_txt}
- Ajustement charge/volume par rapport à la dernière séance de ce type : charge {decision.ajustements.get('charge_pct', 0.0):+.0f}%, volume {decision.ajustements.get('volume_pct', 0.0):+.0f}%
- Raisons de cette stratégie : {raisons_txt}"""
