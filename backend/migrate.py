"""Migration additive et idempotente du schéma DB.

Ne remplace pas Base.metadata.create_all() (qui crée les tables manquantes) :
ce script ajoute uniquement les colonnes manquantes sur des tables déjà
existantes, ce que create_all() ne fait jamais.

Compatible SQLite et Postgres (via DATABASE_URL, cf. database.py).
Peut être exécuté plusieurs fois sans erreur : chaque colonne n'est ajoutée
que si elle n'existe pas déjà. Toutes les colonnes ajoutées sont nullable,
donc les lignes existantes restent valides sans backfill.

Usage : python3 migrate.py  (depuis backend/, ou `python3 -m backend.migrate`)
Appelé aussi automatiquement au démarrage de l'app (voir main.py), après
Base.metadata.create_all().
"""

from sqlalchemy import inspect, text

from database import Base, engine
import models  # noqa: F401 -- enregistre les modèles sur Base.metadata

# Chaque entrée : (table, colonne, type_sql, colonne_apres_pour_logs_uniquement)
COLONNES_A_AJOUTER = [
    ("series_loggees", "reps_prevues", "INTEGER"),
    ("series_loggees", "charge_prevue_kg", "FLOAT"),
    ("historique_seances", "decision_adaptation", "JSON"),
    ("seances", "etat_declare_avant", "JSON"),
    ("seances", "decision_adaptation", "JSON"),
]


def migrer():
    # 1. Crée les tables qui n'existent pas du tout (comportement inchangé,
    #    identique à ce que main.py fait déjà au démarrage).
    Base.metadata.create_all(bind=engine)

    # 2. Ajoute les colonnes manquantes sur les tables existantes.
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table, colonne, type_sql in COLONNES_A_AJOUTER:
            colonnes_existantes = {c["name"] for c in inspector.get_columns(table)}
            if colonne in colonnes_existantes:
                print(f"[migrate] {table}.{colonne} existe déjà — ignoré")
                continue
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {colonne} {type_sql}"))
            print(f"[migrate] {table}.{colonne} ajoutée")


if __name__ == "__main__":
    migrer()
