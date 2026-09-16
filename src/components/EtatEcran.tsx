import type { ReactNode } from 'react';

/**
 * États transverses d'écran : chargement, erreur, vide.
 *
 * Règle appliquée partout dans LEVEL : un écran ne montre jamais un vide muet. Il dit ce qui se
 * passe, pourquoi, et propose au moins une action pour continuer. Ces trois composants
 * matérialisent cette règle une seule fois, pour que chaque écran l'applique de la même façon.
 */

interface Action {
  label: string;
  onClick: () => void;
  /** Action en cours : le bouton reste visible mais devient inopérant, avec son libellé d'attente. */
  enCours?: boolean;
  labelEnCours?: string;
}

function BoutonAction({ action, variante }: { action: Action; variante: 'primary' | 'ghost' }) {
  return (
    <button
      className={`btn btn--${variante}`}
      style={{ marginTop: 10 }}
      disabled={action.enCours}
      onClick={action.onClick}
    >
      {action.enCours ? (action.labelEnCours ?? 'En cours…') : action.label}
    </button>
  );
}

/** Chargement explicite : on dit ce qu'on charge, jamais un écran blanc. */
export function EtatChargement({ message = 'Chargement…' }: { message?: string }) {
  return (
    <section className="card etat-bloc" aria-busy="true">
      <div className="etat-bloc__spinner" aria-hidden="true" />
      <p className="subtle" style={{ margin: 0 }}>
        {message}
      </p>
    </section>
  );
}

/**
 * Erreur remontée à l'utilisateur : ce qui n'a pas marché, et comment continuer.
 * `message` doit déjà être une phrase lisible (voir ApiError dans src/api/client.ts).
 */
export function EtatErreur({
  titre = 'Impossible de charger cette page',
  message,
  action,
  actionSecondaire,
}: {
  titre?: string;
  message: string;
  action?: Action;
  actionSecondaire?: Action;
}) {
  return (
    <section className="card etat-bloc etat-bloc--erreur" role="alert">
      <div className="card__eyebrow">{titre}</div>
      <p className="subtle" style={{ margin: '4px 0 0' }}>
        {message}
      </p>
      {action && <BoutonAction action={action} variante="primary" />}
      {actionSecondaire && <BoutonAction action={actionSecondaire} variante="ghost" />}
    </section>
  );
}

/**
 * Écran vide expliqué : pourquoi c'est vide, ce qui le remplira, et quoi faire maintenant.
 * Jamais « Aucune donnée » tout seul.
 */
export function EtatVide({
  titre,
  message,
  action,
  children,
}: {
  titre: string;
  message: string;
  action?: Action;
  children?: ReactNode;
}) {
  return (
    <section className="card etat-bloc">
      <div className="card__eyebrow">{titre}</div>
      <p className="subtle" style={{ margin: '4px 0 0' }}>
        {message}
      </p>
      {children}
      {action && <BoutonAction action={action} variante="primary" />}
    </section>
  );
}

/** Erreur d'une action (pas d'un chargement) : ligne discrète sous le bouton concerné. */
export function LigneErreur({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <p className="ligne-erreur" role="alert">
      {message}
    </p>
  );
}
