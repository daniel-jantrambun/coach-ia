import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { type Activity, api, type Category, type Stats } from "../api";
import { BarChart, DotChart } from "../charts";
import {
  activityLabel,
  CATEGORIES,
  CATEGORY_ORDER,
  dayLabel,
  duration,
  km,
  minutes,
  speedLabel,
} from "../format";
import { Alert, Card, errorMessage, Spinner } from "../ui";

const PERIODS = [
  { weeks: 12, label: "12 sem." },
  { weeks: 26, label: "6 mois" },
  { weeks: 52, label: "1 an" },
];
const PACE_STEPS = [5, 10, 15, 20, 30, 60, 120, 300];

function chipClass(active: boolean): string {
  return `min-h-10 rounded-lg border px-3 text-sm ${
    active ? "border-accent bg-accent text-accent-ink" : "border-border bg-surface text-ink"
  }`;
}

function Tile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-surface-2 px-3 py-2">
      <dt className="text-xs text-ink-3">{label}</dt>
      <dd className="font-medium tabular-nums">{value}</dd>
    </div>
  );
}

export function GraphsPage() {
  const [params, setParams] = useSearchParams();
  const weeks = Number(params.get("periode")) || 26;
  const [stats, setStats] = useState<Stats | null>(null);
  const [list, setList] = useState<Activity[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .stats(weeks)
      .then(setStats)
      .catch((e) => setError(errorMessage(e)));
  }, [weeks]);

  const available = stats ? CATEGORY_ORDER.filter((c) => stats.categories[c]) : [];
  const requested = params.get("type") as Category | null;
  const cat: Category | undefined = requested && CATEGORIES[requested] ? requested : available[0];

  useEffect(() => {
    if (!cat) return;
    setList(null);
    api
      .activities(100, cat)
      .then(setList)
      .catch((e) => setError(errorMessage(e)));
  }, [cat]);

  function select(next: { type?: Category; periode?: number }) {
    const p = new URLSearchParams(params);
    if (next.type) p.set("type", next.type);
    if (next.periode) p.set("periode", String(next.periode));
    setParams(p, { replace: true });
  }

  if (error) return <Alert>{error}</Alert>;
  if (!stats) return <Spinner />;

  const data = cat ? stats.categories[cat] : undefined;
  const hasDistance = !!data && data.total.km > 0 && cat !== "gym";
  const isSpeed = cat === "bike";
  const weekLabels = data?.weeks.map((w) => dayLabel(w.start, { day: "numeric", month: "short" })) ?? [];

  return (
    <>
      <div className="space-y-2">
        <fieldset className="flex flex-wrap gap-2">
          <legend className="sr-only">Type d'activité</legend>
          {(available.length ? available : CATEGORY_ORDER.slice(0, 1)).map((c) => (
            <button
              key={c}
              type="button"
              aria-pressed={c === cat}
              onClick={() => select({ type: c })}
              className={chipClass(c === cat)}
            >
              <span aria-hidden>{CATEGORIES[c].icon}</span> {CATEGORIES[c].label}
            </button>
          ))}
        </fieldset>
        <fieldset className="flex flex-wrap gap-2">
          <legend className="sr-only">Période</legend>
          {PERIODS.map((p) => (
            <button
              key={p.weeks}
              type="button"
              aria-pressed={p.weeks === weeks}
              onClick={() => select({ periode: p.weeks })}
              className={chipClass(p.weeks === weeks)}
            >
              {p.label}
            </button>
          ))}
        </fieldset>
      </div>

      {!cat || !data ? (
        <Card>
          <p className="text-sm text-ink-2">
            Aucune activité sur cette période.{" "}
            <Link to="/activites" className="text-accent underline">
              Importez vos activités
            </Link>{" "}
            pour voir vos graphes.
          </p>
        </Card>
      ) : (
        <>
          <Card
            title={`${CATEGORIES[cat].label} · ${PERIODS.find((p) => p.weeks === weeks)?.label ?? `${weeks} sem.`}`}
          >
            <dl className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              <Tile label="Séances" value={String(data.total.sessions)} />
              <Tile label="Durée" value={minutes(data.total.minutes)} />
              {hasDistance && <Tile label="Distance" value={km(data.total.km)} />}
              {data.total.speed_m_s && (
                <Tile
                  label={isSpeed ? "Vitesse moyenne" : "Allure moyenne"}
                  value={speedLabel(cat, data.total.speed_m_s)}
                />
              )}
              {data.total.avg_hr && <Tile label="FC moyenne" value={`${data.total.avg_hr} bpm`} />}
            </dl>
            <div className="mt-4 space-y-5">
              <BarChart
                label={hasDistance ? "Distance par semaine (km)" : "Durée par semaine"}
                values={data.weeks.map((w) => (hasDistance ? w.km : w.minutes))}
                labels={weekLabels}
                formatY={(v) => (hasDistance ? String(v) : minutes(v))}
                tooltip={(i) => {
                  const w = data.weeks[i];
                  return (
                    <>
                      <p className="text-ink-3">Semaine du {weekLabels[i]}</p>
                      <p className="font-medium tabular-nums">
                        {w.sessions} séance{w.sessions > 1 ? "s" : ""} · {minutes(w.minutes)}
                      </p>
                      {hasDistance && <p className="tabular-nums text-ink-2">{km(w.km)}</p>}
                    </>
                  );
                }}
              />
              {data.total.speed_m_s && (
                <DotChart
                  label={
                    isSpeed
                      ? "Vitesse moyenne par semaine (km/h)"
                      : `Allure moyenne par semaine (${cat === "swim" ? "/100 m" : "/km"}, plus haut = plus rapide)`
                  }
                  values={data.weeks.map((w) =>
                    w.speed_m_s
                      ? isSpeed
                        ? w.speed_m_s * 3.6
                        : (cat === "swim" ? 100 : 1000) / w.speed_m_s
                      : null,
                  )}
                  labels={weekLabels}
                  invert={!isSpeed}
                  ySteps={isSpeed ? undefined : PACE_STEPS}
                  formatY={(v) =>
                    isSpeed
                      ? v.toLocaleString("fr-FR", { maximumFractionDigits: 1 })
                      : `${Math.floor(v / 60)}:${String(Math.round(v % 60)).padStart(2, "0")}`
                  }
                  tooltip={(i) => {
                    const w = data.weeks[i];
                    return (
                      <>
                        <p className="text-ink-3">Semaine du {weekLabels[i]}</p>
                        <p className="font-medium tabular-nums">
                          {w.speed_m_s ? speedLabel(cat, w.speed_m_s) : "—"}
                        </p>
                        <p className="tabular-nums text-ink-2">
                          {w.sessions} séance{w.sessions > 1 ? "s" : ""}
                        </p>
                      </>
                    );
                  }}
                />
              )}
              {data.total.avg_hr && (
                <DotChart
                  label="FC moyenne par semaine (bpm)"
                  values={data.weeks.map((w) => w.avg_hr)}
                  labels={weekLabels}
                  formatY={(v) => String(Math.round(v))}
                  tooltip={(i) => {
                    const w = data.weeks[i];
                    return (
                      <>
                        <p className="text-ink-3">Semaine du {weekLabels[i]}</p>
                        <p className="font-medium tabular-nums">{w.avg_hr} bpm</p>
                        <p className="tabular-nums text-ink-2">
                          {w.sessions} séance{w.sessions > 1 ? "s" : ""}
                        </p>
                      </>
                    );
                  }}
                />
              )}
            </div>
          </Card>

          <Card title="Activités">{list === null ? <Spinner /> : <ActivityList activities={list} />}</Card>
        </>
      )}
    </>
  );
}

export function ActivityList({ activities }: { activities: Activity[] }) {
  if (activities.length === 0) return <p className="text-sm text-ink-2">Aucune activité.</p>;
  return (
    <ul className="divide-y divide-border">
      {activities.map((a) => (
        <li key={a.id}>
          <Link
            to={`/activites/${encodeURIComponent(a.id)}`}
            className="-mx-2 flex items-center justify-between gap-3 rounded-lg px-2 py-2 text-sm hover:bg-surface-2"
          >
            <div>
              <p>
                <span aria-hidden>{CATEGORIES[a.category].icon} </span>
                {activityLabel(a)}
              </p>
              <p className="text-xs text-ink-3 first-letter:uppercase">
                {new Date(a.start_time).toLocaleDateString("fr-FR", {
                  weekday: "short",
                  day: "numeric",
                  month: "short",
                  year: "numeric",
                })}
              </p>
            </div>
            <div className="flex items-center gap-3">
              <div className="text-right tabular-nums">
                <p>
                  {a.distance_m ? `${km(a.distance_m / 1000)} · ` : ""}
                  {duration(a.duration_s)}
                </p>
                <p className="text-xs text-ink-3">
                  {a.distance_m && a.category !== "gym"
                    ? speedLabel(a.category, a.distance_m / a.duration_s)
                    : ""}
                  {a.avg_hr ? `${a.distance_m ? " · " : ""}${Math.round(a.avg_hr)} bpm` : ""}
                </p>
              </div>
              <span aria-hidden className="text-ink-3">
                ›
              </span>
            </div>
          </Link>
        </li>
      ))}
    </ul>
  );
}
