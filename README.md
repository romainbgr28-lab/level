# LEVEL

PWA de coaching personnel (force physique + développement intellectuel), installable sur iPhone via "Ajouter à l'écran d'accueil".

## Stack

React + Vite + TypeScript, `react-router-dom` pour la navigation, `vite-plugin-pwa` pour le manifest et le service worker. Backend FastAPI + SQLite (`backend/`) pour le profil, les séances, l'historique d'exercices, les modules d'apprentissage et les streaks. Le bilan hebdomadaire et l'actu n'ont pas de table dédiée et restent mockés (`src/data/mockData.ts`).

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
                 sessions_apprentissage, streaks)
  schemas.py    schémas Pydantic
  seed.py       données initiales (profil, module, séance du jour)
src/
  api/          client.ts — appels fetch vers le backend
  types/        types partagés (contrat de données)
  data/         mockData.ts — bilan hebdomadaire + actu (pas de table backend)
  components/   Header, BottomNav, LineChart (SVG, pas de lib externe)
  screens/      un fichier par écran (Today, Workout, Module, Progress, WeeklyReview, News, Profile)
  App.tsx       routes
```
