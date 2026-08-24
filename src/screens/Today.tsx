import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Header from '../components/Header';
import { genererSeance, getTodayModule, getTodaySeance, terminerSeanceIA } from '../api/client';
import type { ApiEtatDuJour, ApiModule, ApiSeance, ApiSeanceGeneree, ApiTerminerSeanceResult } from '../api/client';

const dateLabel = new Date().toLocaleDateString('fr-FR', {
  weekday: 'long',
  day: 'numeric',
  month: 'long',
});

const SOMMEIL_OPTIONS = ['Mauvais', 'Moyen', 'Bon', 'Excellent'];
const MOTIVATION_OPTIONS = ['Faible', 'Correcte', 'Élevée'];
const CLUB_SEMAINE_OPTIONS: { value: string; label: string }[] = [
  { value: 'non', label: 'Non' },
  { value: '1_fois', label: 'Oui, 1 fois' },
  { value: '2_fois_ou_plus', label: 'Oui, 2 fois ou plus' },
];

type View = 'loading' | 'no-seance' | 'form' | 'seance' | 'compte-rendu' | 'terminee';

export default function Today() {
  const navigate = useNavigate();
  const [view, setView] = useState<View>('loading');
  const [learningModule, setLearningModule] = useState<ApiModule | null>(null);

  const [seance, setSeance] = useState<ApiSeance | ApiSeanceGeneree | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [sommeil, setSommeil] = useState('');
  const [motivation, setMotivation] = useState('');
  const [tempsDispo, setTempsDispo] = useState('');
  const [envieTexte, setEnvieTexte] = useState('');
  const [clubSemaine, setClubSemaine] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const [compteRendu, setCompteRendu] = useState('');
  const [resultat, setResultat] = useState<ApiTerminerSeanceResult | null>(null);

  useEffect(() => {
    Promise.all([getTodaySeance(), getTodayModule()]).then(([s, m]) => {
      setLearningModule(m);
      if (s) {
        setSeance(s);
        setView(s.statut === 'terminee' ? 'terminee' : 'seance');
      } else {
        setView('no-seance');
      }
    });
  }, []);

  async function handleGenerer() {
    setSubmitting(true);
    setError(null);
    try {
      const payload: ApiEtatDuJour = {
        sommeil: sommeil || null,
        motivation: motivation || null,
        temps_dispo: tempsDispo.trim() || null,
        envie_texte: envieTexte.trim() || null,
        entrainement_club_semaine: clubSemaine || null,
      };
      const generee = await genererSeance(payload);
      setSeance(generee);
      setView('seance');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Erreur lors de la génération de la séance.');
    } finally {
      setSubmitting(false);
    }
  }

  async function handleTerminer() {
    if (!seance) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await terminerSeanceIA({ seance_id: seance.id, compte_rendu: compteRendu.trim() });
      setResultat(res);
      setView('terminee');
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur lors de l'enregistrement du compte-rendu.");
    } finally {
      setSubmitting(false);
    }
  }

  if (view === 'loading') {
    return (
      <div className="screen">
        <Header title="Aujourd’hui" />
        <p className="subtle">Chargement…</p>
      </div>
    );
  }

  return (
    <div className="screen">
      <Header title="Aujourd’hui" />
      <h1 className="page-title" style={{ textTransform: 'capitalize' }}>
        {dateLabel}
      </h1>

      {view === 'no-seance' && (
        <section className="card">
          <div className="card__eyebrow">Séance du jour</div>
          <p className="subtle" style={{ margin: '4px 0 14px' }}>
            Aucune séance générée pour aujourd’hui.
          </p>
          <button className="btn btn--primary" onClick={() => setView('form')}>
            Générer ma séance du jour
          </button>
        </section>
      )}

      {view === 'form' && (
        <section className="card">
          <div className="card__eyebrow">État du jour</div>

          <div className="onboarding-theme">
            <div className="section-title">Sommeil de la nuit dernière</div>
            <div className="tag-row tag-row--select">
              {SOMMEIL_OPTIONS.map((o) => (
                <button
                  key={o}
                  type="button"
                  className={`tag tag--selectable ${sommeil === o ? 'tag--active' : ''}`}
                  onClick={() => setSommeil(o)}
                >
                  {o}
                </button>
              ))}
            </div>
          </div>

          <div className="onboarding-theme">
            <div className="section-title">Motivation du jour</div>
            <div className="tag-row tag-row--select">
              {MOTIVATION_OPTIONS.map((o) => (
                <button
                  key={o}
                  type="button"
                  className={`tag tag--selectable ${motivation === o ? 'tag--active' : ''}`}
                  onClick={() => setMotivation(o)}
                >
                  {o}
                </button>
              ))}
            </div>
          </div>

          <div className="onboarding-theme">
            <div className="section-title">As-tu eu un entraînement club cette semaine ?</div>
            <div className="tag-row tag-row--select">
              {CLUB_SEMAINE_OPTIONS.map((o) => (
                <button
                  key={o.value}
                  type="button"
                  className={`tag tag--selectable ${clubSemaine === o.value ? 'tag--active' : ''}`}
                  onClick={() => setClubSemaine(o.value)}
                >
                  {o.label}
                </button>
              ))}
            </div>
          </div>

          <div className="onboarding-theme">
            <div className="section-title">Temps disponible aujourd’hui</div>
            <input
              type="text"
              className="textarea"
              style={{ minHeight: 'unset', padding: 12 }}
              placeholder="Ex : 45 min"
              value={tempsDispo}
              onChange={(e) => setTempsDispo(e.target.value)}
            />
          </div>

          <div className="onboarding-theme">
            <div className="section-title">Envie du moment (optionnel)</div>
            <textarea
              className="textarea"
              placeholder="Ex : j’ai envie de pousser fort aujourd’hui…"
              value={envieTexte}
              onChange={(e) => setEnvieTexte(e.target.value)}
            />
          </div>

          {error && (
            <p className="subtle" style={{ color: '#e5484d', margin: '4px 0 12px' }}>
              {error}
            </p>
          )}

          <button className="btn btn--primary" disabled={submitting} onClick={handleGenerer}>
            {submitting ? 'Génération en cours…' : 'Générer ma séance du jour'}
          </button>
        </section>
      )}

      {(view === 'seance' || view === 'compte-rendu' || view === 'terminee') && seance && (
        <section className="card">
          <div className="card__eyebrow">Séance du jour</div>
          <h2 className="card__title">{'nom' in seance ? seance.nom : seance.nom_seance}</h2>
          <p className="subtle" style={{ margin: '4px 0 12px' }}>
            {seance.exercices.length} exercices
          </p>
          <div>
            {seance.exercices.map((ex, i) => (
              <div className="exercise-row" key={i}>
                <span className="exercise-row__name">{ex.nom}</span>
                <span className="exercise-row__meta">
                  {ex.series}x{ex.repetitions}
                  {ex.charge_indicative ? ` · ${ex.charge_indicative}` : ''}
                </span>
              </div>
            ))}
          </div>
          {'explication' in seance && seance.explication && (
            <p className="subtle" style={{ marginTop: 14, lineHeight: 1.55 }}>
              {seance.explication}
            </p>
          )}

          {view === 'seance' && (
            <button className="btn btn--primary" style={{ marginTop: 14 }} onClick={() => setView('compte-rendu')}>
              Terminer la séance
            </button>
          )}

          {view === 'compte-rendu' && (
            <div style={{ marginTop: 14 }}>
              <div className="section-title">Compte-rendu de la séance</div>
              <textarea
                className="textarea"
                placeholder="Raconte comment s’est passée la séance : exercices réalisés, charges, ressenti…"
                value={compteRendu}
                onChange={(e) => setCompteRendu(e.target.value)}
              />
              {error && (
                <p className="subtle" style={{ color: '#e5484d', margin: '4px 0 12px' }}>
                  {error}
                </p>
              )}
              <button
                className="btn btn--primary"
                disabled={submitting || !compteRendu.trim()}
                style={{ opacity: submitting || !compteRendu.trim() ? 0.5 : 1 }}
                onClick={handleTerminer}
              >
                {submitting ? 'Enregistrement…' : 'Valider le compte-rendu'}
              </button>
            </div>
          )}

          {view === 'terminee' && (
            <p className="subtle" style={{ marginTop: 14 }}>
              Séance terminée{resultat ? ` · +${resultat.xp_gagne} XP` : ' pour aujourd’hui.'}
            </p>
          )}
        </section>
      )}

      {learningModule && (
        <section className="card">
          <div className="card__eyebrow">Module du jour</div>
          <span className="tag">{learningModule.categorie}</span>
          <h2 className="card__title" style={{ marginTop: 10 }}>
            {learningModule.titre}
          </h2>
          <p className="subtle" style={{ margin: '6px 0 14px' }}>
            {learningModule.contenu.slice(0, 120)}…
          </p>
          <button className="btn btn--ghost" onClick={() => navigate('/module')}>
            Ouvrir
          </button>
        </section>
      )}
    </div>
  );
}
