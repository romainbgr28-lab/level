import { useEffect, useState } from 'react';
import Header from '../components/Header';
import { deleteProfil, getProfil, getStats, patchProfil } from '../api/client';
import type { ApiDisponibilites, ApiProfil, ApiStats } from '../api/client';
import DevDatePanel from '../components/DevDatePanel';
import { LABELS_THEMES_OBJECTIFS, JOURS_DISPONIBILITES, OPTIONS_MINUTES } from './Onboarding';

// Jour de match habituel : nom complet capitalisé, format attendu par
// calendrier_matchs.jour_habituel (backend/regles_seance.py::JOURS_SEMAINE). Ne pas confondre
// avec les clés minuscules de `disponibilites`.
const JOURS_MATCH = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche'];

export default function Profile() {
  const [profil, setProfil] = useState<ApiProfil | null>(null);
  const [stats, setStats] = useState<ApiStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [resetting, setResetting] = useState(false);
  const [confirmingReset, setConfirmingReset] = useState(false);
  const [resetError, setResetError] = useState<string | null>(null);

  // ---- Édition des réglages qui pilotent réellement le programme ----
  // Disponibilités et jour de match sont les entrées de la structure hebdomadaire : sans moyen
  // de les corriger, un changement d'emploi du temps obligeait à réinitialiser tout le profil.
  const [editionOuverte, setEditionOuverte] = useState(false);
  const [dispoBrouillon, setDispoBrouillon] = useState<ApiDisponibilites>({});
  const [jourMatchBrouillon, setJourMatchBrouillon] = useState<string>('');
  const [enregistrement, setEnregistrement] = useState(false);
  const [editionErreur, setEditionErreur] = useState<string | null>(null);
  const [editionConfirmee, setEditionConfirmee] = useState(false);

  function ouvrirEdition(p: ApiProfil) {
    const base: ApiDisponibilites = {};
    for (const { key } of JOURS_DISPONIBILITES) base[key] = p.disponibilites?.[key] ?? null;
    setDispoBrouillon(base);
    setJourMatchBrouillon(p.calendrier_matchs.jour_habituel ?? '');
    setEditionErreur(null);
    setEditionConfirmee(false);
    setEditionOuverte(true);
  }

  async function enregistrerEdition(p: ApiProfil) {
    setEnregistrement(true);
    setEditionErreur(null);
    try {
      const misAJour = await patchProfil({
        disponibilites: dispoBrouillon,
        // Les exceptions déjà saisies sont conservées telles quelles : on ne modifie ici que
        // le jour habituel.
        calendrier_matchs: { ...p.calendrier_matchs, jour_habituel: jourMatchBrouillon || null },
      });
      setProfil(misAJour);
      setEditionOuverte(false);
      setEditionConfirmee(true);
    } catch (e) {
      setEditionErreur(e instanceof Error ? e.message : 'Enregistrement impossible.');
    } finally {
      setEnregistrement(false);
    }
  }

  useEffect(() => {
    Promise.all([getProfil(), getStats()])
      .then(([p, s]) => {
        setProfil(p);
        setStats(s);
      })
      .finally(() => setLoading(false));
  }, []);

  async function handleReset() {
    setResetting(true);
    setResetError(null);
    try {
      await deleteProfil();
      window.location.reload();
    } catch (e) {
      setResetError(e instanceof Error ? e.message : 'Erreur lors de la réinitialisation.');
      setResetting(false);
    }
  }

  if (loading) {
    return (
      <div className="screen">
        <Header title="Profil" />
        <p className="subtle">Chargement…</p>
      </div>
    );
  }

  if (!profil) {
    return (
      <div className="screen">
        <Header title="Profil" />
        <p className="subtle">Aucun profil enregistré.</p>
      </div>
    );
  }

  return (
    <div className="screen">
      <Header title="Profil" />
      <h1 className="page-title">Profil</h1>

      <div className="section-title">Objectifs</div>
      <div className="tag-row">
        {(profil.objectifs_v2 ?? []).length > 0
          ? [...profil.objectifs_v2]
              .sort((a, b) => a.rang - b.rang)
              .map((o) => (
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

      {editionConfirmee && (
        <p className="subtle" style={{ marginTop: 16 }}>
          Réglages enregistrés — ton programme a été reconstruit en conséquence.
        </p>
      )}

      {!editionOuverte ? (
        <button className="btn btn--ghost" style={{ margin: '20px 0' }} onClick={() => ouvrirEdition(profil)}>
          Modifier mes disponibilités et mon jour de match
        </button>
      ) : (
        <section className="card" style={{ margin: '20px 0' }}>
          <div className="card__eyebrow">Mes disponibilités</div>
          <p className="subtle" style={{ margin: '0 0 14px' }}>
            LEVEL ne place une séance que sur un jour disponible. Modifier ces réglages reconstruit
            ton programme.
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

          {editionErreur && (
            <p className="subtle" style={{ color: 'var(--danger)', margin: '14px 0 0' }}>
              {editionErreur}
            </p>
          )}

          <div style={{ display: 'flex', gap: 8, marginTop: 20 }}>
            <button
              className="btn btn--ghost"
              style={{ flex: 1 }}
              disabled={enregistrement}
              onClick={() => setEditionOuverte(false)}
            >
              Annuler
            </button>
            <button
              className="btn btn--primary"
              style={{ flex: 1 }}
              disabled={enregistrement}
              onClick={() => void enregistrerEdition(profil)}
            >
              {enregistrement ? 'Enregistrement…' : 'Enregistrer'}
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
        Réinitialiser efface le profil et relance l'onboarding. Pour un simple changement
        d'emploi du temps ou de jour de match, utilise plutôt l'édition ci-dessus.
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
          <p style={{ marginBottom: 14 }}>Supprimer le profil et relancer l’onboarding ?</p>
          {resetError && (
            <p className="subtle" style={{ color: 'var(--danger)', marginBottom: 12 }}>
              {resetError}
            </p>
          )}
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
