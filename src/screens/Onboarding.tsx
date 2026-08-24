import { useState } from 'react';
import { saveProfil } from '../api/client';
import type { ApiCalendrierException, ApiProfil, ApiQualitesPhysiques } from '../api/client';

interface OnboardingProps {
  onDone: (profil: ApiProfil) => void;
}

const OBJECTIFS = ['Force', 'Endurance', 'Perte de poids', 'Discipline mentale', 'Culture générale'];
const POSTES = ['Gardien', 'Défenseur', 'Milieu', 'Attaquant'];
const QUALITES: { key: keyof ApiQualitesPhysiques; label: string }[] = [
  { key: 'force', label: 'Force' },
  { key: 'explosivite', label: 'Explosivité' },
  { key: 'vitesse', label: 'Vitesse' },
  { key: 'endurance', label: 'Endurance' },
];
const THEMES_INTELLECTUELS = ['Culture générale', 'Économie', 'Histoire', 'Sciences'];
const NIVEAUX_INTELLECTUELS = ['Débutant', 'Intermédiaire', 'Avancé'];
const JOURS_SEMAINE = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche'];
const JOURS = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim'];
const DUREES = ['15 min', '30 min', '45 min', '60 min'];
const MATERIELS = ['Aucun', 'Poids du corps', 'Haltères', 'Salle complète'];
const TAGS_ESTHETIQUES = ['Bras', 'Épaules', 'Abdos', 'Dos', 'Jambes', 'Silhouette générale'];

const TOTAL_STEPS = 8;

function niveauPhysiqueAuto(qualites: ApiQualitesPhysiques): string {
  const moyenne = (qualites.force + qualites.explosivite + qualites.vitesse + qualites.endurance) / 4;
  if (moyenne <= 2) return 'Débutant';
  if (moyenne <= 3.5) return 'Intermédiaire';
  return 'Avancé';
}

export default function Onboarding({ onDone }: OnboardingProps) {
  const [step, setStep] = useState(0);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [objectifs, setObjectifs] = useState<string[]>([]);
  const [poste, setPoste] = useState('');
  const [qualites, setQualites] = useState<ApiQualitesPhysiques>({
    force: 0,
    explosivite: 0,
    vitesse: 0,
    endurance: 0,
  });
  const [niveauxIntellectuels, setNiveauxIntellectuels] = useState<Record<string, string>>({});
  const [jourHabituel, setJourHabituel] = useState('');
  const [exceptions, setExceptions] = useState<ApiCalendrierException[]>([]);
  const [exceptionDate, setExceptionDate] = useState('');
  const [exceptionLabel, setExceptionLabel] = useState('');
  const [jours, setJours] = useState<string[]>([]);
  const [duree, setDuree] = useState('');
  const [materiel, setMateriel] = useState('');
  const [tagsEsthetiques, setTagsEsthetiques] = useState<string[]>([]);
  const [texteEsthetique, setTexteEsthetique] = useState('');

  const toggle = (list: string[], value: string, setter: (v: string[]) => void) => {
    setter(list.includes(value) ? list.filter((v) => v !== value) : [...list, value]);
  };

  function addException() {
    if (!exceptionDate) return;
    setExceptions((prev) => [...prev, { date: exceptionDate, label: exceptionLabel || undefined }]);
    setExceptionDate('');
    setExceptionLabel('');
  }

  function removeException(index: number) {
    setExceptions((prev) => prev.filter((_, i) => i !== index));
  }

  const canContinue = (() => {
    switch (step) {
      case 0:
        return objectifs.length > 0;
      case 1:
        return poste !== '';
      case 2:
        return QUALITES.every((q) => qualites[q.key] > 0);
      case 3:
        return THEMES_INTELLECTUELS.every((t) => niveauxIntellectuels[t]);
      case 4:
        return jourHabituel !== '' || exceptions.length > 0;
      case 5:
        return jours.length > 0 && duree !== '';
      case 6:
        return materiel !== '';
      case 7:
        return true; // étape optionnelle
      default:
        return false;
    }
  })();

  const handleSubmit = async () => {
    setSaving(true);
    setError(null);
    try {
      const niveauIntellectuel = THEMES_INTELLECTUELS.map(
        (t) => `${t}: ${niveauxIntellectuels[t]}`
      ).join(', ');
      const contraintesTemps = `${jours.join('/')} · ${duree}/séance`;
      const hasEsthetique = tagsEsthetiques.length > 0 || texteEsthetique.trim() !== '';

      const profil = await saveProfil({
        objectifs,
        poste,
        niveau_physique: niveauPhysiqueAuto(qualites),
        niveaux_qualites_physiques: qualites,
        niveau_intellectuel: niveauIntellectuel,
        calendrier_matchs: {
          jour_habituel: jourHabituel || null,
          exceptions,
        },
        objectif_esthetique: hasEsthetique
          ? { tags: tagsEsthetiques, texte_libre: texteEsthetique.trim() || undefined }
          : null,
        contraintes_temps: contraintesTemps,
        materiel,
      });
      onDone(profil);
    } catch {
      setError("Impossible d'enregistrer le profil. Réessaie.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="screen">
      <div className="onboarding-progress">
        {Array.from({ length: TOTAL_STEPS }).map((_, i) => (
          <div key={i} className={`onboarding-progress__dot ${i <= step ? 'active' : ''}`} />
        ))}
      </div>

      {step === 0 && (
        <section>
          <h1 className="page-title">Tes objectifs</h1>
          <p className="subtle">Choisis un ou plusieurs objectifs.</p>
          <div className="tag-row tag-row--select">
            {OBJECTIFS.map((o) => (
              <button
                key={o}
                type="button"
                className={`tag tag--selectable ${objectifs.includes(o) ? 'tag--active' : ''}`}
                onClick={() => toggle(objectifs, o, setObjectifs)}
              >
                {o}
              </button>
            ))}
          </div>
        </section>
      )}

      {step === 1 && (
        <section>
          <h1 className="page-title">Poste joué</h1>
          <p className="subtle">Sur le terrain, tu joues plutôt…</p>
          <div className="option-list">
            {POSTES.map((p) => (
              <button
                key={p}
                type="button"
                className={`option-item ${poste === p ? 'option-item--active' : ''}`}
                onClick={() => setPoste(p)}
              >
                {p}
              </button>
            ))}
          </div>
        </section>
      )}

      {step === 2 && (
        <section>
          <h1 className="page-title">Niveau physique actuel</h1>
          <p className="subtle">Pour chaque qualité, de 1 (faible) à 5 (élevé).</p>
          {QUALITES.map(({ key, label }) => (
            <div key={key} className="onboarding-theme">
              <div className="section-title">{label}</div>
              <div className="rpe-grid" style={{ gridTemplateColumns: 'repeat(5, 1fr)' }}>
                {[1, 2, 3, 4, 5].map((val) => (
                  <button
                    key={val}
                    type="button"
                    className={`rpe-btn ${qualites[key] === val ? 'selected' : ''}`}
                    onClick={() => setQualites((prev) => ({ ...prev, [key]: val }))}
                  >
                    {val}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </section>
      )}

      {step === 3 && (
        <section>
          <h1 className="page-title">Niveau intellectuel souhaité</h1>
          <p className="subtle">Par thème.</p>
          {THEMES_INTELLECTUELS.map((theme) => (
            <div key={theme} className="onboarding-theme">
              <div className="section-title">{theme}</div>
              <div className="tag-row tag-row--select">
                {NIVEAUX_INTELLECTUELS.map((n) => (
                  <button
                    key={n}
                    type="button"
                    className={`tag tag--selectable ${
                      niveauxIntellectuels[theme] === n ? 'tag--active' : ''
                    }`}
                    onClick={() =>
                      setNiveauxIntellectuels((prev) => ({ ...prev, [theme]: n }))
                    }
                  >
                    {n}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </section>
      )}

      {step === 4 && (
        <section>
          <h1 className="page-title">Calendrier des matchs</h1>
          <p className="subtle">Jour de match habituel</p>
          <div className="option-list">
            {JOURS_SEMAINE.map((j) => (
              <button
                key={j}
                type="button"
                className={`option-item ${jourHabituel === j ? 'option-item--active' : ''}`}
                onClick={() => setJourHabituel(jourHabituel === j ? '' : j)}
              >
                {j}
              </button>
            ))}
          </div>

          <p className="subtle" style={{ marginTop: 20 }}>
            Exceptions ponctuelles (match reporté, tournoi…)
          </p>
          <div className="exception-form">
            <input
              type="date"
              className="textarea exception-form__date"
              value={exceptionDate}
              onChange={(e) => setExceptionDate(e.target.value)}
            />
            <input
              type="text"
              className="textarea exception-form__label"
              placeholder="Libellé (optionnel)"
              value={exceptionLabel}
              onChange={(e) => setExceptionLabel(e.target.value)}
            />
            <button type="button" className="btn btn--ghost btn--sm" onClick={addException} disabled={!exceptionDate}>
              Ajouter
            </button>
          </div>

          {exceptions.length > 0 && (
            <ul className="exception-list">
              {exceptions.map((e, i) => (
                <li key={`${e.date}-${i}`} className="exception-list__item">
                  <span>
                    {new Date(e.date).toLocaleDateString('fr-FR')}
                    {e.label ? ` — ${e.label}` : ''}
                  </span>
                  <button type="button" onClick={() => removeException(i)} aria-label="Supprimer">
                    ×
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {step === 5 && (
        <section>
          <h1 className="page-title">Contraintes de temps</h1>
          <p className="subtle">Jours disponibles</p>
          <div className="tag-row tag-row--select">
            {JOURS.map((j) => (
              <button
                key={j}
                type="button"
                className={`tag tag--selectable ${jours.includes(j) ? 'tag--active' : ''}`}
                onClick={() => toggle(jours, j, setJours)}
              >
                {j}
              </button>
            ))}
          </div>
          <p className="subtle" style={{ marginTop: 20 }}>
            Durée par séance
          </p>
          <div className="option-list">
            {DUREES.map((d) => (
              <button
                key={d}
                type="button"
                className={`option-item ${duree === d ? 'option-item--active' : ''}`}
                onClick={() => setDuree(d)}
              >
                {d}
              </button>
            ))}
          </div>
        </section>
      )}

      {step === 6 && (
        <section>
          <h1 className="page-title">Matériel disponible</h1>
          <div className="option-list">
            {MATERIELS.map((m) => (
              <button
                key={m}
                type="button"
                className={`option-item ${materiel === m ? 'option-item--active' : ''}`}
                onClick={() => setMateriel(m)}
              >
                {m}
              </button>
            ))}
          </div>
        </section>
      )}

      {step === 7 && (
        <section>
          <h1 className="page-title">Objectif esthétique</h1>
          <p className="subtle">Optionnel — zones à travailler en priorité.</p>
          <div className="tag-row tag-row--select">
            {TAGS_ESTHETIQUES.map((t) => (
              <button
                key={t}
                type="button"
                className={`tag tag--selectable ${tagsEsthetiques.includes(t) ? 'tag--active' : ''}`}
                onClick={() => toggle(tagsEsthetiques, t, setTagsEsthetiques)}
              >
                {t}
              </button>
            ))}
          </div>
          <textarea
            className="textarea"
            style={{ marginTop: 14 }}
            placeholder="Précision libre (optionnel)…"
            value={texteEsthetique}
            onChange={(e) => setTexteEsthetique(e.target.value)}
          />
        </section>
      )}

      {error && <p className="subtle" style={{ color: 'var(--danger)' }}>{error}</p>}

      <div className="onboarding-actions">
        {step > 0 && (
          <button
            type="button"
            className="btn btn--ghost"
            onClick={() => setStep((s) => s - 1)}
            disabled={saving}
          >
            Retour
          </button>
        )}
        {step < TOTAL_STEPS - 1 ? (
          <button
            type="button"
            className="btn btn--primary"
            disabled={!canContinue}
            onClick={() => setStep((s) => s + 1)}
          >
            Continuer
          </button>
        ) : (
          <button
            type="button"
            className="btn btn--primary"
            disabled={!canContinue || saving}
            onClick={handleSubmit}
          >
            {saving ? 'Enregistrement…' : 'Terminer'}
          </button>
        )}
      </div>
    </div>
  );
}
