import { useMemo, useState } from 'react';
import { saveProfil, genererProgramme } from '../api/client';
import type {
  ApiCalendrierException,
  ApiProfil,
  ApiQualitesPhysiques,
  ApiDisponibilites,
  ThemeObjectifV2,
} from '../api/client';

interface OnboardingProps {
  onDone: (profil: ApiProfil) => void;
}

// ---------- User Model V2 : objectifs hiérarchisés ----------
// Thèmes techniques envoyés au backend (voir backend/user_model_v2.THEMES_OBJECTIFS_V2) — le
// frontend affiche LABELS_THEMES_OBJECTIFS, jamais ces identifiants bruts.
const THEMES_OBJECTIFS: ThemeObjectifV2[] = [
  'force',
  'esthetique_hypertrophie',
  'perte_de_gras',
  'performance_sport_pratique',
  'endurance',
  'discipline_mentale',
];

export const LABELS_THEMES_OBJECTIFS: Record<ThemeObjectifV2, string> = {
  force: 'Force',
  esthetique_hypertrophie: 'Esthétique / Hypertrophie',
  perte_de_gras: 'Perte de gras',
  performance_sport_pratique: 'Performance dans mon sport',
  endurance: 'Endurance',
  discipline_mentale: 'Discipline mentale',
};

const MAX_OBJECTIFS = 3;

const POSTES = ['Gardien', 'Défenseur', 'Milieu', 'Attaquant'];
const QUALITES: { key: keyof ApiQualitesPhysiques; label: string }[] = [
  { key: 'force', label: 'Force' },
  { key: 'explosivite', label: 'Explosivité' },
  { key: 'vitesse', label: 'Vitesse' },
  { key: 'endurance', label: 'Endurance' },
];
const JOURS_SEMAINE = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche'];

// Disponibilités structurées (Phase 3) : clé backend (minuscule, sans accent) + libellé
// d'affichage. Exporté pour réutilisation en lecture par Profile.tsx.
export const JOURS_DISPONIBILITES: { key: string; label: string }[] = [
  { key: 'lundi', label: 'Lundi' },
  { key: 'mardi', label: 'Mardi' },
  { key: 'mercredi', label: 'Mercredi' },
  { key: 'jeudi', label: 'Jeudi' },
  { key: 'vendredi', label: 'Vendredi' },
  { key: 'samedi', label: 'Samedi' },
  { key: 'dimanche', label: 'Dimanche' },
];
const OPTIONS_MINUTES = [15, 30, 45, 60, 90];
const MATERIELS = ['Aucun', 'Poids du corps', 'Haltères', 'Salle complète'];
const TAGS_ESTHETIQUES = ['Bras', 'Épaules', 'Abdos', 'Dos', 'Jambes', 'Silhouette générale'];

function niveauPhysiqueAuto(qualites: ApiQualitesPhysiques): string {
  const moyenne = (qualites.force + qualites.explosivite + qualites.vitesse + qualites.endurance) / 4;
  if (moyenne <= 2) return 'Débutant';
  if (moyenne <= 3.5) return 'Intermédiaire';
  return 'Avancé';
}

function disponibilitesVides(): ApiDisponibilites {
  return Object.fromEntries(JOURS_DISPONIBILITES.map((j) => [j.key, null]));
}

/** Case cochable carrée : plusieurs sélections possibles sur l'étape. */
function CheckboxItem({ label, selected, onClick, disabled }: { label: string; selected: boolean; onClick: () => void; disabled?: boolean }) {
  return (
    <button type="button" className={`choice-item ${selected ? 'selected' : ''}`} onClick={onClick} disabled={disabled}>
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

type SportChoice = 'aucun' | 'football' | 'autre';

export default function Onboarding({ onDone }: OnboardingProps) {
  const [step, setStep] = useState(0);
  const [saving, setSaving] = useState(false);
  const [generatingProgramme, setGeneratingProgramme] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // --- 1. Contexte sportif (sport pratiqué != objectif, voir user_model_v2.py) ---
  const [sportChoice, setSportChoice] = useState<SportChoice>('aucun');
  const [autreSportTexte, setAutreSportTexte] = useState('');
  const [poste, setPoste] = useState('');
  const [frequenceHebdo, setFrequenceHebdo] = useState('');

  // --- 2. Objectifs hiérarchisés (1 à 3, classés — poids calculés côté backend) ---
  const [objectifsRanges, setObjectifsRanges] = useState<ThemeObjectifV2[]>([]);

  // --- 3. Niveau perçu (biométrie + qualités déclarées, non objectif) ---
  const [age, setAge] = useState('');
  const [tailleCm, setTailleCm] = useState('');
  const [poidsKg, setPoidsKg] = useState('');
  const [qualites, setQualites] = useState<ApiQualitesPhysiques>({
    force: 0,
    explosivite: 0,
    vitesse: 0,
    endurance: 0,
  });

  // --- 4. Matériel ---
  const [materiel, setMateriel] = useState('');

  // --- 5. Disponibilités structurées ---
  const [disponibilites, setDisponibilites] = useState<ApiDisponibilites>(disponibilitesVides());

  // --- 6. Reste des champs existants ---
  const [jourHabituel, setJourHabituel] = useState('');
  const [exceptions, setExceptions] = useState<ApiCalendrierException[]>([]);
  const [exceptionDate, setExceptionDate] = useState('');
  const [exceptionLabel, setExceptionLabel] = useState('');
  const [clubActif, setClubActif] = useState<'' | 'oui' | 'non'>('');
  const [seancesClub, setSeancesClub] = useState('');
  const [tagsEsthetiques, setTagsEsthetiques] = useState<string[]>([]);
  const [texteEsthetique, setTexteEsthetique] = useState('');

  const sport = sportChoice === 'aucun' ? null : sportChoice === 'football' ? 'football' : autreSportTexte.trim();

  // Le calendrier de matchs n'a de sens que pour le football : étape masquée sinon (Phase 6 —
  // ne pas injecter de contexte football pour un profil qui n'en a pas).
  const steps = useMemo(
    () =>
      ['contexte_sportif', 'objectifs', 'niveau', 'materiel', 'disponibilites', ...(sportChoice === 'football' ? ['calendrier'] : []), 'esthetique'] as const,
    [sportChoice]
  );
  const TOTAL_STEPS = steps.length;
  const currentKey = steps[step];

  const toggleTag = (list: string[], value: string, setter: (v: string[]) => void) => {
    setter(list.includes(value) ? list.filter((v) => v !== value) : [...list, value]);
  };

  function toggleObjectif(theme: ThemeObjectifV2) {
    setObjectifsRanges((prev) => {
      if (prev.includes(theme)) return prev.filter((t) => t !== theme);
      if (prev.length >= MAX_OBJECTIFS) return prev; // max 3 (voir user_model_v2.MAX_OBJECTIFS_ACTIFS)
      return [...prev, theme];
    });
  }

  function deplacerObjectif(index: number, direction: -1 | 1) {
    setObjectifsRanges((prev) => {
      const cible = index + direction;
      if (cible < 0 || cible >= prev.length) return prev;
      const copie = [...prev];
      [copie[index], copie[cible]] = [copie[cible], copie[index]];
      return copie;
    });
  }

  function setMinutesJour(jourKey: string, minutes: number | null) {
    setDisponibilites((prev) => ({ ...prev, [jourKey]: minutes }));
  }

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
    switch (currentKey) {
      case 'contexte_sportif':
        if (sportChoice === 'aucun') return true;
        if (sportChoice === 'football') return poste !== '';
        return autreSportTexte.trim() !== '';
      case 'objectifs':
        return objectifsRanges.length > 0 && objectifsRanges.length <= MAX_OBJECTIFS;
      case 'niveau':
        return (
          Number(age) > 0 &&
          Number(tailleCm) > 0 &&
          Number(poidsKg) > 0 &&
          QUALITES.every((q) => qualites[q.key] > 0)
        );
      case 'materiel':
        return materiel !== '';
      case 'disponibilites':
        return Object.values(disponibilites).some((m) => m != null);
      case 'calendrier':
        return (
          (jourHabituel !== '' || exceptions.length > 0) &&
          clubActif !== '' &&
          (clubActif === 'non' || Number(seancesClub) > 0)
        );
      case 'esthetique':
        return true; // étape optionnelle
      default:
        return false;
    }
  })();

  const handleSubmit = async () => {
    setSaving(true);
    setError(null);
    try {
      const hasEsthetique = tagsEsthetiques.length > 0 || texteEsthetique.trim() !== '';

      // objectifs_v2 : rang déduit de l'ordre de sélection/classement ; poids toujours à 0 ici,
      // recalculé côté backend à partir du rang (voir schemas.ProfilBase._normaliser_v2) — le
      // frontend n'est jamais source de vérité sur les poids (Phase 2).
      const objectifs_v2 = objectifsRanges.map((theme, i) => ({ theme, rang: i + 1, poids: 0 }));

      const profil = await saveProfil({
        objectifs_v2,
        contexte_sportif: {
          sport,
          frequence_hebdo: frequenceHebdo ? Number(frequenceHebdo) : null,
          poste: sportChoice === 'football' ? poste : null,
        },
        disponibilites,
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

      {currentKey === 'contexte_sportif' && (
        <section>
          <h1 className="page-title">Ton sport</h1>
          <p className="subtle">Un seul choix. Ceci ne présume pas de tes objectifs — tu les choisis ensuite.</p>
          <div className="choice-list">
            <RadioItem label="Aucun sport pratiqué" selected={sportChoice === 'aucun'} onClick={() => setSportChoice('aucun')} />
            <RadioItem label="Football" selected={sportChoice === 'football'} onClick={() => setSportChoice('football')} />
            <RadioItem label="Autre sport" selected={sportChoice === 'autre'} onClick={() => setSportChoice('autre')} />
          </div>

          {sportChoice === 'autre' && (
            <input
              type="text"
              className="textarea"
              style={{ minHeight: 'unset', padding: 12, marginTop: 14 }}
              placeholder="Quel sport ?"
              value={autreSportTexte}
              onChange={(e) => setAutreSportTexte(e.target.value)}
            />
          )}

          {sportChoice === 'football' && (
            <>
              <p className="subtle" style={{ marginTop: 20 }}>Poste joué — un seul choix.</p>
              <div className="choice-list">
                {POSTES.map((p) => (
                  <RadioItem key={p} label={p} selected={poste === p} onClick={() => setPoste(p)} />
                ))}
              </div>
            </>
          )}

          {sportChoice !== 'aucun' && (
            <div className="onboarding-theme" style={{ marginTop: 20 }}>
              <div className="section-title">Fréquence hebdomadaire (optionnel)</div>
              <input
                type="number"
                min={0}
                max={14}
                className="textarea"
                style={{ minHeight: 'unset', padding: 12 }}
                placeholder="Nombre de séances / semaine"
                value={frequenceHebdo}
                onChange={(e) => setFrequenceHebdo(e.target.value)}
              />
            </div>
          )}
        </section>
      )}

      {currentKey === 'objectifs' && (
        <section>
          <h1 className="page-title">Tes objectifs</h1>
          <p className="subtle">
            Choisis 1 à {MAX_OBJECTIFS} objectifs, puis classe-les : 1 = priorité principale.
          </p>
          <div className="choice-list">
            {THEMES_OBJECTIFS.map((theme) => (
              <CheckboxItem
                key={theme}
                label={LABELS_THEMES_OBJECTIFS[theme]}
                selected={objectifsRanges.includes(theme)}
                disabled={!objectifsRanges.includes(theme) && objectifsRanges.length >= MAX_OBJECTIFS}
                onClick={() => toggleObjectif(theme)}
              />
            ))}
          </div>

          {objectifsRanges.length > 0 && (
            <>
              <p className="subtle" style={{ marginTop: 20 }}>
                Classement (1 = priorité principale) :
              </p>
              <ul className="exception-list">
                {objectifsRanges.map((theme, i) => (
                  <li key={theme} className="exception-list__item">
                    <span>
                      {i + 1}. {LABELS_THEMES_OBJECTIFS[theme]}
                    </span>
                    <span style={{ display: 'flex', gap: 6 }}>
                      <button type="button" onClick={() => deplacerObjectif(i, -1)} disabled={i === 0} aria-label="Monter">
                        ↑
                      </button>
                      <button
                        type="button"
                        onClick={() => deplacerObjectif(i, 1)}
                        disabled={i === objectifsRanges.length - 1}
                        aria-label="Descendre"
                      >
                        ↓
                      </button>
                    </span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </section>
      )}

      {currentKey === 'niveau' && (
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

          <p className="subtle" style={{ marginTop: 20 }}>
            Pour chaque qualité, de 1 (faible) à 5 (élevé) — c'est ton ressenti, pas une mesure objective.
          </p>
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

      {currentKey === 'materiel' && (
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

      {currentKey === 'disponibilites' && (
        <section>
          <h1 className="page-title">Tes disponibilités</h1>
          <p className="subtle">Pour chaque jour, choisis une durée ou « Indisponible ».</p>
          {JOURS_DISPONIBILITES.map(({ key, label }) => (
            <div key={key} className="onboarding-theme">
              <div className="section-title">{label}</div>
              <div className="choice-list choice-list--grid" style={{ gap: 8 }}>
                <CheckboxItem
                  label="Indisponible"
                  selected={disponibilites[key] == null}
                  onClick={() => setMinutesJour(key, null)}
                />
                {OPTIONS_MINUTES.map((m) => (
                  <CheckboxItem key={m} label={`${m} min`} selected={disponibilites[key] === m} onClick={() => setMinutesJour(key, m)} />
                ))}
              </div>
            </div>
          ))}
        </section>
      )}

      {currentKey === 'calendrier' && (
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

      {currentKey === 'esthetique' && (
        <section>
          <h1 className="page-title">Objectif esthétique</h1>
          <p className="subtle">Optionnel — zones à travailler en priorité, plusieurs choix possibles.</p>
          <div className="choice-list choice-list--grid" style={{ gap: 10 }}>
            {TAGS_ESTHETIQUES.map((t) => (
              <CheckboxItem
                key={t}
                label={t}
                selected={tagsEsthetiques.includes(t)}
                onClick={() => toggleTag(tagsEsthetiques, t, setTagsEsthetiques)}
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
