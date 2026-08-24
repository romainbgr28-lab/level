# LEVEL

PWA de coaching personnel (force physique + développement intellectuel), installable sur iPhone via "Ajouter à l'écran d'accueil".

## Stack

React + Vite + TypeScript, `react-router-dom` pour la navigation, `vite-plugin-pwa` pour le manifest et le service worker. Backend FastAPI + SQLite (`backend/`) pour le profil, les séances, l'historique d'exercices, l'historique de séances (prévu/réalisé + contexte + phase calendaire), les modules d'apprentissage et les streaks. Le bilan hebdomadaire et l'actu n'ont pas de table dédiée et restent mockés (`src/data/mockData.ts`).

⚠️ SQLite ne migre pas automatiquement un changement de schéma : après avoir tiré une modification des modèles (`backend/models.py`), supprime `backend/level.db` avant de relancer `uvicorn`, sinon les anciennes colonnes/tables restent en place et l'API renverra des erreurs de validation.

## Démarrer

Backend (API sur `http://localhost:8000`) :

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Frontend :

```bash
npm install
npm run dev
```

Le frontend appelle l'API sur `http://localhost:8000` par défaut ; surcharger avec la variable d'environnement Vite `VITE_API_BASE` si besoin.

## Build

```bash
npm run build
npm run preview
```

## Installer sur iPhone

1. Ouvrir l'app buildée (servie en HTTPS) dans Safari.
2. Partager → "Sur l'écran d'accueil".

## Structure

```
backend/
  main.py       endpoints REST FastAPI
  models.py     tables SQLAlchemy (profil, seances, exercices_historique, modules_intellectuels,
                 sessions_apprentissage, streaks, historique_seances)
  schemas.py    schémas Pydantic
  calendrier.py calcul de la phase calendaire (jour_de_match / veille / lendemain / developpement)
                 à partir du calendrier_matchs du profil
  seed.py       données initiales (module, séance du jour — le profil reste vide pour déclencher l'onboarding)
src/
  api/          client.ts — appels fetch vers le backend
  types/        types partagés (contrat de données)
  data/         mockData.ts — bilan hebdomadaire + actu (pas de table backend)
  components/   Header, BottomNav, LineChart (SVG, pas de lib externe)
  screens/      un fichier par écran (Today, Workout, Module, Progress, WeeklyReview, News, Profile)
  App.tsx       routes
```
