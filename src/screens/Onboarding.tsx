import { useState } from 'react';
import { saveProfil, genererProgramme } from '../api/client';
import type { ApiCalendrierException, ApiProfil, ApiQualitesPhysiques } from '../api/client';

interface OnboardingProps {
  onDone: (profil: ApiProfil) => void;
}

const OBJECTIFS = ['Force', 'Endurance', 'Perte de poids', 'Discipline mentale'];
const POSTES = ['Gardien', 'Défenseur', 'Milieu', 'Attaquant'];
const QUALITES: { key: keyof ApiQualitesPhysiques; label: string }[] = [
  { key: 'force', label: 'Force' },
  { key: 'explosivite', label: 'Explosivité' },
  { key: 'vitesse', label: 'Vitesse' },
  { key: 'endurance', label: 'Endurance' },
];
const JOURS_SEMAINE = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche'];
const JOURS = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim'];
const DUREES = ['15 min', '30 min', '45 min', '60 min'];
const MATERIELS = ['Aucun', 'Poids du corps', 'Haltères', 'Salle complète'];
const TAGS_ESTHETIQUES = ['Bras', 'Épaules', 'Abdos', 'Dos', 'Jambes', 'Silhouette générale'];

const TOTAL_STEPS = 7;

function niveauPhysiqueAuto(qualites: ApiQualitesPhysiques): string {
  const moyenne = (qualites.force + qualites.explosivite + qualites.vitesse + qualites.endurance) / 4;
  if (moyenne <= 2) return 'Débutant';
  if (moyenne <= 3.5) return 'Intermédiaire';
  return 'Avancé';
}

/** Case cochable carrée : plusieurs sélections possibles sur l'étape. */
function CheckboxItem({ label, selected, onClick }: { label: string; selected: boolean; onClick: () => void }) {
  return (
    <button type="button" className={`choice-item ${selected ? 'selected' : ''}`} onClick={onClick}>
      <span className="choice-item__indicator choice-item__indicator--checkbox">
        {selected && (
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="3.5">
            <path d="M5 13l4 4L19 7" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        )}
      </span>
      {label}
    </button>
  );
}

/** Bouton rond : une seule sélection possible sur l'étape. */
function RadioItem({ label, selected, onClick }: { label: string; selected: boolean; onClick: () => void }) {
  return (
    <button type="button" className={`choice-item ${selected ? 'selected' : ''}`} onClick={onClick}>
      <span className="choice-item__indicator choice-item__indicator--radio">
        {selected && <span className="choice-item__dot" />}
      </span>
      {label}
    </button>
  );
}

export default function Onboarding({ onDone }: OnboardingProps) {
  const [step, setStep] = useState(0);
  const [saving, setSaving] = useState(false);
  const [generatingProgramme, setGeneratingProgramme] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [objectifs, setObjectifs] = useState<string[]>([]);
  const [poste, setPoste] = useState('');
  const [age, setAge] = useState('');
  const [tailleCm, setTailleCm] = useState('');
  const [poidsKg, setPoidsKg] = useState('');
  const [qualites, setQualites] = useState<ApiQualitesPhysiques>({
    force: 0,
    explosivite: 0,
    vitesse: 0,
    endurance: 0,
  });
  const [jourHabituel, setJourHabituel] = useState('');
  const [exceptions, setExceptions] = useState<ApiCalendrierException[]>([]);
  const [exceptionDate, setExceptionDate] = useState('');
  const [exceptionLabel, setExceptionLabel] = useState('');
  const [clubActif, setClubActif] = useState<'' | 'oui' | 'non'>('');
  const [seancesClub, setSeancesClub] = useState('');
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
        return (
          Number(age) > 0 &&
          Number(tailleCm) > 0 &&
          Number(poidsKg) > 0 &&
          QUALITES.every((q) => qualites[q.key] > 0)
        );
      case 3:
        return (
          (jourHabituel !== '' || exceptions.length > 0) &&
          clubActif !== '' &&
          (clubActif === 'non' || Number(seancesClub) > 0)
        );
      case 4:
        return jours.length > 0 && duree !== '';
      case 5:
        return materiel !== '';
      case 6:
        return true; // étape optionnelle
      default:
        return false;
    }
  })();

  const handleSubmit = async () => {
    setSaving(true);
    setError(null);
    try {
      const contraintesTemps = `${jours.join('/')} · ${duree}/séance`;
      const hasEsthetique = tagsEsthetiques.length > 0 || texteEsthetique.trim() !== '';

      const profil = await saveProfil({
        objectifs,
        poste,
        age: Number(age),
        taille_cm: Number(tailleCm),
        poids_kg: Number(poidsKg),
        niveau_physique: niveauPhysiqueAuto(qualites),
        niveaux_qualites_physiques: qualites,
        calendrier_matchs: {
          jour_habituel: jourHabituel || null,
          exceptions,
          entrainements_club: {
            actif: clubActif === 'oui',
            seances_par_semaine: clubActif === 'oui' ? Number(seancesClub) : null,
          },
        },
        objectif_esthetique: hasEsthetique
          ? { tags: tagsEsthetiques, texte_libre: texteEsthetique.trim() || undefined }
          : null,
        contraintes_temps: contraintesTemps,
        materiel,
      });

      setGeneratingProgramme(true);
      try {
        await genererProgramme();
      } catch {
        // La génération du programme ne doit pas bloquer l'entrée dans l'app :
        // le profil est déjà enregistré, l'utilisateur peut continuer sans programme.
      } finally {
        setGeneratingProgramme(false);
      }

      onDone(profil);
    } catch (e) {
      const detail = e instanceof Error ? e.message : '';
      setError(`Impossible d'enregistrer le profil. ${detail}`);
    } finally {
      setSaving(false);
    }
  };

  if (generatingProgramme) {
    return (
      <div className="screen">
        <div className="onboarding-loading">
          <p className="page-title">Construction de ton programme personnalisé…</p>
        </div>
      </div>
    );
  }

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
          <p className="subtle">Plusieurs choix possibles.</p>
          <div className="choice-list">
            {OBJECTIFS.map((o) => (
              <CheckboxItem key={o} label={o} selected={objectifs.includes(o)} onClick={() => toggle(objectifs, o, setObjectifs)} />
            ))}
          </div>
        </section>
      )}

      {step === 1 && (
        <section>
          <h1 className="page-title">Poste joué</h1>
          <p className="subtle">Un seul choix.</p>
          <div className="choice-list">
            {POSTES.map((p) => (
              <RadioItem key={p} label={p} selected={poste === p} onClick={() => setPoste(p)} />
            ))}
          </div>
        </section>
      )}

      {step === 2 && (
        <section>
          <h1 className="page-title">Niveau physique actuel</h1>

          <p className="subtle">Âge, taille et poids — utilisés pour calculer tes charges de départ.</p>
          <div className="onboarding-theme">
            <div className="section-title">Âge</div>
            <input
              type="number"
              min={10}
              max={90}
              className="textarea"
              style={{ minHeight: 'unset', padding: 12 }}
              placeholder="Âge (années)"
              value={age}
              onChange={(e) => setAge(e.target.value)}
            />
          </div>
          <div className="onboarding-theme">
            <div className="section-title">Taille (cm)</div>
            <input
              type="number"
              min={100}
              max={230}
              className="textarea"
              style={{ minHeight: 'unset', padding: 12 }}
              placeholder="Taille en cm"
              value={tailleCm}
              onChange={(e) => setTailleCm(e.target.value)}
            />
          </div>
          <div className="onboarding-theme">
            <div className="section-title">Poids (kg)</div>
            <input
              type="number"
              min={30}
              max={200}
              step="0.1"
              className="textarea"
              style={{ minHeight: 'unset', padding: 12 }}
              placeholder="Poids en kg"
              value={poidsKg}
              onChange={(e) => setPoidsKg(e.target.value)}
            />
          </div>

          <p className="subtle" style={{ marginTop: 20 }}>Pour chaque qualité, de 1 (faible) à 5 (élevé).</p>
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
          <h1 className="page-title">Calendrier des matchs</h1>
          <p className="subtle">Jour de match habituel — un seul choix.</p>
          <div className="choice-list">
            {JOURS_SEMAINE.map((j) => (
              <RadioItem
                key={j}
                label={j}
                selected={jourHabituel === j}
                onClick={() => setJourHabituel(jourHabituel === j ? '' : j)}
              />
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

          <p className="subtle" style={{ marginTop: 20 }}>
            As-tu des entraînements club en plus des matchs ? Un seul choix.
          </p>
          <div className="choice-list" style={{ marginBottom: clubActif === 'oui' ? 14 : 0 }}>
            <RadioItem label="Oui" selected={clubActif === 'oui'} onClick={() => setClubActif('oui')} />
            <RadioItem
              label="Non"
              selected={clubActif === 'non'}
              onClick={() => {
                setClubActif('non');
                setSeancesClub('');
              }}
            />
          </div>
          {clubActif === 'oui' && (
            <input
              type="number"
              min={1}
              max={14}
              className="textarea"
              style={{ minHeight: 'unset', padding: 12 }}
              placeholder="Nombre de séances par semaine"
              value={seancesClub}
              onChange={(e) => setSeancesClub(e.target.value)}
            />
          )}
        </section>
      )}

      {step === 4 && (
        <section>
          <h1 className="page-title">Contraintes de temps</h1>
          <p className="subtle">Jours disponibles — plusieurs choix possibles.</p>
          <div className="choice-list choice-list--grid" style={{ gap: 10 }}>
            {JOURS.map((j) => (
              <CheckboxItem key={j} label={j} selected={jours.includes(j)} onClick={() => toggle(jours, j, setJours)} />
            ))}
          </div>
          <p className="subtle" style={{ marginTop: 20 }}>
            Durée par séance — un seul choix.
          </p>
          <div className="choice-list">
            {DUREES.map((d) => (
              <RadioItem key={d} label={d} selected={duree === d} onClick={() => setDuree(d)} />
            ))}
          </div>
        </section>
      )}

      {step === 5 && (
        <section>
          <h1 className="page-title">Matériel disponible</h1>
          <p className="subtle">Un seul choix.</p>
          <div className="choice-list">
            {MATERIELS.map((m) => (
              <RadioItem key={m} label={m} selected={materiel === m} onClick={() => setMateriel(m)} />
            ))}
          </div>
        </section>
      )}

      {step === 6 && (
        <section>
          <h1 className="page-title">Objectif esthétique</h1>
          <p className="subtle">Optionnel — zones à travailler en priorité, plusieurs choix possibles.</p>
          <div className="choice-list choice-list--grid" style={{ gap: 10 }}>
            {TAGS_ESTHETIQUES.map((t) => (
              <CheckboxItem
                key={t}
                label={t}
                selected={tagsEsthetiques.includes(t)}
                onClick={() => toggle(tagsEsthetiques, t, setTagsEsthetiques)}
              />
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
