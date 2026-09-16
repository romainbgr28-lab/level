import type { ApiJourSemaine } from '../api/client';

// Bandeau de semaine : sept repères sobres qui répondent à « où j'en suis dans ma semaine »
// sans carte ni widget. Les statuts viennent du moteur (backend/contexte_jour.py) — ce
// composant ne décide rien, il ne fait qu'afficher ce qui a déjà été décidé.

const GLYPHE_PAR_STATUT: Record<string, string> = {
  seance: '●',
  repos: '·',
  match: '▲',
  indisponible: '×',
};

export default function SemaineStrip({ jours }: { jours: ApiJourSemaine[] }) {
  if (jours.length === 0) return null;

  return (
    <div className="semaine-strip" role="list" aria-label="Ma semaine">
      {jours.map((jour) => (
        <div
          key={jour.date}
          role="listitem"
          className={[
            'semaine-strip__jour',
            `semaine-strip__jour--${jour.statut}`,
            jour.est_aujourdhui ? 'semaine-strip__jour--aujourdhui' : '',
            jour.est_passe ? 'semaine-strip__jour--passe' : '',
          ]
            .filter(Boolean)
            .join(' ')}
          title={`${jour.jour_label} — ${jour.type_seance_prevu ?? jour.statut}`}
        >
          <span className="semaine-strip__label">{jour.jour_abbrev}</span>
          <span className="semaine-strip__marque">{GLYPHE_PAR_STATUT[jour.statut] ?? '·'}</span>
        </div>
      ))}
    </div>
  );
}
