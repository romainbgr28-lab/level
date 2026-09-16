import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Header from '../components/Header';
import { deleteProfil, getProfil, getStats, messageErreur, patchProfil } from '../api/client';
import type { ApiDisponibilites, ApiObjectifV2, ApiProfil, ApiStats, ThemeObjectifV2 } from '../api/client';
import DevDatePanel from '../components/DevDatePanel';
import { EtatChargement, EtatErreur, EtatVide, LigneErreur } from '../components/EtatEcran';
import { feedback } from '../components/Toast';
import { donneesModifiees } from '../utils/donneesFraiches';
import {
  LABELS_THEMES_OBJECTIFS,
  JOURS_DISPONIBILITES,
  MAX_OBJECTIFS,
  OPTIONS_MINUTES,
  THEMES_OBJECTIFS,
} from './Onboarding';

// Jour de match habituel : nom complet capitalisé, format attendu par
// calendrier_matchs.jour_habituel (backend/regles_seance.py::JOURS_SEMAINE). Ne pas confondre
// avec les clés minuscules de `disponibilites`.
const JOURS_MATCH = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche'];

/** Ce que la modification a réellement produit, tel que renvoyé par le backend : affiché à
 * l'utilisateur sans rien supposer (voir ApiProfilPatchResult). */
interface ResultatEdition {
  programmeRecalcule: boolean;
  programmeErreur: string | null;
  seanceSupprimee: boolean;
}

/** Thèmes d'objectifs d'un profil, du plus prioritaire au moins prioritaire. */
function themesDuProfil(p: ApiProfil): ThemeObjectifV2[] {
  return [...(p.objectifs_v2 ?? [])].sort((a, b) => a.rang - b.rang).map((o) => o.theme);
}

export default function Profile() {
  const navigate = useNavigate();
  const [profil, setProfil] = useState<ApiProfil | null>(null);
  const [stats, setStats] = useState<ApiStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [chargementErreur, setChargementErreur] = useState<string | null>(null);
  const [resetting, setResetting] = useState(false);
  const [confirmingReset, setConfirmingReset] = useState(false);
  const [resetError, setResetError] = useState<string | null>(null);

  // ---- Édition des réglages qui pilotent réellement le programme ----
  // Disponibilités, jour de match et hiérarchie d'objectifs sont les entrées de la structure
  // hebdomadaire : sans moyen de les corriger, un changement d'objectif ou d'emploi du temps
  // obligeait à supprimer tout le profil et à refaire l'onboarding.
  type Section = 'disponibilites' | 'objectifs' | null;
  const [sectionOuverte, setSectionOuverte] = useState<Section>(null);
  const [dispoBrouillon, setDispoBrouillon] = useState<ApiDisponibilites>({});
  const [jourMatchBrouillon, setJourMatchBrouillon] = useState<string>('');
  const [objectifsBrouillon, setObjectifsBrouillon] = useState<ThemeObjectifV2[]>([]);
  const [enregistrement, setEnregistrement] = useState(false);
  const [editionErreur, setEditionErreur] = useState<string | null>(null);
  const [resultatEdition, setResultatEdition] = useState<ResultatEdition | null>(null);

  const charger = useCallback(() => {
    setLoading(true);
    setChargementErreur(null);
    Promise.all([getProfil(), getStats().catch(() => null)])
      .then(([p, s]) => {
        setProfil(p);
        setStats(s);
      })
      .catch((e) => setChargementErreur(messageErreur(e, 'Ton profil n’a pas pu être chargé.')))
      .finally(() => setLoading(false));
  }, []);

  useEffect(charger, [charger]);

  function ouvrirDisponibilites(p: ApiProfil) {
    const base: ApiDisponibilites = {};
    for (const { key } of JOURS_DISPONIBILITES) base[key] = p.disponibilites?.[key] ?? null;
    setDispoBrouillon(base);
    setJourMatchBrouillon(p.calendrier_matchs.jour_habituel ?? '');
    setEditionErreur(null);
    setResultatEdition(null);
    setSectionOuverte('disponibilites');
  }

  function ouvrirObjectifs(p: ApiProfil) {
    setObjectifsBrouillon(themesDuProfil(p));
    setEditionErreur(null);
    setResultatEdition(null);
    setSectionOuverte('objectifs');
  }

  function basculerObjectif(theme: ThemeObjectifV2) {
    setObjectifsBrouillon((prev) => {
      if (prev.includes(theme)) return prev.filter((t) => t !== theme);
      if (prev.length >= MAX_OBJECTIFS) return prev; // max 3, cf. user_model_v2.MAX_OBJECTIFS_ACTIFS
      return [...prev, theme];
    });
  }

  function deplacerObjectif(index: number, direction: -1 | 1) {
    setObjectifsBrouillon((prev) => {
      const cible = index + direction;
      if (cible < 0 || cible >= prev.length) return prev;
      const copie = [...prev];
      [copie[index], copie[cible]] = [copie[cible], copie[index]];
      return copie;
    });
  }

  /**
   * Enregistre une modification et rend compte de ses conséquences réelles. Le backend
   * reconstruit le programme dans la foulée (PATCH /api/profil) : on n'annonce ce recalcul que
   * s'il a effectivement eu lieu, et on dit quoi faire s'il a échoué.
   */
  async function enregistrer(payload: Parameters<typeof patchProfil>[0]) {
    if (enregistrement) return; // garde anti double-clic
    setEnregistrement(true);
    setEditionErreur(null);
    try {
      const res = await patchProfil(payload);
      setProfil(res.profil);
      setSectionOuverte(null);
      setResultatEdition({
        programmeRecalcule: res.programme_recalcule,
        programmeErreur: res.programme_erreur,
        seanceSupprimee: res.seance_du_jour_supprimee,
      });
      // Programme, séance du jour et contexte ont pu changer : les écrans encore montés ne
      // doivent pas continuer à afficher l'ancien planning.
      donneesModifiees('profil', 'programme', 'seance');
      feedback('Profil enregistré');
    } catch (e) {
      setEditionErreur(
        messageErreur(e, 'Tes modifications n’ont pas pu être enregistrées. Rien n’a été changé.')
      );
    } finally {
      setEnregistrement(false);
    }
  }

  async function handleReset() {
    setResetting(true);
    setResetError(null);
    try {
      await deleteProfil();
      window.location.reload();
    } catch (e) {
      setResetError(messageErreur(e, 'Le profil n’a pas pu être supprimé.'));
      setResetting(false);
    }
  }

  if (loading) {
    return (
      <div className="screen">
        <Header title="Profil" />
        <h1 className="page-title">Profil</h1>
        <EtatChargement message="Chargement de ton profil…" />
      </div>
    );
  }

  if (chargementErreur) {
    return (
      <div className="screen">
        <Header title="Profil" />
        <h1 className="page-title">Profil</h1>
        <EtatErreur
          message={chargementErreur}
          action={{ label: 'Réessayer', onClick: charger }}
          actionSecondaire={{ label: 'Retour à aujourd’hui', onClick: () => navigate('/aujourdhui') }}
        />
      </div>
    );
  }

  if (!profil) {
    return (
      <div className="screen">
        <Header title="Profil" />
        <h1 className="page-title">Profil</h1>
        <EtatVide
          titre="Aucun profil"
          message="LEVEL a besoin de ton profil pour construire ton programme. Quelques questions suffisent."
          action={{ label: 'Créer mon profil', onClick: () => window.location.reload() }}
        />
      </div>
    );
  }

  const objectifsActuels: ApiObjectifV2[] = [...(profil.objectifs_v2 ?? [])].sort((a, b) => a.rang - b.rang);

  return (
    <div className="screen">
      <Header title="Profil" />
      <h1 className="page-title">Profil</h1>

      {/* Compte rendu de la dernière modification : ce qui a changé, et quoi faire si le
          recalcul du programme n'a pas abouti. */}
      {resultatEdition && (
        <section className="card">
          <div className="card__eyebrow">Modifications enregistrées</div>
          {resultatEdition.programmeRecalcule ? (
            <>
              <p className="subtle" style={{ margin: '4px 0 0' }}>
                Ton programme a été recalculé à partir de tes nouveaux réglages. Tes séances
                déjà réalisées et ton historique sont intacts.
                {resultatEdition.seanceSupprimee
                  ? ' La séance prévue aujourd’hui a été retirée : ton nouveau planning n’en prévoit plus.'
                  : ''}
              </p>
              <button className="btn btn--primary" style={{ marginTop: 12 }} onClick={() => navigate('/programme')}>
                Voir mon nouveau programme
              </button>
            </>
          ) : (
            <>
              <p className="subtle" style={{ margin: '4px 0 0' }}>
                {resultatEdition.programmeErreur ??
                  'Tes réglages sont enregistrés, mais ton programme n’a pas pu être recalculé.'}
              </p>
              <button className="btn btn--primary" style={{ marginTop: 12 }} onClick={() => navigate('/programme')}>
                Recalculer mon programme
              </button>
            </>
          )}
        </section>
      )}

      <div className="section-title">Objectifs</div>
      <div className="tag-row">
        {objectifsActuels.length > 0
          ? objectifsActuels.map((o) => (
              <span className="tag" key={o.theme}>
                {o.rang}. {LABELS_THEMES_OBJECTIFS[o.theme] ?? o.theme}
              </span>
            ))
          : (profil.objectifs ?? []).map((g) => (
              <span className="tag" key={g}>
                {g}
              </span>
            ))}
      </div>

      {sectionOuverte !== 'objectifs' ? (
        <button
          className="btn btn--ghost btn--sm"
          style={{ marginTop: 10 }}
          onClick={() => ouvrirObjectifs(profil)}
        >
          Modifier mes objectifs
        </button>
      ) : (
        <section className="card" style={{ margin: '12px 0' }}>
          <div className="card__eyebrow">Mes objectifs</div>
          <p className="subtle" style={{ margin: '0 0 14px' }}>
            Choisis jusqu’à {MAX_OBJECTIFS} objectifs, du plus important au moins important.
            Ils déterminent le contenu de tes séances : les modifier reconstruit ton programme
            pour les semaines à venir. Ton historique n’est pas touché.
          </p>
          <div className="tag-row tag-row--select">
            {THEMES_OBJECTIFS.map((theme) => {
              const choisi = objectifsBrouillon.includes(theme);
              return (
                <button
                  key={theme}
                  type="button"
                  className={`tag tag--selectable ${choisi ? 'tag--active' : ''}`}
                  disabled={!choisi && objectifsBrouillon.length >= MAX_OBJECTIFS}
                  onClick={() => basculerObjectif(theme)}
                >
                  {LABELS_THEMES_OBJECTIFS[theme]}
                </button>
              );
            })}
          </div>

          {objectifsBrouillon.length > 0 && (
            <div style={{ marginTop: 16 }}>
              <div className="section-title">Ordre de priorité</div>
              {objectifsBrouillon.map((theme, i) => (
                <div className="info-row" key={theme}>
                  <span className="info-row__label">
                    {i + 1}. {LABELS_THEMES_OBJECTIFS[theme]}
                  </span>
                  <span>
                    <button
                      type="button"
                      className="icon-btn"
                      aria-label="Monter"
                      disabled={i === 0}
                      onClick={() => deplacerObjectif(i, -1)}
                    >
                      ↑
                    </button>
                    <button
                      type="button"
                      className="icon-btn"
                      aria-label="Descendre"
                      disabled={i === objectifsBrouillon.length - 1}
                      onClick={() => deplacerObjectif(i, 1)}
                    >
                      ↓
                    </button>
                  </span>
                </div>
              ))}
            </div>
          )}

          <LigneErreur message={editionErreur} />

          <div style={{ display: 'flex', gap: 8, marginTop: 20 }}>
            <button
              className="btn btn--ghost"
              style={{ flex: 1 }}
              disabled={enregistrement}
              onClick={() => setSectionOuverte(null)}
            >
              Annuler
            </button>
            <button
              className="btn btn--primary"
              style={{ flex: 1 }}
              disabled={enregistrement || objectifsBrouillon.length === 0}
              onClick={() =>
                void enregistrer({
                  // `poids` est recalculé côté backend à partir du rang : on envoie 0, jamais
                  // une valeur choisie ici (voir ApiObjectifV2).
                  objectifs_v2: objectifsBrouillon.map((theme, i) => ({ theme, rang: i + 1, poids: 0 })),
                })
              }
            >
              {enregistrement ? 'Enregistrement…' : 'Enregistrer et recalculer'}
            </button>
          </div>
        </section>
      )}

      <div className="section-title">Sport pratiqué</div>
      <div className="info-row">
        <span className="info-row__label">Sport</span>
        <span className="info-row__value">{profil.contexte_sportif?.sport ?? 'Aucun'}</span>
      </div>
      {profil.contexte_sportif?.sport === 'football' && (
        <div className="info-row">
          <span className="info-row__label">Poste joué</span>
          <span className="info-row__value">{profil.contexte_sportif?.poste ?? profil.poste ?? '—'}</span>
        </div>
      )}
      {profil.contexte_sportif?.frequence_hebdo != null && (
        <div className="info-row">
          <span className="info-row__label">Fréquence hebdo</span>
          <span className="info-row__value">{profil.contexte_sportif.frequence_hebdo}x / semaine</span>
        </div>
      )}

      <div className="section-title">Biométrie</div>
      <div className="info-row">
        <span className="info-row__label">Âge</span>
        <span className="info-row__value">{profil.age} ans</span>
      </div>
      <div className="info-row">
        <span className="info-row__label">Taille</span>
        <span className="info-row__value">{profil.taille_cm} cm</span>
      </div>
      <div className="info-row">
        <span className="info-row__label">Poids</span>
        <span className="info-row__value">{profil.poids_kg} kg</span>
      </div>

      <div className="section-title">Niveaux actuels</div>
      <div className="info-row">
        <span className="info-row__label">Physique</span>
        <span className="info-row__value">{profil.niveau_physique}</span>
      </div>
      <div className="info-row">
        <span className="info-row__label">Force</span>
        <span className="info-row__value">{profil.niveaux_qualites_physiques.force}/5</span>
      </div>
      <div className="info-row">
        <span className="info-row__label">Explosivité</span>
        <span className="info-row__value">{profil.niveaux_qualites_physiques.explosivite}/5</span>
      </div>
      <div className="info-row">
        <span className="info-row__label">Vitesse</span>
        <span className="info-row__value">{profil.niveaux_qualites_physiques.vitesse}/5</span>
      </div>
      <div className="info-row">
        <span className="info-row__label">Endurance</span>
        <span className="info-row__value">{profil.niveaux_qualites_physiques.endurance}/5</span>
      </div>

      <div className="section-title">Calendrier des matchs</div>
      <div className="info-row">
        <span className="info-row__label">Jour habituel</span>
        <span className="info-row__value">{profil.calendrier_matchs.jour_habituel ?? '—'}</span>
      </div>
      {profil.calendrier_matchs.entrainements_club && (
        <div className="info-row">
          <span className="info-row__label">Entraînements club</span>
          <span className="info-row__value">
            {profil.calendrier_matchs.entrainements_club.actif
              ? `${profil.calendrier_matchs.entrainements_club.seances_par_semaine ?? '—'} / semaine`
              : 'Aucun'}
          </span>
        </div>
      )}
      {profil.calendrier_matchs.exceptions.length > 0 && (
        <ul className="exception-list">
          {profil.calendrier_matchs.exceptions.map((e, i) => (
            <li key={`${e.date}-${i}`} className="exception-list__item">
              <span>
                {new Date(e.date).toLocaleDateString('fr-FR')}
                {e.label ? ` — ${e.label}` : ''}
              </span>
            </li>
          ))}
        </ul>
      )}

      {profil.objectif_esthetique &&
        (profil.objectif_esthetique.tags.length > 0 || profil.objectif_esthetique.texte_libre) && (
          <>
            <div className="section-title">Objectif esthétique</div>
            {profil.objectif_esthetique.tags.length > 0 && (
              <div className="tag-row">
                {profil.objectif_esthetique.tags.map((t) => (
                  <span className="tag" key={t}>
                    {t}
                  </span>
                ))}
              </div>
            )}
            {profil.objectif_esthetique.texte_libre && (
              <p className="subtle">{profil.objectif_esthetique.texte_libre}</p>
            )}
          </>
        )}

      <div className="section-title">Disponibilités</div>
      {profil.disponibilites && Object.values(profil.disponibilites).some((m) => m != null) ? (
        JOURS_DISPONIBILITES.map(({ key, label }) => (
          <div className="info-row" key={key}>
            <span className="info-row__label">{label}</span>
            <span className="info-row__value">
              {profil.disponibilites[key] != null ? `${profil.disponibilites[key]} min` : 'Indisponible'}
            </span>
          </div>
        ))
      ) : (
        <div className="info-row">
          <span className="info-row__label">Temps disponible</span>
          <span className="info-row__value">{profil.contraintes_temps ?? '—'}</span>
        </div>
      )}
      <div className="section-title">Matériel</div>
      <div className="info-row">
        <span className="info-row__label">Matériel</span>
        <span className="info-row__value">{profil.materiel}</span>
      </div>

      {sectionOuverte !== 'disponibilites' ? (
        <button
          className="btn btn--ghost"
          style={{ margin: '20px 0' }}
          onClick={() => ouvrirDisponibilites(profil)}
        >
          Modifier mes disponibilités et mon jour de match
        </button>
      ) : (
        <section className="card" style={{ margin: '20px 0' }}>
          <div className="card__eyebrow">Mes disponibilités</div>
          <p className="subtle" style={{ margin: '0 0 14px' }}>
            LEVEL ne place une séance que sur un jour disponible. Modifier ces réglages reconstruit
            ton planning des semaines à venir ; tes séances passées restent dans ton historique.
          </p>
          {JOURS_DISPONIBILITES.map(({ key, label }) => (
            <div key={key} className="onboarding-theme">
              <div className="section-title">{label}</div>
              <div className="tag-row tag-row--select">
                <button
                  type="button"
                  className={`tag tag--selectable ${dispoBrouillon[key] == null ? 'tag--active' : ''}`}
                  onClick={() => setDispoBrouillon((prev) => ({ ...prev, [key]: null }))}
                >
                  Indisponible
                </button>
                {OPTIONS_MINUTES.map((min) => (
                  <button
                    key={min}
                    type="button"
                    className={`tag tag--selectable ${dispoBrouillon[key] === min ? 'tag--active' : ''}`}
                    onClick={() => setDispoBrouillon((prev) => ({ ...prev, [key]: min }))}
                  >
                    {min} min
                  </button>
                ))}
              </div>
            </div>
          ))}

          <div className="card__eyebrow" style={{ marginTop: 20 }}>Jour de match habituel</div>
          <p className="subtle" style={{ margin: '0 0 10px' }}>
            LEVEL ne place jamais de séance un jour de match, et allège la veille.
          </p>
          <div className="tag-row tag-row--select">
            <button
              type="button"
              className={`tag tag--selectable ${jourMatchBrouillon === '' ? 'tag--active' : ''}`}
              onClick={() => setJourMatchBrouillon('')}
            >
              Aucun
            </button>
            {JOURS_MATCH.map((jour) => (
              <button
                key={jour}
                type="button"
                className={`tag tag--selectable ${jourMatchBrouillon === jour ? 'tag--active' : ''}`}
                onClick={() => setJourMatchBrouillon(jour)}
              >
                {jour}
              </button>
            ))}
          </div>

          <LigneErreur message={editionErreur} />

          <div style={{ display: 'flex', gap: 8, marginTop: 20 }}>
            <button
              className="btn btn--ghost"
              style={{ flex: 1 }}
              disabled={enregistrement}
              onClick={() => setSectionOuverte(null)}
            >
              Annuler
            </button>
            <button
              className="btn btn--primary"
              style={{ flex: 1 }}
              disabled={enregistrement}
              onClick={() =>
                void enregistrer({
                  disponibilites: dispoBrouillon,
                  // Les exceptions déjà saisies sont conservées telles quelles : on ne modifie
                  // ici que le jour habituel.
                  calendrier_matchs: {
                    ...profil.calendrier_matchs,
                    jour_habituel: jourMatchBrouillon || null,
                  },
                })
              }
            >
              {enregistrement ? 'Enregistrement…' : 'Enregistrer et recalculer'}
            </button>
          </div>
        </section>
      )}

      {stats && (
        <div className="stat-grid">
          <div className="stat-tile">
            <div className="stat-tile__value">{stats.total_seances}</div>
            <div className="stat-tile__label">Séances</div>
          </div>
          <div className="stat-tile">
            <div className="stat-tile__value">{stats.total_modules}</div>
            <div className="stat-tile__label">Modules</div>
          </div>
          <div className="stat-tile">
            <div className="stat-tile__value">{stats.record_streak}</div>
            <div className="stat-tile__label">Record streak</div>
          </div>
        </div>
      )}

      <DevDatePanel />

      <div className="section-title">Développement</div>
      <p className="subtle" style={{ marginBottom: 10 }}>
        Réinitialiser efface le profil, ton programme et relance l’onboarding. Pour changer
        d’objectif, d’emploi du temps ou de jour de match, utilise les modifications ci-dessus :
        elles conservent ton historique.
      </p>
      {!confirmingReset ? (
        <button
          className="btn btn--ghost"
          style={{ borderColor: 'var(--danger)', color: 'var(--danger)' }}
          onClick={() => setConfirmingReset(true)}
        >
          Réinitialiser le profil (relance l’onboarding)
        </button>
      ) : (
        <div className="card" style={{ borderColor: 'var(--danger)' }}>
          <p style={{ marginBottom: 14 }}>
            Supprimer ton profil et relancer l’onboarding ? Tu devras répondre à nouveau à toutes
            les questions et un nouveau programme sera construit.
          </p>
          <LigneErreur message={resetError} />
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              className="btn btn--ghost"
              style={{ flex: 1 }}
              disabled={resetting}
              onClick={() => {
                setConfirmingReset(false);
                setResetError(null);
              }}
            >
              Annuler
            </button>
            <button
              className="btn btn--primary"
              style={{ flex: 1, background: 'var(--danger)' }}
              disabled={resetting}
              onClick={handleReset}
            >
              {resetting ? 'Suppression…' : 'Confirmer'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
