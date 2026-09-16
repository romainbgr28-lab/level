"""Contexte compact remis au coach conversationnel avant chaque message.

Objectif (spécification V0 section 7) : quand l'utilisateur écrit « je fais quoi
aujourd'hui ? », LEVEL doit déjà savoir qui il est, ce que prévoit son programme et ce qu'il
a réellement fait — sans pour autant recevoir toute la base de données.

Ce module est PUR : il reçoit des dicts déjà lus en base (par ``coach_actions``) et renvoie
un dict, puis un texte court destiné au prompt. Aucune I/O, aucun appel IA, aucun import de
FastAPI ni de SQLAlchemy — donc testable seul (test_coach_contexte.py).

Deux règles tenues ici :
- **compacité** : on ne met que ce qui sert à décider ou à répondre. L'historique est borné
  (``MAX_SEANCES_HISTORIQUE``), les exercices d'une séance passée sont résumés, pas détaillés
  série par série. Le détail reste accessible au coach en appelant une action
  (``get_progression_exercice``, ``get_historique``), justement pour qu'il n'ait pas à tout
  recevoir d'avance ;
- **jamais d'invention** : une information absente est absente du contexte (clé à ``None``),
  elle n'est pas remplacée par une valeur plausible. Le prompt dit explicitement au modèle
  qu'une donnée manquante se demande ou se récupère par une action.
"""

from datetime import date
from typing import Any, Optional

# Nombre de séances passées résumées dans le contexte. Assez pour que le coach parle de la
# semaine écoulée sans relire toute la base ; au-delà, il doit appeler une action.
MAX_SEANCES_HISTORIQUE = 5

LABELS_OBJECTIFS = {
    "force": "force",
    "esthetique_hypertrophie": "esthétique / hypertrophie",
    "perte_de_gras": "perte de gras",
    "performance_sport_pratique": "performance dans le sport pratiqué",
    "endurance": "endurance",
    "discipline_mentale": "discipline mentale",
}

LABELS_STATUT_JOUR = {
    "aucun_profil": "aucun profil enregistré",
    "aucun_programme": "aucun programme actif",
    "match": "jour de match",
    "repos": "jour de repos",
    "indisponible": "jour non disponible (déclaré indisponible au profil)",
    "seance": "jour de séance",
}


def _resume_exercice_prevu(item: dict[str, Any]) -> str:
    nom = item.get("nom") or f"exercice #{item.get('exercice_id')}"
    series = item.get("series")
    reps = item.get("repetitions")
    charge = item.get("charge_indicative")
    morceaux = [nom]
    if series and reps:
        morceaux.append(f"{series}×{reps}")
    if charge:
        morceaux.append(str(charge))
    return " — ".join(morceaux)


def _resume_seance_passee(entry: dict[str, Any]) -> str:
    morceaux = [f"{entry.get('date')}", str(entry.get("type_seance") or "séance")]
    if entry.get("rpe") is not None:
        morceaux.append(f"RPE {entry['rpe']}")
    if entry.get("pourcentage_complete") is not None:
        morceaux.append(f"{entry['pourcentage_complete']}% complété")
    noms = [
        (ex.get("nom") or f"#{ex.get('exercice_id')}")
        for ex in (entry.get("exercices_realises") or [])
        if isinstance(ex, dict)
    ]
    if noms:
        morceaux.append("exercices : " + ", ".join(noms))
    return " · ".join(morceaux)


def construire_contexte(
    profil: Optional[dict[str, Any]],
    programme: Optional[dict[str, Any]],
    contexte_jour: dict[str, Any],
    seance_du_jour: Optional[dict[str, Any]],
    historique_recent: list[dict[str, Any]],
    contextes_signales: list[dict[str, Any]],
    aujourdhui: date,
) -> dict[str, Any]:
    """Snapshot structuré de ce que LEVEL sait de l'utilisateur, à cet instant.

    ``contexte_jour`` est le résultat de ``contexte_jour.construire_contexte_jour`` : la
    décision du jour (match / repos / séance / indisponible) n'est pas recalculée ici, elle
    est reprise telle quelle du moteur qui en est propriétaire.
    """
    contexte: dict[str, Any] = {
        "date": aujourdhui.isoformat(),
        "jour_label": contexte_jour.get("jour_label"),
        "profil": None,
        "objectifs": [],
        "disponibilites": None,
        "materiel": None,
        "calendrier_matchs": None,
        "programme": None,
        "jour": {
            "statut": contexte_jour.get("statut"),
            "statut_label": LABELS_STATUT_JOUR.get(contexte_jour.get("statut"), contexte_jour.get("statut")),
            "type_seance_prevu": contexte_jour.get("type_seance_prevu"),
            "phase_calendaire": contexte_jour.get("phase_calendaire"),
            "prochaine_seance": contexte_jour.get("prochaine_seance"),
        },
        "seance_du_jour": None,
        "historique_recent": [],
        "contraintes_actives": [],
    }

    if profil:
        contexte["profil"] = {
            "age": profil.get("age"),
            "taille_cm": profil.get("taille_cm"),
            "poids_kg": profil.get("poids_kg"),
            "niveau_physique": profil.get("niveau_physique"),
            "sport": (profil.get("contexte_sportif") or {}).get("sport"),
            "poste": (profil.get("contexte_sportif") or {}).get("poste"),
            # Fréquence du SPORT pratiqué, jamais le nombre de séances LEVEL : les deux sont
            # distincts (voir user_model_v2.py) et les confondre casserait la structure
            # hebdomadaire. Le nom de clé le rappelle explicitement au modèle.
            "frequence_hebdo_sport": (profil.get("contexte_sportif") or {}).get("frequence_hebdo"),
        }
        contexte["objectifs"] = [
            {
                "theme": o.get("theme"),
                "label": LABELS_OBJECTIFS.get(o.get("theme"), o.get("theme")),
                "rang": o.get("rang"),
            }
            for o in (profil.get("objectifs_v2") or [])
        ]
        contexte["disponibilites"] = profil.get("disponibilites")
        contexte["materiel"] = profil.get("materiel")
        contexte["calendrier_matchs"] = profil.get("calendrier_matchs")

    if programme:
        contexte["programme"] = {
            "semaine_courante": contexte_jour.get("semaine_programme"),
            "duree_semaines": programme.get("duree_semaines"),
            "phase_nom": contexte_jour.get("phase_nom"),
            "phase_description": contexte_jour.get("phase_description"),
            "gabarit_hebdomadaire": programme.get("gabarit_hebdomadaire"),
        }

    if seance_du_jour:
        contexte["seance_du_jour"] = {
            "id": seance_du_jour.get("id"),
            "nom": seance_du_jour.get("nom"),
            "statut": seance_du_jour.get("statut"),
            "duree_prevue_min": seance_du_jour.get("duree_prevue"),
            "exercices": [
                _resume_exercice_prevu(item)
                for item in (seance_du_jour.get("exercices") or [])
                if isinstance(item, dict)
            ],
        }

    contexte["historique_recent"] = [
        _resume_seance_passee(entry) for entry in historique_recent[:MAX_SEANCES_HISTORIQUE]
    ]

    contexte["contraintes_actives"] = [
        {
            "type": c.get("type"),
            "valeur": c.get("valeur"),
            "details": c.get("details"),
            "depuis": c.get("date_debut"),
        }
        for c in contextes_signales
    ]

    return contexte


def _ligne(libelle: str, valeur: Any) -> Optional[str]:
    if valeur is None or valeur == [] or valeur == {} or valeur == "":
        return None
    return f"{libelle} : {valeur}"


def formater_pour_prompt(contexte: dict[str, Any]) -> str:
    """Rend le contexte en texte court injecté dans le prompt système.

    Une section absente n'est pas écrite du tout (plutôt qu'écrite vide) : le modèle voit
    littéralement ce que LEVEL sait, et rien qui ressemble à une donnée qu'il pourrait
    compléter de lui-même.
    """
    lignes: list[str] = [f"Nous sommes le {contexte['date']} ({contexte.get('jour_label') or '?'})."]

    profil = contexte.get("profil")
    if profil:
        details = [
            f"{profil['age']} ans" if profil.get("age") else None,
            f"{profil['taille_cm']} cm" if profil.get("taille_cm") else None,
            f"{profil['poids_kg']} kg" if profil.get("poids_kg") else None,
            f"niveau {profil['niveau_physique']}" if profil.get("niveau_physique") else None,
        ]
        details = [d for d in details if d]
        lignes.append("PROFIL : " + ", ".join(details) if details else "PROFIL : renseigné")
        if profil.get("sport"):
            sport = profil["sport"]
            if profil.get("poste"):
                sport += f" ({profil['poste']})"
            if profil.get("frequence_hebdo_sport"):
                sport += f", {profil['frequence_hebdo_sport']}×/semaine"
            lignes.append(f"SPORT PRATIQUÉ : {sport}")
    else:
        lignes.append("PROFIL : aucun profil enregistré — l'onboarding n'est pas terminé.")

    objectifs = contexte.get("objectifs") or []
    if objectifs:
        ordonnes = sorted(objectifs, key=lambda o: o.get("rang") or 99)
        lignes.append(
            "OBJECTIFS (par priorité) : "
            + ", ".join(f"{o['rang']}. {o['label']}" for o in ordonnes)
        )

    for libelle, cle in (("MATÉRIEL", "materiel"), ("DISPONIBILITÉS (min/jour)", "disponibilites")):
        ligne = _ligne(libelle, contexte.get(cle))
        if ligne:
            lignes.append(ligne)

    calendrier = contexte.get("calendrier_matchs") or {}
    if calendrier.get("jour_habituel"):
        lignes.append(f"MATCH HABITUEL : {calendrier['jour_habituel']}")
    if calendrier.get("exceptions"):
        lignes.append(f"EXCEPTIONS DE MATCH : {calendrier['exceptions']}")

    programme = contexte.get("programme")
    if programme:
        entete = f"PROGRAMME ACTIF : semaine {programme.get('semaine_courante')}/{programme.get('duree_semaines')}"
        if programme.get("phase_nom"):
            entete += f" — phase « {programme['phase_nom']} »"
        lignes.append(entete)
        if programme.get("gabarit_hebdomadaire"):
            lignes.append(f"SEMAINE TYPE : {programme['gabarit_hebdomadaire']}")
    else:
        lignes.append("PROGRAMME ACTIF : aucun.")

    jour = contexte.get("jour") or {}
    ligne_jour = f"AUJOURD'HUI : {jour.get('statut_label')}"
    if jour.get("type_seance_prevu"):
        ligne_jour += f", type prévu « {jour['type_seance_prevu']} »"
    lignes.append(ligne_jour)
    if jour.get("prochaine_seance"):
        prochaine = jour["prochaine_seance"]
        lignes.append(
            f"PROCHAINE SÉANCE PRÉVUE : {prochaine.get('jour_label')} {prochaine.get('date')} "
            f"({prochaine.get('type_seance_prevu')})"
        )

    seance = contexte.get("seance_du_jour")
    if seance:
        lignes.append(
            f"SÉANCE DU JOUR (id={seance['id']}, statut={seance['statut']}, "
            f"{seance.get('duree_prevue_min') or '?'} min) : {seance['nom']}"
        )
        for exercice in seance.get("exercices") or []:
            lignes.append(f"  • {exercice}")
    else:
        lignes.append("SÉANCE DU JOUR : aucune séance encore générée pour aujourd'hui.")

    historique = contexte.get("historique_recent") or []
    if historique:
        lignes.append("SÉANCES RÉCENTES :")
        lignes.extend(f"  • {h}" for h in historique)
    else:
        lignes.append("SÉANCES RÉCENTES : aucune séance terminée pour l'instant.")

    contraintes = contexte.get("contraintes_actives") or []
    if contraintes:
        lignes.append("CONTRAINTES ACTIVES SIGNALÉES :")
        for c in contraintes:
            detail = f" ({c['details']})" if c.get("details") else ""
            lignes.append(f"  • {c['type']} : {c.get('valeur') or '—'}{detail}, depuis le {c.get('depuis')}")

    return "\n".join(lignes)
