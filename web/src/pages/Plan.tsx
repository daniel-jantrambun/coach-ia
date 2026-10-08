import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { api, type Plan, type PlanSummary, type Session, type Week } from "../api";
import { dayLabel, distanceLabel, duration, KIND_LABELS, km, PHASE_LABELS, pace, todayIso } from "../format";
import { Alert, Button, buttonClass, Card, errorMessage, Spinner } from "../ui";

const NARRATE_POLL_MS = 10_000;

export function PlanPage() {
  const { planId } = useParams();
  const navigate = useNavigate();
  const [plans, setPlans] = useState<PlanSummary[] | null>(null);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Sans identifiant dans l'URL, on affiche le plan le plus récent.
  const selectedId = planId ? Number(planId) : plans?.[0]?.id;

  useEffect(() => {
    api
      .plans()
      .then(setPlans)
      .catch((e) => setError(errorMessage(e)));
  }, []);

  const reload = useCallback(() => {
    if (selectedId === undefined) return;
    api
      .plan(selectedId)
      .then(setPlan)
      .catch((e) => setError(errorMessage(e)));
  }, [selectedId]);

  useEffect(reload, [reload]);

  // Pendant que le LLM rédige (1 à 2 min par semaine sur le NAS), on rafraîchit régulièrement.
  useEffect(() => {
    if (!plan?.narrating) return;
    const timer = setInterval(reload, NARRATE_POLL_MS);
    return () => clearInterval(timer);
  }, [plan?.narrating, reload]);

  if (error) return <Alert>{error}</Alert>;
  if (plans === null || (selectedId !== undefined && plan === null)) return <Spinner />;

  if (plans.length === 0) {
    return (
      <Card>
        <div className="space-y-3 py-6 text-center">
          <p className="text-3xl" aria-hidden>
            🎯
          </p>
          <h1 className="text-lg font-semibold">Pas encore de plan</h1>
          <p className="text-sm text-ink-2">
            Fixez un objectif de course : le plan est calculé à partir de vos activités récentes.
          </p>
          <Link to="/plans/nouveau" className={buttonClass("primary")}>
            Créer mon plan
          </Link>
        </div>
      </Card>
    );
  }
  if (!plan) return null;

  async function narrate() {
    if (!plan) return;
    try {
      await api.narrate(plan.id);
      reload();
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  const today = todayIso();
  const weeksLeft = plan.weeks.filter((w) => w.start > today).length;
  const narrated = plan.weeks.filter((w) => w.text).length;

  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-2">
        {plans.length > 1 ? (
          <select
            aria-label="Choisir un plan"
            className="min-h-10 rounded-lg border border-border bg-surface px-2 text-sm"
            value={plan.id}
            onChange={(e) => navigate(`/plans/${e.target.value}`)}
          >
            {plans.map((p) => (
              <option key={p.id} value={p.id}>
                {distanceLabel(p.goal.distance_km)} ·{" "}
                {dayLabel(p.goal.race_date, { day: "numeric", month: "short", year: "numeric" })}
              </option>
            ))}
          </select>
        ) : (
          <span />
        )}
        <Link to="/plans/nouveau" className={buttonClass("secondary")}>
          + Nouvel objectif
        </Link>
      </div>

      <Card>
        <p className="text-sm text-ink-3">Objectif</p>
        <h1 className="text-2xl font-semibold">
          {distanceLabel(plan.goal.distance_km)} en {duration(plan.goal.target_time_s)}
        </h1>
        <p className="mt-1 text-sm text-ink-2">
          {dayLabel(plan.goal.race_date, { weekday: "long", day: "numeric", month: "long", year: "numeric" })}
          {weeksLeft > 0 && ` · dans ${weeksLeft} semaine${weeksLeft > 1 ? "s" : ""}`}
        </p>
        <dl className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
          {(["race", "tempo", "intervals", "easy"] as const).map((key) => (
            <div key={key} className="rounded-lg bg-surface-2 px-3 py-2">
              <dt className="text-xs text-ink-3">
                {{ race: "Allure course", tempo: "Seuil", intervals: "Fractionné", easy: "Footing" }[key]}
              </dt>
              <dd className="font-medium tabular-nums">{pace(plan.paces[key])}</dd>
            </div>
          ))}
        </dl>
        {plan.warnings.length > 0 && (
          <ul className="mt-4 space-y-2">
            {plan.warnings.map((w) => (
              <li
                key={w}
                className="flex gap-2 rounded-lg border border-warning/40 px-3 py-2 text-sm text-ink-2"
              >
                <span aria-hidden className="text-warning">
                  ⚠
                </span>
                <span>
                  <span className="sr-only">Attention : </span>
                  {w}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card
        title="Le mot du coach"
        action={
          <Button variant="secondary" onClick={narrate} disabled={plan.narrating}>
            {plan.narrating ? "Rédaction…" : narrated ? "Réécrire" : "Rédiger le plan"}
          </Button>
        }
      >
        {plan.narrating ? (
          <Spinner
            label={`Le coach rédige les séances (${narrated}/${plan.weeks.length} semaines)… comptez 1 à 2 min par semaine.`}
          />
        ) : plan.narrate_error ? (
          <Alert>{plan.narrate_error}</Alert>
        ) : (
          <p className="text-sm text-ink-2">
            {narrated
              ? `${narrated} semaine${narrated > 1 ? "s" : ""} rédigée${narrated > 1 ? "s" : ""} par le LLM local. Les chiffres restent ceux du plan.`
              : "Le LLM local peut expliquer chaque séance en quelques phrases. Les chiffres du plan ne changent pas."}
          </p>
        )}
      </Card>

      <ol className="space-y-3">
        {plan.weeks.map((week) => (
          <WeekCard key={week.index} week={week} total={plan.weeks.length} today={today} />
        ))}
      </ol>
    </>
  );
}

function addDays(day: string, n: number): string {
  const d = new Date(`${day}T12:00:00`);
  d.setDate(d.getDate() + n);
  return d.toISOString().slice(0, 10);
}

function WeekCard({ week, total, today }: { week: Week; total: number; today: string }) {
  const end = addDays(week.start, 6);
  const isCurrent = week.start <= today && today <= end;
  const isPast = end < today;
  const [open, setOpen] = useState(isCurrent);

  return (
    <li
      className={`rounded-xl border bg-surface ${isCurrent ? "border-accent" : "border-border"} ${isPast ? "opacity-60" : ""}`}
    >
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
      >
        <div>
          <p className="text-sm font-semibold">
            Semaine {week.index + 1}/{total}
            {isCurrent && (
              <span className="ml-2 rounded bg-accent px-1.5 py-0.5 text-xs text-accent-ink">en cours</span>
            )}
          </p>
          <p className="text-xs text-ink-3">
            {dayLabel(week.start, { day: "numeric", month: "short" })} –{" "}
            {dayLabel(end, { day: "numeric", month: "short" })} · {PHASE_LABELS[week.phase]}
            {week.deload && " · décharge"}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-sm font-medium tabular-nums">{km(week.volume_km)}</span>
          <span aria-hidden className={`text-ink-3 transition ${open ? "rotate-180" : ""}`}>
            ▾
          </span>
        </div>
      </button>
      {open && (
        <div className="space-y-3 border-t border-border px-4 py-3">
          <ul className="divide-y divide-border">
            {week.sessions.map((session) => (
              <SessionRow key={session.date + session.kind} session={session} today={today} />
            ))}
          </ul>
          {week.text && (
            <blockquote className="rounded-lg bg-surface-2 px-3 py-2 text-sm whitespace-pre-line text-ink-2">
              {week.text}
            </blockquote>
          )}
        </div>
      )}
    </li>
  );
}

function SessionRow({ session, today }: { session: Session; today: string }) {
  const isToday = session.date === today;
  const detail =
    session.reps && session.rep_m
      ? `${session.reps} × ${session.rep_m >= 1000 ? `${session.rep_m / 1000} km` : `${session.rep_m} m`}` +
        (session.recovery_s ? `, récup ${session.recovery_s} s` : "")
      : null;
  return (
    <li className={`flex items-start justify-between gap-3 py-2 ${isToday ? "font-medium" : ""}`}>
      <div>
        <p className="text-sm">
          <span className="inline-block w-24 text-ink-3 first-letter:uppercase">
            {isToday ? "Aujourd'hui" : dayLabel(session.date)}
          </span>
          {KIND_LABELS[session.kind]}
        </p>
        {detail && <p className="ml-24 text-xs text-ink-3">{detail}</p>}
      </div>
      <div className="text-right text-sm tabular-nums">
        <p>{km(session.distance_km)}</p>
        <p className="text-xs text-ink-3">{pace(session.pace_s_per_km)}</p>
      </div>
    </li>
  );
}
