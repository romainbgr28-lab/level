import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Header from '../components/Header';
import { genererProgramme, getContexteJour, getProgrammeActif, messageErreur } from '../api/client';
import type { ApiContexteJour, ApiProgramme } from '../api/client';
import { EtatChargement, EtatErreur, EtatVide, LigneErreur } from '../components/EtatEcran';
import { feedback } from '../components/Toast';
import { donneesModifiees, surDonneesModifiees } from '../utils/donneesFraiches';
import { typeSeanceMeta } from '../data/programmeTypes';
// Semaine courante partagée avec l'écran Aujourd'hui : s'appuie sur getNow() et respecte donc
// la date simulée (src/utils/devDate.ts), là où un Date.now() local l'ignorait silencieusement.
import { semaineActuelle } from '../utils/programme';

// Libellés des statuts de jour décidés par le moteur (backend/contexte_jour.py) : le frontend
// se contente de les nommer, il n'en redérive aucun.
const LIBELLE_STATUT_JOUR: Record<string, string> = {
  match: 'Match',
  repos: 'Repos',
  indisponible: 'Indisponible',
};

function statutSemaine(num: number, semaineActuelleNum: number): 'passee' | 'actuelle' | 'a-venir' {
  if (num < semaineActuelleNum) return 'passee';
  if (num === semaineActuelleNum) return 'actuelle';
  return 'a-venir';
}

export default function Programme() {
  const navigate = useNavigate();
  const [programme, setProgramme] = useState<ApiProgramme | null>(null);
  const [contexte, setContexte] = useState<ApiContexteJour | null>(null);
  const [loading, setLoading] = useState(true);
  const [chargementErreur, setChargementErreur] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmationRegeneration, setConfirmationRegeneration] = useState(false);

  const charger = useCallback(() => {
    setLoading(true);
    setChargementErreur(null);
    // Le contexte porte la semaine réelle (match, indisponibilité, jour courant) : sans lui on
    // ne peut afficher que le gabarit brut, qui ne dit rien des contraintes du calendrier. Son
    // échec n'empêche donc pas d'afficher le programme, contrairement à celui du programme.
    Promise.all([getProgrammeActif(), getContexteJour().catch(() => null)])
      .then(([prog, ctx]) => {
        setProgramme(prog);
        setContexte(ctx);
      })
      .catch((e) => setChargementErreur(messageErreur(e, 'Ton programme n’a pas pu être chargé.')))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    charger();
    // Une modification de profil reconstruit le programme côté serveur : cet écran doit refléter
    // le nouveau planning, pas celui affiché avant la modification.
    return surDonneesModifiees((sujet) => {
      if (sujet === 'profil' || sujet === 'programme') charger();
    });
  }, [charger]);

  async function handleGenerer(regenerer: boolean) {
    if (generating) return; // garde anti double-clic : une seule construction à la fois
    setGenerating(true);
    setError(null);
    try {
      const prog = await genererProgramme(regenerer);
      setProgramme(prog);
      setContexte(await getContexteJour().catch(() => null));
      setConfirmationRegeneration(false);
      donneesModifiees('programme');
      feedback(regenerer ? 'Programme recalculé' : 'Programme créé');
    } catch (e) {
      setError(messageErreur(e, 'Ton programme n’a pas pu être construit.'));
    } finally {
      setGenerating(false);
    }
  }

  if (loading) {
    return (
      <div className="screen">
        <Header title="Mon programme" />
        <h1 className="page-title">Mon programme</h1>
        <EtatChargement message="Chargement de ton programme…" />
      </div>
    );
  }

  if (chargementErreur) {
    return (
      <div className="screen">
        <Header title="Mon programme" />
        <h1 className="page-title">Mon programme</h1>
        <EtatErreur
          titre="Programme indisponible"
          message={chargementErreur}
          action={{ label: 'Réessayer', onClick: charger }}
          actionSecondaire={{ label: 'Retour à aujourd’hui', onClick: () => navigate('/') }}
        />
      </div>
    );
  }

  if (!programme) {
    return (
      <div className="screen">
        <Header title="Mon programme" />
        <h1 className="page-title">Mon programme</h1>
        <EtatVide
          titre="Pas encore de programme"
          message="Ton programme répartit tes séances sur 8 semaines à partir de tes objectifs, de tes disponibilités et de ton calendrier de matchs. LEVEL le construit en une fois, puis l’adapte au fil de tes séances."
          action={{
            label: 'Construire mon programme',
            onClick: () => void handleGenerer(false),
            enCours: generating,
            labelEnCours: 'Construction en cours…',
          }}
        >
          <LigneErreur message={error} />
        </EtatVide>
      </div>
    );
  }

  const semaine = semaineActuelle(programme);
  const jours = Object.entries(programme.gabarit_hebdomadaire);
  const phaseActive = programme.phases.find(
    (phase) => semaine >= phase.semaine_debut && semaine <= phase.semaine_fin
  );
  const debut = new Date(programme.date_debut);
  const fin = new Date(debut.getTime() + programme.duree_semaines * 7 * 24 * 60 * 60 * 1000);
  const formatDate = (d: Date) => d.toLocaleDateString('fr-FR', { day: 'numeric', month: 'long' });

  return (
    <div className="screen">
      <Header title="Mon programme" />

      <section className="programme-hero">
        <div className="programme-hero__eyebrow">Programme en cours</div>
        <div className="programme-hero__figure">
          <span className="programme-hero__num">{semaine}</span>
          <span className="programme-hero__total">/ {programme.duree_semaines}</span>
        </div>
        <div className="programme-hero__dates">
          {formatDate(debut)} — {formatDate(fin)}
        </div>

        <div className="programme-weeks">
          {Array.from({ length: programme.duree_semaines }).map((_, i) => {
            const num = i + 1;
            const statut = statutSemaine(num, semaine);
            return (
              <div key={num} className={`programme-week programme-week--${statut}`} title={`Semaine ${num}`}>
                <span className="programme-week__bar" />
                <span className="programme-week__num">{num}</span>
              </div>
            );
          })}
        </div>
      </section>

      {phaseActive && (
        <section className="card">
          <div className="card__eyebrow">Phase actuelle</div>
          <div className="programme-phase__nom" style={{ color: 'var(--text)', fontSize: 20 }}>
            {phaseActive.nom}
          </div>
          <p className="subtle" style={{ marginTop: 6 }}>{phaseActive.description}</p>
        </section>
      )}

      <section className="card">
        <div className="card__eyebrow">Toutes les phases</div>
        {programme.phases.map((phase) => {
          const active = phase === phaseActive;
          return (
            <div key={phase.nom} className={`programme-phase ${active ? 'programme-phase--active' : ''}`}>
              <div className="programme-phase__head">
                <span className="programme-phase__nom">{phase.nom}</span>
                <span className="subtle">
                  S{phase.semaine_debut}–{phase.semaine_fin}
                </span>
              </div>
            </div>
          );
        })}
      </section>

      <section className="card">
        <div className="card__eyebrow">Ma semaine</div>
        {contexte && contexte.semaine.length > 0 ? (
          contexte.semaine.map((jour) => {
            const meta = jour.type_seance_prevu ? typeSeanceMeta(jour.type_seance_prevu) : null;
            return (
              <div
                key={jour.date}
                className={`programme-jour${jour.est_aujourdhui ? ' programme-jour--aujourdhui' : ''}${
                  jour.est_passe ? ' programme-jour--passe' : ''
                }`}
              >
                <span className="programme-jour__label">{jour.jour_label}</span>
                <span className="programme-jour__type" style={meta ? { color: meta.color } : undefined}>
                  {meta ? meta.label : (LIBELLE_STATUT_JOUR[jour.statut] ?? '—')}
                </span>
              </div>
            );
          })
        ) : (
          <>
            {/* Contexte indisponible (réseau) : on affiche le gabarit brut plutôt que rien, en
                disant explicitement ce qui manque — sinon l'utilisateur croit lire sa semaine
                réelle alors que matchs et indisponibilités n'y sont pas reflétés. */}
            <p className="subtle" style={{ margin: '0 0 10px' }}>
              Trame habituelle de ta semaine. Tes matchs et tes indisponibilités n’ont pas pu être
              récupérés : la semaine réelle peut différer.
            </p>
            {jours.map(([jour, type]) => {
              const meta = typeSeanceMeta(type);
              return (
                <div key={jour} className="programme-jour">
                  <span className="programme-jour__label">{jour}</span>
                  <span className="programme-jour__type" style={{ color: meta.color }}>
                    {meta.label}
                  </span>
                </div>
              );
            })}
            <button className="btn btn--ghost btn--sm" style={{ marginTop: 12 }} onClick={charger}>
              Réessayer
            </button>
          </>
        )}
      </section>

      {/* Action principale : retourner à ce qu'il y a à faire aujourd'hui. La régénération est
          une option avancée, pas le geste mis en avant. */}
      <div className="editorial-cta">
        <button className="btn btn--primary" onClick={() => navigate('/')}>
          Voir ma journée →
        </button>
        <button className="link-discreet" onClick={() => setConfirmationRegeneration(true)}>
          Recalculer mon programme
        </button>
      </div>
      <LigneErreur message={error} />

      {confirmationRegeneration && (
        <div className="modal-overlay" onClick={() => setConfirmationRegeneration(false)}>
          <div className="modal-sheet" onClick={(e) => e.stopPropagation()}>
            <h2 className="card__title" style={{ clear: 'both', marginBottom: 8 }}>
              Recalculer ton programme ?
            </h2>
            <p className="subtle" style={{ marginBottom: 16 }}>
              LEVEL reconstruit les 8 semaines à venir à partir de ton profil actuel : objectifs,
              disponibilités, calendrier de matchs. Tes séances déjà réalisées et ton historique
              ne sont pas touchés — seul ce qui est prévu ensuite change.
            </p>
            <LigneErreur message={error} />
            <button
              className="btn btn--ghost"
              style={{ marginBottom: 8 }}
              disabled={generating}
              onClick={() => setConfirmationRegeneration(false)}
            >
              Annuler
            </button>
            <button
              className="btn btn--primary"
              disabled={generating}
              onClick={() => void handleGenerer(true)}
            >
              {generating ? 'Recalcul en cours…' : 'Recalculer'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
