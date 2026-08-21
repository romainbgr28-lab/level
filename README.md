# LEVEL

PWA de coaching personnel (force physique + développement intellectuel), installable sur iPhone via "Ajouter à l'écran d'accueil".

## Stack

React + Vite + TypeScript, `react-router-dom` pour la navigation, `vite-plugin-pwa` pour le manifest et le service worker. Aucun backend : toutes les données viennent de `src/data/mockData.ts`.

## Démarrer

```bash
npm install
npm run dev
```

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
src/
  types/        types partagés (contrat de données)
  data/         mockData.ts — toutes les données mockées, cohérentes entre écrans
  components/   Header, BottomNav, LineChart (SVG, pas de lib externe)
  screens/      un fichier par écran (Today, Workout, Module, Progress, WeeklyReview, News, Profile)
  App.tsx       routes
```

Pour brancher un vrai backend : remplacer les imports de `src/data/mockData.ts` par des appels API/hooks (ex. React Query) exposant la même forme de données (`src/types`). Les écrans ne dépendent que de ces types, pas du mock directement au-delà de l'import.
