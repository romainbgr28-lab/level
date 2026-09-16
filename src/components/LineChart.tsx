import type { ChargeDataPoint } from '../types';

interface LineChartProps {
  data: ChargeDataPoint[];
  /** Unité affichée à côté de la dernière valeur ("kg" par défaut). */
  unite?: string;
  width?: number;
  height?: number;
}

function formatJour(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso; // libellé déjà formaté côté appelant
  return d.toLocaleDateString('fr-FR', { day: 'numeric', month: 'short' });
}

function formatValeur(valeur: number): string {
  return valeur >= 1000 ? valeur.toLocaleString('fr-FR', { maximumFractionDigits: 0 }) : `${valeur}`;
}

export default function LineChart({ data, unite = 'kg', width = 320, height = 140 }: LineChartProps) {
  const padding = 24;
  const loads = data.map((d) => d.loadKg);
  const min = Math.min(...loads);
  const max = Math.max(...loads);
  const range = max - min || 1;

  const points = data.map((d, i) => {
    const x = padding + (i / (data.length - 1)) * (width - padding * 2);
    const y = height - padding - ((d.loadKg - min) / range) * (height - padding * 2);
    return { x, y, ...d };
  });

  const path = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ');
  const dernier = points[points.length - 1];
  const areaPath = `${path} L${dernier.x.toFixed(1)},${height - padding} L${points[0].x.toFixed(1)},${height - padding} Z`;

  return (
    <svg viewBox={`0 0 ${width} ${height}`} width="100%" height={height} role="img" aria-label="Évolution">
      <defs>
        {/* Palette LEVEL (crème / charbon / lime) — les couleurs viennent des tokens CSS,
            plus des valeurs violettes codées en dur héritées de l'ancien thème sombre, qui
            rendaient notamment le libellé de valeur illisible sur fond crème. */}
        <linearGradient id="chartFill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.35" />
          <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={areaPath} fill="url(#chartFill)" />
      <path
        d={path}
        fill="none"
        stroke="var(--accent-2)"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {points.map((p, i) => (
        <circle
          key={p.date}
          cx={p.x}
          cy={p.y}
          r={i === points.length - 1 ? 4 : 2.5}
          fill={i === points.length - 1 ? 'var(--accent)' : 'var(--surface)'}
          stroke="var(--accent-2)"
          strokeWidth="1.5"
        />
      ))}
      <text x={points[0].x} y={height - 4} fontSize="10" fill="var(--text-faint)">
        {formatJour(data[0].date)}
      </text>
      <text x={dernier.x} y={height - 4} fontSize="10" fill="var(--text-faint)" textAnchor="end">
        {formatJour(data[data.length - 1].date)}
      </text>
      <text
        x={dernier.x}
        y={dernier.y - 10}
        fontSize="12"
        fontWeight="700"
        fill="var(--text)"
        textAnchor="end"
      >
        {formatValeur(data[data.length - 1].loadKg)} {unite}
      </text>
    </svg>
  );
}
