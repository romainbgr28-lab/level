import { useEffect, useState } from 'react';

/**
 * Retour discret sur une action réussie (série validée, profil enregistré, exercice remplacé…).
 *
 * Volontairement minimal : un seul message à la fois, effacé automatiquement. Les erreurs ne
 * passent pas par ici — elles s'affichent à l'endroit où l'action a échoué, avec le moyen de
 * réessayer (voir LigneErreur/EtatErreur), là où un toast disparaîtrait avant d'être utile.
 */

type Ecouteur = (message: string) => void;

let ecouteur: Ecouteur | null = null;

/** Affiche un retour court. Sans <ToastHost /> monté, l'appel est simplement sans effet. */
export function feedback(message: string): void {
  ecouteur?.(message);
}

const DUREE_MS = 2600;

export default function ToastHost() {
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    ecouteur = (m) => setMessage(m);
    return () => {
      ecouteur = null;
    };
  }, []);

  useEffect(() => {
    if (message === null) return;
    const t = setTimeout(() => setMessage(null), DUREE_MS);
    return () => clearTimeout(t);
  }, [message]);

  if (message === null) return null;

  return (
    <div className="toast" role="status" aria-live="polite">
      {message}
    </div>
  );
}
