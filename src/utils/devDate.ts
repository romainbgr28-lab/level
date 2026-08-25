// Simulation de la date courante, pour tester le programme (semaine/jour, séance du jour,
// adaptation) sans attendre le temps réel.
//
// Ne modifie ni les données réelles ni la date système : fournit seulement une "date
// courante" alternative aux endroits qui en ont besoin (semaine/jour du programme, écran
// Aujourd'hui) et, via le header X-Dev-Date, au backend (voir backend/dev_date.py — lui-même
// gardé par sa propre variable d'environnement DEV_MODE côté serveur : sans elle, le backend
// ignore le header même si le panneau est visible côté frontend).
//
// Le panneau (DevDatePanel) est visible en build de développement (import.meta.env.DEV) OU,
// en production (ex: Vercel), une fois activé explicitement via l'URL ?devmode=1 — l'activation
// est alors mémorisée en localStorage. Visite ?devmode=0 pour la désactiver.

const STORAGE_KEY = 'level_dev_simulated_date';
const DEV_MODE_STORAGE_KEY = 'level_dev_mode_enabled';

function lireFlagDevModeDepuisUrl(): boolean | null {
  if (typeof window === 'undefined') return null;
  const valeur = new URLSearchParams(window.location.search).get('devmode');
  if (valeur === '1') return true;
  if (valeur === '0') return false;
  return null;
}

function devModeActivePersiste(): boolean {
  try {
    const depuisUrl = lireFlagDevModeDepuisUrl();
    if (depuisUrl !== null) {
      localStorage.setItem(DEV_MODE_STORAGE_KEY, depuisUrl ? '1' : '0');
      return depuisUrl;
    }
    return localStorage.getItem(DEV_MODE_STORAGE_KEY) === '1';
  } catch {
    return false;
  }
}

export const DEV_MODE_ENABLED = import.meta.env.DEV || devModeActivePersiste();

// Format YYYY-MM-DD, ou null si aucune simulation n'est active.
export function getDevSimulatedDate(): string | null {
  if (!DEV_MODE_ENABLED) return null;
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

export function setDevSimulatedDate(dateStr: string | null): void {
  if (!DEV_MODE_ENABLED) return;
  try {
    if (dateStr) {
      localStorage.setItem(STORAGE_KEY, dateStr);
    } else {
      localStorage.removeItem(STORAGE_KEY);
    }
  } catch {
    // localStorage indisponible (navigation privée, quota...) : simulation ignorée.
  }
}

// Remplace new Date() partout où le code doit connaître "aujourd'hui" côté frontend.
export function getNow(): Date {
  const override = getDevSimulatedDate();
  if (override) {
    const [y, m, d] = override.split('-').map(Number);
    return new Date(y, m - 1, d);
  }
  return new Date();
}
