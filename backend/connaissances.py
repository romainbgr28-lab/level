"""Bibliothèque de connaissances théoriques (sport/football), stockée en fichier
statique (backend/data/bibliotheque_theorique_sport.json) plutôt qu'en base :
c'est un contenu de référence figé, non modifié par l'app en runtime, donc pas
besoin d'une table pour ça.

Ce module sélectionne, pour une séance donnée, un petit nombre de fiches
pertinentes (2 à 4) à injecter dans le prompt Mistral — jamais le fichier
entier, pour ne pas gonfler inutilement le prompt (voir main.py::generer_seance).
"""

import json
from pathlib import Path
from typing import Optional

_PATH = Path(__file__).parent / "data" / "bibliotheque_theorique_sport.json"
_data: Optional[dict] = None


def _load() -> dict:
    global _data
    if _data is None:
        with open(_PATH, encoding="utf-8") as f:
            _data = json.load(f)
    return _data


def get_exercices_musculation_base() -> list[dict]:
    """Fiches d'exercices de musculation de base (squat, développé couché, rowing,
    soulevé de terre), destinées à peupler la bibliothèque d'exercices (seed.py)."""
    return _load()["musculation_execution_exercices_base"]


def get_notes_generation_ia() -> list[str]:
    """Règles de comportement que Mistral doit respecter systématiquement
    (garde-fous pliométrie, formulation en repères indicatifs, rappel
    gainage/prévention, exclusion de zone sensible, ...)."""
    return _load()["notes_generation_ia"]["instructions_pour_prompt_mistral"]


def _find_by_id(items: list[dict], id_: str) -> Optional[dict]:
    return next((item for item in items if item.get("id") == id_), None)


def _fiche(titre: str, contenu: str, extra: Optional[str] = None) -> str:
    txt = f"### {titre}\n{contenu}"
    if extra:
        txt += f"\n{extra}"
    return txt


def _priorites_poste_fiche(poste: str) -> Optional[str]:
    for entry in _load()["priorites_par_poste"]:
        if entry["poste"].lower() == (poste or "").lower():
            return _fiche(
                f"Priorités physiques pour le poste {entry['poste']}",
                "Priorités : " + ", ".join(entry["priorites"]) + f". {entry.get('note', '')}",
            )
    return None


def _prevention_blessures_fiche(zone_sensible: Optional[str] = None) -> str:
    data = _load()["prevention_blessures"]
    fifa = data["protocole_fifa11plus"]
    parts = [
        f"Protocole FIFA 11+ (fréquence recommandée : {fifa['frequence_recommandee']}). {fifa['avertissement']}",
        "Gainage à intégrer : "
        + "; ".join(f"{g['type']} ({g['exercice']}, {g['modalite']})" for g in data["gainage"]),
    ]
    if zone_sensible:
        zone_info = next((z for z in data["zones_a_risque"] if z["zone"].lower() == zone_sensible.lower()), None)
        if zone_info:
            parts.append(f"Zone à risque signalée « {zone_sensible} » : {zone_info['exercice_prevention']}")
    return _fiche("Prévention des blessures", "\n".join(parts))


def selectionner_fiches_pertinentes(type_seance: str, poste: str, zone_sensible: Optional[str] = None) -> list[str]:
    """Sélectionne 2 à 4 fiches pertinentes selon le type de séance suggéré par
    le moteur de règles et le poste du joueur. Ne renvoie jamais tout le fichier."""
    data = _load()
    fiches: list[str] = []

    if type_seance == "explosivité_vitesse":
        for id_ in ("explosivite_force_explosive", "vitesse_vivacite_reactivite"):
            item = _find_by_id(data["qualites_physiques_football"], id_)
            if item:
                fiches.append(_fiche(item["titre"], item["contenu"]))
        fiches.append(_prevention_blessures_fiche(zone_sensible))

    elif type_seance == "force":
        item = _find_by_id(data["principes_fondamentaux"], "zones_charge_objectif")
        if item:
            tableau_txt = "; ".join(
                f"{row['objectif']} : {row['charge_pct_1RM']} 1RM, {row['repetitions']} reps, "
                f"repos {row['repos']}, RPE {row['rpe_cible']}"
                for row in item["tableau"]
            )
            fiches.append(_fiche(item["titre"], f"{item['contenu']} {item['note']}", tableau_txt))
        item = _find_by_id(data["principes_fondamentaux"], "surcharge_progressive")
        if item:
            fiches.append(_fiche(item["titre"], item["contenu"]))

    elif type_seance == "esthétique":
        item = _find_by_id(data["principes_fondamentaux"], "hypertrophie_volume")
        if item:
            fiches.append(_fiche(item["titre"], item["contenu"]))
        interf = data["interference_force_esthetique_explosivite"]
        fiches.append(_fiche(interf["titre"], interf["contenu"], "; ".join(interf["recommandations_pratiques"])))

    elif type_seance == "décharge":
        for id_ in ("recuperation_supercompensation", "signes_surentrainement"):
            item = _find_by_id(data["principes_fondamentaux"], id_)
            if item:
                fiches.append(_fiche(item["titre"], item["contenu"]))

    poste_fiche = _priorites_poste_fiche(poste)
    if poste_fiche:
        fiches.append(poste_fiche)

    return fiches[:4]
