import { useState } from 'react';
import { saveProfil } from '../api/client';
import type { ApiProfil } from '../api/client';

interface OnboardingProps {
  onDone: (profil: ApiProfil) => void;
}

const OBJECTIFS = ['Force', 'Endurance', 'Perte de poids', 'Discipline mentale', 'Culture générale'];
const NIVEAUX_PHYSIQUES = ['Débutant', 'Intermédiaire', 'Avancé'];
const THEMES_INTELLECTUELS = ['Culture générale', 'Économie', 'Histoire', 'Sciences'];
const NIVEAUX_INTELLECTUELS = ['Débutant', 'Intermédiaire', 'Avancé'];
const JOURS = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim'];
const DUREES = ['15 min', '30 min', '45 min', '60 min'];
const MATERIELS = ['Aucun', 'Poids du corps', 'Haltères', 'Salle complète'];

const TOTAL_STEPS = 5;

export default function Onboarding({ onDone }: OnboardingProps) {
  const [step, setStep] = useState(0);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [objectifs, setObjectifs] = useState<string[]>([]);
  const [niveauPhysique, setNiveauPhysique] = useState('');
  const [niveauxIntellectuels, setNiveauxIntellectuels] = useState<Record<string, string>>({});
  const [jours, setJours] = useState<string[]>([]);
  const [duree, setDuree] = useState('');
  const [materiel, setMateriel] = useState('');

  const toggle = (list: string[], value: string, setter: (v: string[]) => void) => {
    setter(list.includes(value) ? list.filter((v) => v !== value) : [...list, value]);
  };

  const canContinue = (() => {
    switch (step) {
      case 0:
        return objectifs.length > 0;
      case 1:
        return niveauPhysique !== '';
      case 2:
        return THEMES_INTELLECTUELS.every((t) => niveauxIntellectuels[t]);
      case 3:
        return jours.length > 0 && duree !== '';
      case 4:
        return materiel !== '';
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

      const profil = await saveProfil({
        objectifs,
        niveau_physique: niveauPhysique,
        niveau_intellectuel: niveauIntellectuel,
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
          <h1 className="page-title">Niveau physique actuel</h1>
          <p className="subtle">Où en es-tu aujourd'hui ?</p>
          <div className="option-list">
            {NIVEAUX_PHYSIQUES.map((n) => (
              <button
                key={n}
                type="button"
                className={`option-item ${niveauPhysique === n ? 'option-item--active' : ''}`}
                onClick={() => setNiveauPhysique(n)}
              >
                {n}
              </button>
            ))}
          </div>
        </section>
      )}

      {step === 2 && (
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

      {step === 3 && (
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

      {step === 4 && (
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
