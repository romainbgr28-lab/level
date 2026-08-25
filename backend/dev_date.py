"""Simulation de la date courante, réservée au développement.

En production, `get_current_date` renvoie toujours `date.today()` : ce module
n'a alors strictement aucun effet. Il n'est activé que si la variable
d'environnement DEV_MODE est positionnée côté backend (jamais en prod), et
seulement si le client envoie explicitement le header X-Dev-Date.

Ne modifie ni les données réelles, ni la date de création du programme, ni
les timestamps déjà enregistrés en base : ce module ne fait que fournir une
date "aujourd'hui" alternative aux endpoints qui en ont besoin.
"""

import os
from datetime import date, datetime
from typing import Optional

from fastapi import Header

DEV_MODE = os.environ.get("DEV_MODE", "").strip().lower() in ("1", "true", "yes")


def get_current_date(x_dev_date: Optional[str] = Header(default=None)) -> date:
    """Dépendance FastAPI : date "aujourd'hui" à utiliser par l'endpoint.

    Ignorée (retombe sur la vraie date système) sauf si DEV_MODE est actif
    côté backend ET que le header X-Dev-Date (format YYYY-MM-DD) est fourni.
    """
    if DEV_MODE and x_dev_date:
        try:
            return datetime.strptime(x_dev_date, "%Y-%m-%d").date()
        except ValueError:
            pass
    return date.today()
