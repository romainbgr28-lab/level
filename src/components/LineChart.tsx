import type { ChargeDataPoint } from '../types';

interface LineChartProps {
  data: ChargeDataPoint[];
  width?: number;
  height?: number;
}

export default function LineChart({ data, width = 320, height = 140 }: LineChartProps) {
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
  const areaPath = `${path} L${points[points.length - 1].x.toFixed(1)},${height - padding} L${points[0].x.toFixed(1)},${height - padding} Z`;

  return (
    <svg viewBox={`0 0 ${width} ${height}`} width="100%" height={height} role="img" aria-label="Évolution de la charge">
      <defs>
        <linearGradient id="chartFill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#7c5cff" stopOpacity="0.35" />
          <stop offset="100%" stopColor="#7c5cff" stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={areaPath} fill="url(#chartFill)" />
      <path d={path} fill="none" stroke="#9b8cff" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
      {points.map((p, i) => (
        <circle
          key={i}
          cx={p.x}
          cy={p.y}
          r={i === points.length - 1 ? 4 : 3}
          fill={i === points.length - 1 ? '#7c5cff' : '#0a0a0f'}
          stroke="#9b8cff"
          strokeWidth="1.5"
        />
      ))}
      <text x={points[0].x} y={height - 4} fontSize="10" fill="#64647a">
        {data[0].date}
      </text>
      <text x={points[points.length - 1].x} y={height - 4} fontSize="10" fill="#64647a" textAnchor="end">
        {data[data.length - 1].date}
      </text>
      <text
        x={points[points.length - 1].x}
        y={points[points.length - 1].y - 10}
        fontSize="12"
        fontWeight="700"
        fill="#f2f2f6"
        textAnchor="end"
      >
        {data[data.length - 1].loadKg} kg
      </text>
    </svg>
  );
}
