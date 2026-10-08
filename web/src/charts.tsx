import { type PointerEvent, type ReactNode, useEffect, useRef, useState } from "react";

// Graphes à une seule série (un axe, une couleur) : courbe et barres, avec survol et infobulle.

const PAD = { top: 10, right: 12, bottom: 24, left: 46 };
const COLOR = "var(--series-1)";

export function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(600);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  return [ref, width] as const;
}

/** Graduations « rondes » couvrant [min, max]. `steps` : pas autorisés (ex. secondes pour une allure). */
export function niceTicks(min: number, max: number, count = 4, steps?: number[]): number[] {
  const hi = max > min ? max : min + 1;
  const raw = (hi - min) / count;
  let step: number;
  if (steps) {
    step = steps.find((s) => s >= raw) ?? steps[steps.length - 1];
  } else {
    const magnitude = 10 ** Math.floor(Math.log10(raw));
    step = ([1, 2, 2.5, 5, 10].find((m) => m * magnitude >= raw) ?? 10) * magnitude;
  }
  const ticks: number[] = [];
  for (let v = Math.floor(min / step) * step; v <= Math.ceil(hi / step) * step + step * 1e-9; v += step) {
    ticks.push(Number(v.toFixed(6)));
  }
  return ticks;
}

/** Bornes robustes (percentiles) : un pic GPS ou un arrêt n'écrase pas l'échelle. */
export function robustDomain(values: (number | null)[], low = 0.02, high = 0.98): [number, number] | null {
  const sorted = values.filter((v): v is number => v !== null && Number.isFinite(v)).sort((a, b) => a - b);
  if (sorted.length === 0) return null;
  const at = (q: number) =>
    sorted[Math.min(sorted.length - 1, Math.max(0, Math.round(q * (sorted.length - 1))))];
  return [at(low), at(high)];
}

function Tooltip({ left, width, children }: { left: number; width: number; children: ReactNode }) {
  const w = 150;
  return (
    <div
      className="pointer-events-none absolute top-0 rounded-lg border border-border bg-surface px-2.5 py-1.5 text-xs shadow-sm"
      style={{ left: Math.min(Math.max(left - w / 2, 0), width - w), width: w }}
    >
      {children}
    </div>
  );
}

type LineChartProps = {
  label: string;
  x: number[];
  y: (number | null)[];
  formatX: (v: number) => string;
  formatY: (v: number) => string;
  xTicks?: number[];
  yDomain?: [number, number];
  ySteps?: number[];
  /** Allure : les petites valeurs (plus rapide) en haut. */
  invert?: boolean;
  hover: number | null;
  onHover: (index: number | null) => void;
  height?: number;
};

export function LineChart({
  label,
  x,
  y,
  formatX,
  formatY,
  xTicks,
  yDomain,
  ySteps,
  invert = false,
  hover,
  onHover,
  height = 160,
}: LineChartProps) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const domain = yDomain ?? robustDomain(y, 0, 1) ?? [0, 1];
  const yTicks = niceTicks(domain[0], domain[1], 4, ySteps);
  const [y0, y1] = [yTicks[0], yTicks[yTicks.length - 1]];
  const [x0, x1] = [x[0] ?? 0, x[x.length - 1] ?? 1];
  const innerW = Math.max(width - PAD.left - PAD.right, 10);
  const innerH = height - PAD.top - PAD.bottom;
  const px = (v: number) => PAD.left + (x1 > x0 ? ((v - x0) / (x1 - x0)) * innerW : innerW / 2);
  const py = (v: number) => {
    const clamped = Math.min(Math.max(v, y0), y1);
    const ratio = (clamped - y0) / (y1 - y0 || 1);
    return PAD.top + (invert ? ratio : 1 - ratio) * innerH;
  };

  // Un tracé par portion continue (pas de ligne à travers les trous de données).
  const segments: string[] = [];
  let current: string[] = [];
  y.forEach((v, i) => {
    if (v === null) {
      if (current.length) segments.push(current.join(" "));
      current = [];
    } else {
      current.push(`${px(x[i]).toFixed(1)},${py(v).toFixed(1)}`);
    }
  });
  if (current.length) segments.push(current.join(" "));

  function onPointerMove(event: PointerEvent<SVGRectElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    const value = x0 + ((event.clientX - rect.left) / rect.width) * (x1 - x0);
    let best = 0;
    for (let i = 1; i < x.length; i++) if (Math.abs(x[i] - value) < Math.abs(x[best] - value)) best = i;
    onHover(best);
  }

  const hovered = hover !== null && hover < y.length ? y[hover] : null;
  const ticksX =
    xTicks ?? niceTicks(x0, x1, Math.max(2, Math.floor(innerW / 80))).filter((t) => t >= x0 && t <= x1);

  return (
    <figure>
      <figcaption className="mb-1 text-xs font-medium text-ink-2">{label}</figcaption>
      <div ref={ref} className="relative">
        <svg width={width} height={height} role="img" aria-label={label}>
          {yTicks.map((t) => (
            <g key={t}>
              <line x1={PAD.left} x2={PAD.left + innerW} y1={py(t)} y2={py(t)} stroke="var(--grid)" />
              <text
                x={PAD.left - 6}
                y={py(t)}
                dy="0.32em"
                textAnchor="end"
                className="fill-ink-3 text-[10px]"
              >
                {formatY(t)}
              </text>
            </g>
          ))}
          {ticksX.map((t) => (
            <text key={t} x={px(t)} y={height - 6} textAnchor="middle" className="fill-ink-3 text-[10px]">
              {formatX(t)}
            </text>
          ))}
          {segments.map((points) => (
            <polyline
              key={points.slice(0, 24)}
              fill="none"
              stroke={COLOR}
              strokeWidth={2}
              strokeLinejoin="round"
              strokeLinecap="round"
              points={points}
            />
          ))}
          {hover !== null && hover < x.length && (
            <g>
              <line
                x1={px(x[hover])}
                x2={px(x[hover])}
                y1={PAD.top}
                y2={PAD.top + innerH}
                stroke="var(--text-3)"
                strokeDasharray="3 3"
              />
              {hovered !== null && (
                <circle
                  cx={px(x[hover])}
                  cy={py(hovered)}
                  r={4}
                  fill={COLOR}
                  stroke="var(--surface)"
                  strokeWidth={2}
                />
              )}
            </g>
          )}
          <rect
            x={PAD.left}
            y={0}
            width={innerW}
            height={height}
            fill="transparent"
            onPointerMove={onPointerMove}
            onPointerDown={onPointerMove}
            onPointerLeave={() => onHover(null)}
          />
        </svg>
        {hover !== null && hover < x.length && (
          <Tooltip left={px(x[hover])} width={width}>
            <p className="text-ink-3">{formatX(x[hover])}</p>
            <p className="font-medium tabular-nums">{hovered !== null ? formatY(hovered) : "—"}</p>
          </Tooltip>
        )}
      </div>
    </figure>
  );
}

type BarChartProps = {
  label: string;
  values: (number | null)[];
  /** Étiquette de chaque barre sous l'axe (affichées en partie si elles sont nombreuses). */
  labels: string[];
  formatY: (v: number) => string;
  tooltip: (index: number) => ReactNode;
  ySteps?: number[];
  height?: number;
};

export function BarChart({ label, values, labels, formatY, tooltip, ySteps, height = 160 }: BarChartProps) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const max = Math.max(0, ...values.map((v) => v ?? 0));
  const yTicks = niceTicks(0, max || 1, 4, ySteps);
  const yMax = yTicks[yTicks.length - 1];
  const innerW = Math.max(width - PAD.left - PAD.right, 10);
  const innerH = height - PAD.top - PAD.bottom;
  const slot = innerW / Math.max(values.length, 1);
  const gap = Math.min(2, slot / 3); // 2 px de séparation entre barres
  const py = (v: number) => PAD.top + innerH - (v / yMax) * innerH;
  const every = Math.ceil(values.length / Math.max(1, Math.floor(innerW / 48)));

  function bar(i: number, v: number) {
    const x = PAD.left + i * slot + gap / 2;
    const w = Math.max(slot - gap, 1);
    const top = py(v);
    const base = PAD.top + innerH;
    const r = Math.min(4, w / 2, base - top);
    // Coins arrondis seulement en haut (le bas reste posé sur l'axe).
    return `M${x},${base} V${top + r} Q${x},${top} ${x + r},${top} H${x + w - r} Q${x + w},${top} ${x + w},${top + r} V${base} Z`;
  }

  return (
    <figure>
      <figcaption className="mb-1 text-xs font-medium text-ink-2">{label}</figcaption>
      <div ref={ref} className="relative">
        <svg width={width} height={height} role="img" aria-label={label}>
          {yTicks.map((t) => (
            <g key={t}>
              <line x1={PAD.left} x2={PAD.left + innerW} y1={py(t)} y2={py(t)} stroke="var(--grid)" />
              <text
                x={PAD.left - 6}
                y={py(t)}
                dy="0.32em"
                textAnchor="end"
                className="fill-ink-3 text-[10px]"
              >
                {formatY(t)}
              </text>
            </g>
          ))}
          {values.map((v, i) =>
            v ? (
              <path
                // biome-ignore lint/suspicious/noArrayIndexKey: barres à position fixe
                key={i}
                d={bar(i, v)}
                fill={COLOR}
                opacity={hover === null || hover === i ? 1 : 0.55}
              />
            ) : null,
          )}
          {labels.map((l, i) =>
            i % every === 0 ? (
              <text
                // biome-ignore lint/suspicious/noArrayIndexKey: étiquettes à position fixe
                key={i}
                x={PAD.left + (i + 0.5) * slot}
                y={height - 6}
                textAnchor="middle"
                className="fill-ink-3 text-[10px]"
              >
                {l}
              </text>
            ) : null,
          )}
          {/* Zones de survol : toute la hauteur de chaque colonne, plus grandes que la barre. */}
          {values.map((_, i) => (
            <rect
              // biome-ignore lint/suspicious/noArrayIndexKey: colonnes à position fixe
              key={i}
              x={PAD.left + i * slot}
              y={0}
              width={slot}
              height={height}
              fill="transparent"
              onPointerEnter={() => setHover(i)}
              onPointerDown={() => setHover(i)}
              onPointerLeave={() => setHover(null)}
            />
          ))}
        </svg>
        {hover !== null && (
          <Tooltip left={PAD.left + (hover + 0.5) * slot} width={width}>
            {tooltip(hover)}
          </Tooltip>
        )}
      </div>
    </figure>
  );
}

type DotChartProps = {
  label: string;
  /** Une valeur par colonne (semaine) ; null = pas de donnée, rien n'est dessiné. */
  values: (number | null)[];
  labels: string[];
  formatY: (v: number) => string;
  tooltip: (index: number) => ReactNode;
  ySteps?: number[];
  /** Allure : les petites valeurs (plus rapide) en haut. */
  invert?: boolean;
  height?: number;
};

/** Un point par colonne, sans ligne : les colonnes vides restent vides (une ligne inventerait la tendance).
 * Mêmes colonnes que BarChart, pour s'aligner avec un graphe de volume au-dessus. Échelle resserrée sur les
 * valeurs (pas de barre, donc pas besoin de partir de zéro). */
export function DotChart({
  label,
  values,
  labels,
  formatY,
  tooltip,
  ySteps,
  invert = false,
  height = 150,
}: DotChartProps) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const present = values.filter((v): v is number => v !== null);
  const lo = Math.min(...present);
  const hi = Math.max(...present);
  const margin = (hi - lo) * 0.1 || 1;
  const yTicks = niceTicks(lo - margin, hi + margin, 4, ySteps);
  const [y0, y1] = [yTicks[0], yTicks[yTicks.length - 1]];
  const innerW = Math.max(width - PAD.left - PAD.right, 10);
  const innerH = height - PAD.top - PAD.bottom;
  const slot = innerW / Math.max(values.length, 1);
  const cx = (i: number) => PAD.left + (i + 0.5) * slot;
  const py = (v: number) => {
    const ratio = (v - y0) / (y1 - y0 || 1);
    return PAD.top + (invert ? ratio : 1 - ratio) * innerH;
  };
  const every = Math.ceil(values.length / Math.max(1, Math.floor(innerW / 48)));

  return (
    <figure>
      <figcaption className="mb-1 text-xs font-medium text-ink-2">{label}</figcaption>
      <div ref={ref} className="relative">
        <svg width={width} height={height} role="img" aria-label={label}>
          {yTicks.map((t) => (
            <g key={t}>
              <line x1={PAD.left} x2={PAD.left + innerW} y1={py(t)} y2={py(t)} stroke="var(--grid)" />
              <text
                x={PAD.left - 6}
                y={py(t)}
                dy="0.32em"
                textAnchor="end"
                className="fill-ink-3 text-[10px]"
              >
                {formatY(t)}
              </text>
            </g>
          ))}
          {labels.map((l, i) =>
            i % every === 0 ? (
              <text
                // biome-ignore lint/suspicious/noArrayIndexKey: étiquettes à position fixe
                key={i}
                x={cx(i)}
                y={height - 6}
                textAnchor="middle"
                className="fill-ink-3 text-[10px]"
              >
                {l}
              </text>
            ) : null,
          )}
          {hover !== null && values[hover] !== null && (
            <line
              x1={cx(hover)}
              x2={cx(hover)}
              y1={PAD.top}
              y2={PAD.top + innerH}
              stroke="var(--text-3)"
              strokeDasharray="3 3"
            />
          )}
          {values.map((v, i) =>
            v === null ? null : (
              <circle
                // biome-ignore lint/suspicious/noArrayIndexKey: points à position fixe
                key={i}
                cx={cx(i)}
                cy={py(v)}
                r={hover === i ? 5.5 : 4.5}
                fill={COLOR}
                stroke="var(--surface)"
                strokeWidth={2}
              />
            ),
          )}
          {values.map((_, i) => (
            <rect
              // biome-ignore lint/suspicious/noArrayIndexKey: colonnes à position fixe
              key={i}
              x={PAD.left + i * slot}
              y={0}
              width={slot}
              height={height}
              fill="transparent"
              onPointerEnter={() => setHover(i)}
              onPointerDown={() => setHover(i)}
              onPointerLeave={() => setHover(null)}
            />
          ))}
        </svg>
        {hover !== null && values[hover] !== null && (
          <Tooltip left={cx(hover)} width={width}>
            {tooltip(hover)}
          </Tooltip>
        )}
      </div>
    </figure>
  );
}
