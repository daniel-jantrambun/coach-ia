import { type PointerEvent, useEffect, useRef, useState } from "react";
import type { LoadPoint } from "./api";
import { dayLabel, parseDay } from "./format";

// Forme (CTL) et fatigue (ATL) : même unité, un seul axe. La forme du jour (TSB) est affichée à part.
const SERIES = [
  { key: "ctl", label: "Forme (42 j)", color: "var(--series-1)" },
  { key: "atl", label: "Fatigue (7 j)", color: "var(--series-2)" },
] as const;

const HEIGHT = 220;
const PAD = { top: 12, right: 76, bottom: 26, left: 36 };

// Pas de graduation "rond" (1, 2, 5 × 10^n) pour 4 intervalles.
function niceStep(max: number): number {
  const raw = Math.max(max, 1) / 4;
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  return ([1, 2, 5, 10].find((m) => m * magnitude >= raw) ?? 10) * magnitude;
}

export function LoadChart({ data }: { data: LoadPoint[] }) {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(600);
  const [hover, setHover] = useState<number | null>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const innerW = Math.max(width - PAD.left - PAD.right, 10);
  const innerH = HEIGHT - PAD.top - PAD.bottom;
  const step = niceStep(Math.max(...data.map((d) => Math.max(d.ctl, d.atl))));
  const yMax = step * 4;
  const x = (i: number) => PAD.left + (data.length > 1 ? (i / (data.length - 1)) * innerW : innerW / 2);
  const y = (v: number) => PAD.top + innerH - (v / yMax) * innerH;
  const ticks = [0, 1, 2, 3, 4].map((i) => i * step);
  // Repères en abscisse : le 1er de chaque mois.
  const monthTicks = data.flatMap((d, i) => (d.day.endsWith("-01") ? [i] : []));

  function onPointerMove(event: PointerEvent<SVGRectElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    const ratio = (event.clientX - rect.left) / rect.width;
    setHover(Math.min(data.length - 1, Math.max(0, Math.round(ratio * (data.length - 1)))));
  }

  const last = data.length - 1;
  const hovered = hover !== null ? data[hover] : null;
  // Étiquettes directes en bout de courbe, écartées si elles se chevauchent.
  const endLabels = SERIES.map((s) => ({ ...s, y: y(data[last][s.key]) }));
  if (Math.abs(endLabels[0].y - endLabels[1].y) < 14) {
    const [hi, lo] = endLabels[0].y < endLabels[1].y ? [0, 1] : [1, 0];
    const mid = (endLabels[0].y + endLabels[1].y) / 2;
    endLabels[hi].y = mid - 7;
    endLabels[lo].y = mid + 7;
  }

  return (
    <figure className="space-y-2">
      <figcaption className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-2">
        {SERIES.map((s) => (
          <span key={s.key} className="flex items-center gap-1.5">
            <span className="h-0.5 w-4 rounded" style={{ background: s.color }} aria-hidden />
            {s.label}
          </span>
        ))}
      </figcaption>
      <div ref={ref} className="relative">
        <svg
          width={width}
          height={HEIGHT}
          role="img"
          aria-label={`Forme ${data[last].ctl}, fatigue ${data[last].atl} au ${dayLabel(data[last].day)}`}
        >
          {ticks.map((t) => (
            <g key={t}>
              <line x1={PAD.left} x2={PAD.left + innerW} y1={y(t)} y2={y(t)} stroke="var(--grid)" />
              <text x={PAD.left - 6} y={y(t)} dy="0.32em" textAnchor="end" className="fill-ink-3 text-[10px]">
                {t}
              </text>
            </g>
          ))}
          {monthTicks.map((i) => (
            <text key={i} x={x(i)} y={HEIGHT - 6} textAnchor="middle" className="fill-ink-3 text-[10px]">
              {parseDay(data[i].day).toLocaleDateString("fr-FR", { month: "short" })}
            </text>
          ))}
          {SERIES.map((s) => (
            <polyline
              key={s.key}
              fill="none"
              stroke={s.color}
              strokeWidth={2}
              strokeLinejoin="round"
              strokeLinecap="round"
              points={data.map((d, i) => `${x(i)},${y(d[s.key])}`).join(" ")}
            />
          ))}
          {endLabels.map((s) => (
            <text key={s.key} x={x(last) + 8} y={s.y} dy="0.32em" className="fill-ink-2 text-[11px]">
              {s.key === "ctl" ? "Forme" : "Fatigue"} {Math.round(data[last][s.key])}
            </text>
          ))}
          {hovered && hover !== null && (
            <g>
              <line
                x1={x(hover)}
                x2={x(hover)}
                y1={PAD.top}
                y2={PAD.top + innerH}
                stroke="var(--text-3)"
                strokeDasharray="3 3"
              />
              {SERIES.map((s) => (
                <circle
                  key={s.key}
                  cx={x(hover)}
                  cy={y(hovered[s.key])}
                  r={4}
                  fill={s.color}
                  stroke="var(--surface)"
                  strokeWidth={2}
                />
              ))}
            </g>
          )}
          {/* Zone de survol plus grande que les tracés */}
          <rect
            x={PAD.left}
            y={0}
            width={innerW}
            height={HEIGHT}
            fill="transparent"
            onPointerMove={onPointerMove}
            onPointerDown={onPointerMove}
            onPointerLeave={() => setHover(null)}
          />
        </svg>
        {hovered && hover !== null && (
          <div
            className="pointer-events-none absolute top-0 rounded-lg border border-border bg-surface px-2.5 py-1.5 text-xs shadow-sm"
            style={{
              left: Math.min(Math.max(x(hover) - 70, 0), width - 140),
              width: 140,
            }}
          >
            <p className="font-medium first-letter:uppercase">{dayLabel(hovered.day)}</p>
            {SERIES.map((s) => (
              <p key={s.key} className="flex items-center justify-between gap-2 text-ink-2">
                <span className="flex items-center gap-1">
                  <span className="size-2 rounded-full" style={{ background: s.color }} aria-hidden />
                  {s.key === "ctl" ? "Forme" : "Fatigue"}
                </span>
                <span className="tabular-nums text-ink">{hovered[s.key].toFixed(1)}</span>
              </p>
            ))}
            <p className="flex justify-between text-ink-2">
              Charge du jour <span className="tabular-nums text-ink">{Math.round(hovered.load)}</span>
            </p>
          </div>
        )}
      </div>
      <details className="text-sm">
        <summary className="cursor-pointer text-xs text-ink-3">Voir les données (14 derniers jours)</summary>
        <table className="mt-2 w-full text-xs tabular-nums">
          <thead className="text-left text-ink-3">
            <tr>
              <th className="py-1 font-normal">Jour</th>
              <th className="font-normal">Charge</th>
              <th className="font-normal">Forme</th>
              <th className="font-normal">Fatigue</th>
              <th className="font-normal">Fraîcheur</th>
            </tr>
          </thead>
          <tbody>
            {data.slice(-14).map((d) => (
              <tr key={d.day} className="border-t border-border">
                <td className="py-1 first-letter:uppercase">{dayLabel(d.day)}</td>
                <td>{Math.round(d.load)}</td>
                <td>{d.ctl.toFixed(1)}</td>
                <td>{d.atl.toFixed(1)}</td>
                <td>{d.tsb.toFixed(1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </figure>
  );
}
