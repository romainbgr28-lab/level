import { useCallback, useEffect, useRef, useState } from 'react';
import {
  envoyerMessageCoach,
  getConversationCoach,
  getCoachContexte,
  messageErreur,
  type ApiCoachContexte,
} from '../api/client';
import { EtatChargement } from '../components/EtatEcran';

/**
 * Écran Coach — interface de la V0.
 *
 * Volontairement minimal (spécification V0 sections 6 et 25) : une conversation lisible, un
 * champ de saisie, et quelques suggestions. Pas de dashboard, pas de cards partout, pas de
 * petits textes. Les écrans existants (Aujourd'hui, Programme, Progression, Profil) ne sont
 * pas remplacés : ils restent accessibles par la navigation du bas.
 *
 * Ce que cet écran ne fait PAS, et c'est essentiel : il ne décide rien. Il n'interprète pas
 * les messages, ne calcule aucune charge et n'écrit aucune donnée métier. Il poste le texte
 * à `/api/coach/message` et affiche la réponse. Les suggestions elles-mêmes ne sont que des
 * phrases pré-écrites envoyées par le même chemin — jamais un raccourci qui contournerait le
 * moteur.
 */

interface MessageAffiche {
  id: string;
  role: 'utilisateur' | 'coach';
  contenu: string;
  /** Actions métier exécutées pour produire ce message : affichées discrètement pour que
   *  « c'est enregistré » soit vérifiable, jamais une simple affirmation du modèle. */
  actions?: string[];
  enCours?: boolean;
}

/** Suggestions volontairement peu nombreuses (section 6) : le champ libre reste la voie
 *  principale. Ce sont des phrases, pas des commandes : elles passent par le même chemin que
 *  ce que l'utilisateur écrirait lui-même. */
const SUGGESTIONS_PAR_STATUT: Record<string, string[]> = {
  seance: ['Je fais quoi aujourd’hui ?', 'Je n’ai que 25 minutes', 'J’ai fait ma séance'],
  repos: ['C’est quoi ma semaine ?', 'Je peux quand même bouger un peu ?'],
  match: ['Je prépare mon match comment ?', 'C’est quoi ma semaine ?'],
  indisponible: ['C’est quoi ma semaine ?', 'Je voudrais changer mes disponibilités'],
  aucun_programme: ['Construis-moi mon programme'],
  aucun_profil: ['Construis-moi mon programme'],
};

const SUGGESTIONS_DEFAUT = ['Je fais quoi aujourd’hui ?', 'Est-ce que je progresse ?'];

/** Libellés lisibles des actions métier, pour la ligne discrète sous une réponse du coach.
 *  Une action absente de cette table s'affiche sous son nom technique plutôt que d'être
 *  masquée : mieux vaut un mot brut qu'une action invisible. */
const LIBELLES_ACTIONS: Record<string, string> = {
  generer_programme: 'programme construit',
  get_seance_du_jour: 'séance du jour consultée',
  enregistrer_performance: 'performance enregistrée',
  terminer_seance: 'séance clôturée',
  adapter_seance: 'séance adaptée',
  remplacer_exercice: 'exercice remplacé',
  signaler_douleur: 'douleur enregistrée',
  signaler_fatigue: 'fatigue enregistrée',
  deplacer_match: 'calendrier de matchs mis à jour',
  mettre_a_jour_disponibilites: 'disponibilités mises à jour',
  mettre_a_jour_materiel: 'matériel mis à jour',
  get_progression_exercice: 'progression consultée',
};

/** Seules les actions qui CHANGENT quelque chose sont annoncées : lister les lectures
 *  ajouterait du bruit à chaque réponse sans rien apprendre à l'utilisateur. */
function actionsVisibles(actions: { nom: string; resultat: Record<string, unknown> }[]): string[] {
  return actions
    .filter((a) => !a.nom.startsWith('get_') && !a.nom.startsWith('chercher_'))
    .filter((a) => a.resultat?.ok === true)
    .map((a) => LIBELLES_ACTIONS[a.nom] ?? a.nom);
}

export default function Coach() {
  const [messages, setMessages] = useState<MessageAffiche[]>([]);
  const [contexte, setContexte] = useState<ApiCoachContexte | null>(null);
  const [saisie, setSaisie] = useState('');
  const [chargement, setChargement] = useState(true);
  const [envoiEnCours, setEnvoiEnCours] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);

  const finDeFil = useRef<HTMLDivElement>(null);
  // Garde synchrone anti double-envoi : un state React n'est pas encore à jour au moment du
  // second clic/appui, ce qui posterait deux fois le même message (même convention que les
  // actions critiques des autres écrans).
  const envoiVerrou = useRef(false);

  useEffect(() => {
    let annule = false;
    Promise.all([getConversationCoach(), getCoachContexte()])
      .then(([conversation, ctx]) => {
        if (annule) return;
        setMessages(
          conversation.map((m) => ({
            id: `s${m.id}`,
            role: m.role,
            contenu: m.contenu,
            actions: m.actions?.length
              ? m.actions
                  .filter((a) => !a.nom.startsWith('get_') && !a.nom.startsWith('chercher_'))
                  .map((a) => LIBELLES_ACTIONS[a.nom] ?? a.nom)
              : undefined,
          })),
        );
        setContexte(ctx);
      })
      .catch((e) => {
        if (!annule) setErreur(messageErreur(e, 'LEVEL n’arrive pas à charger ta conversation.'));
      })
      .finally(() => {
        if (!annule) setChargement(false);
      });
    return () => {
      annule = true;
    };
  }, []);

  useEffect(() => {
    finDeFil.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages]);

  const envoyer = useCallback(
    async (texte: string) => {
      const message = texte.trim();
      if (!message || envoiVerrou.current) return;
      envoiVerrou.current = true;
      setEnvoiEnCours(true);
      setErreur(null);
      setSaisie('');

      const horodatage = Date.now();
      setMessages((precedents) => [
        ...precedents,
        { id: `u${horodatage}`, role: 'utilisateur', contenu: message },
        { id: `c${horodatage}`, role: 'coach', contenu: '', enCours: true },
      ]);

      try {
        const reponse = await envoyerMessageCoach(message);
        setMessages((precedents) =>
          precedents.map((m) =>
            m.id === `c${horodatage}`
              ? {
                  ...m,
                  contenu: reponse.reponse,
                  actions: actionsVisibles(reponse.actions),
                  enCours: false,
                }
              : m,
          ),
        );
        setContexte(reponse.contexte);
      } catch (e) {
        // La bulle en attente est retirée plutôt que remplie d'un texte d'erreur : une panne
        // ne doit pas ressembler à une réponse du coach (l'utilisateur doit pouvoir faire la
        // différence entre « LEVEL a décidé ça » et « LEVEL n'a pas pu répondre »).
        setMessages((precedents) => precedents.filter((m) => m.id !== `c${horodatage}`));
        setErreur(messageErreur(e, 'LEVEL n’a pas pu répondre.'));
      } finally {
        envoiVerrou.current = false;
        setEnvoiEnCours(false);
      }
    },
    [],
  );

  if (chargement) {
    return (
      <div className="screen">
        <EtatChargement message="Ouverture de LEVEL…" />
      </div>
    );
  }

  const statut = contexte?.jour.statut ?? 'seance';
  const suggestions = SUGGESTIONS_PAR_STATUT[statut] ?? SUGGESTIONS_DEFAUT;
  const filVide = messages.length === 0;

  return (
    <div className="coach">
      <header className="coach__entete">
        <h1 className="coach__titre">LEVEL</h1>
        <p className="coach__statut">{resumeDuJour(contexte)}</p>
      </header>

      <div className="coach__fil">
        {filVide && (
          <div className="coach__accueil">
            <p>{resumeDuJour(contexte)}</p>
            <p className="coach__accueil-invite">Que veux-tu faire&nbsp;?</p>
          </div>
        )}

        {messages.map((message) => (
          <article key={message.id} className={`coach-message coach-message--${message.role}`}>
            <span className="coach-message__auteur">{message.role === 'coach' ? 'LEVEL' : 'TOI'}</span>
            {message.enCours ? (
              <p className="coach-message__texte coach-message__texte--attente">LEVEL réfléchit…</p>
            ) : (
              <p className="coach-message__texte">{message.contenu}</p>
            )}
            {message.actions && message.actions.length > 0 && (
              <p className="coach-message__actions">↳ {message.actions.join(' · ')}</p>
            )}
          </article>
        ))}

        <div ref={finDeFil} />
      </div>

      {erreur && (
        <p className="coach__erreur" role="alert">
          {erreur}
        </p>
      )}

      <div className="coach__pied">
        {!envoiEnCours && (
          <div className="coach__suggestions">
            {suggestions.map((suggestion) => (
              <button
                key={suggestion}
                type="button"
                className="coach__suggestion"
                onClick={() => envoyer(suggestion)}
              >
                {suggestion}
              </button>
            ))}
          </div>
        )}

        <form
          className="coach__saisie"
          onSubmit={(e) => {
            e.preventDefault();
            envoyer(saisie);
          }}
        >
          <textarea
            className="coach__champ"
            placeholder="Écris à LEVEL…"
            value={saisie}
            rows={1}
            onChange={(e) => setSaisie(e.target.value)}
            onKeyDown={(e) => {
              // Entrée envoie, Maj+Entrée passe à la ligne : on écrit à son coach, on ne
              // rédige pas un document.
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                envoyer(saisie);
              }
            }}
          />
          <button
            type="submit"
            className="coach__envoyer"
            disabled={envoiEnCours || saisie.trim() === ''}
            aria-label="Envoyer"
          >
            ↑
          </button>
        </form>
      </div>
    </div>
  );
}

/** Une phrase sur l'état du jour, construite à partir du contexte calculé par le moteur —
 *  jamais redérivée ici (le frontend n'est source de vérité sur aucune décision). */
function resumeDuJour(contexte: ApiCoachContexte | null): string {
  if (!contexte) return 'Prêt quand tu veux.';

  const seance = contexte.seance_du_jour;
  if (seance && seance.statut === 'terminee') return 'Ta séance du jour est terminée.';
  if (seance) {
    const duree = seance.duree_prevue_min ? ` — ${seance.duree_prevue_min} min` : '';
    return `Tu as une séance aujourd’hui : ${seance.nom}${duree}.`;
  }

  switch (contexte.jour.statut) {
    case 'match':
      return 'Tu as match aujourd’hui.';
    case 'repos':
      return 'Aujourd’hui, c’est repos.';
    case 'indisponible':
      return 'Tu n’es pas disponible aujourd’hui.';
    case 'aucun_profil':
      return 'On commence par ton profil.';
    case 'aucun_programme':
      return 'Il te manque un programme.';
    default:
      return contexte.jour.type_seance_prevu
        ? `Tu as une séance prévue aujourd’hui (${contexte.jour.type_seance_prevu}).`
        : 'Prêt quand tu veux.';
  }
}
