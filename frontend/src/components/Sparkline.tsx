interface TrendPoint {
  period: string;
  value: number;
}

// Stroke colors validated against the dark surface (lightness band, chroma,
// CVD separation, contrast) with the dataviz palette validator.
const STROKE: Record<string, string> = {
  breach: "#f43f5e",
  at_risk: "#d97706",
  conflict: "#d97706",
  ok: "#059669",
};

const WIDTH = 172;
const HEIGHT = 52;
const PAD_X = 6;
const PAD_TOP = 14;
const PAD_BOTTOM = 12;

export function Sparkline({
  points,
  threshold,
  status,
  unit,
}: {
  points: TrendPoint[];
  threshold: number;
  status: string;
  unit?: string;
}) {
  if (points.length < 2) return null;
  const values = points.map((point) => point.value);
  const lo = Math.min(...values, threshold);
  const hi = Math.max(...values, threshold);
  const span = hi - lo || 1;
  const plotWidth = WIDTH - PAD_X * 2;
  const plotHeight = HEIGHT - PAD_TOP - PAD_BOTTOM;

  const x = (index: number) => PAD_X + (index / (points.length - 1)) * plotWidth;
  const y = (value: number) => PAD_TOP + (1 - (value - lo) / span) * plotHeight;

  const stroke = STROKE[status] ?? STROKE.at_risk;
  const path = points.map((point, index) => `${index === 0 ? "M" : "L"}${x(index).toFixed(1)},${y(point.value).toFixed(1)}`).join(" ");
  const last = points[points.length - 1];
  const first = points[0];
  const suffix = unit === "x" ? "x" : "";
  const label = `Trend ${points.map((point) => `${point.period}: ${point.value.toFixed(2)}${suffix}`).join(", ")}; covenant limit ${threshold.toFixed(2)}${suffix}`;

  return (
    <svg
      width={WIDTH}
      height={HEIGHT}
      viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
      role="img"
      aria-label={label}
      className="shrink-0"
    >
      {/* covenant limit — recessive dashed rule with a text-token label */}
      <line
        x1={PAD_X}
        x2={WIDTH - PAD_X}
        y1={y(threshold)}
        y2={y(threshold)}
        stroke="#64748b"
        strokeWidth={1.25}
        strokeDasharray="4 3"
      />
      <text x={WIDTH - PAD_X} y={y(threshold) - 3} textAnchor="end" fontSize={9} fill="#94a3b8">
        limit {threshold.toFixed(2)}{suffix}
      </text>

      <path d={path} fill="none" stroke={stroke} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />

      {points.map((point, index) => (
        <circle
          key={point.period + index}
          cx={x(index)}
          cy={y(point.value)}
          r={index === points.length - 1 ? 4.5 : 4}
          fill={stroke}
          stroke="#0b1322"
          strokeWidth={2}
        />
      ))}

      {/* selective direct labels: first and last values only */}
      <text x={x(0)} y={y(first.value) - 7} textAnchor="start" fontSize={9.5} fill="#cbd5e1">
        {first.value.toFixed(2)}{suffix}
      </text>
      <text x={x(points.length - 1)} y={y(last.value) - 7} textAnchor="end" fontSize={10} fontWeight={700} fill="#e2e8f0">
        {last.value.toFixed(2)}{suffix}
      </text>
      <text x={PAD_X} y={HEIGHT - 1} textAnchor="start" fontSize={8.5} fill="#64748b">
        {first.period}
      </text>
      <text x={WIDTH - PAD_X} y={HEIGHT - 1} textAnchor="end" fontSize={8.5} fill="#64748b">
        {last.period}
      </text>
    </svg>
  );
}
