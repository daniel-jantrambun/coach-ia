import { type FormEvent, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router";
import { type Analysis, type Axis, api, type Focus, type Sport, type SportProfile } from "../api";
import { AXIS_LABELS, km, minutes, SPORT_ORDER, SPORTS } from "../format";
import { Alert, Button, buttonClass, Card, errorMessage, Spinner } from "../ui";

const AXIS_HINTS: Record<Axis, string> = {
  maintien: "Garder le niveau actuel, sans augmenter la charge.",
  endurance: "Tenir plus longtemps : volume en hausse et une sortie longue chaque semaine.",
  vitesse: "Aller plus vite : une séance intense par semaine (fractionné, seuil).",
  technique: "Nager mieux : une séance d'éducatifs chaque semaine.",
  force: "Gagner en force : séances de renforcement alternées (bas, haut du corps, corps entier).",
};

const TREND_LABELS: Record<SportProfile["trend"], string> = {
  hausse: "↗ en hausse",
  baisse: "↘ en baisse",
  stable: "→ stable",
  nouveau: "nouveau",
};

const OTHER_SPORT_LABELS: Record<string, string> = {
  walking: "Marche",
  hiking: "Randonnée",
  training: "Yoga / mobilité",
  cross_country_skiing: "Ski de fond",
  alpine_skiing: "Ski",
  rowing: "Aviron",
  tennis: "Tennis",
};

export function NewBlockPage() {
  const navigate = useNavigate();
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [focus, setFocus] = useState<Focus>({});
  const [sessions, setSessions] = useState(4);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .analysis()
      .then((a) => {
        setAnalysis(a);
        // Par défaut : on garde les sports pratiqués, au niveau actuel.
        const detected = SPORT_ORDER.filter((s) => a.sports[s]);
        setFocus(Object.fromEntries(detected.map((s) => [s, "maintien"])));
        const current = detected.reduce((n, s) => n + (a.sports[s]?.recent_sessions_per_week ?? 0), 0);
        setSessions(Math.min(Math.max(Math.round(current), detected.length, 3), 12));
      })
      .catch((e) => setError(errorMessage(e)));
  }, []);

  if (error && !analysis) return <Alert>{error}</Alert>;
  if (!analysis) return <Spinner label="Analyse de vos activités…" />;

  const chosen = SPORT_ORDER.filter((s) => focus[s]);
  const minSessions = Math.max(chosen.length, 1);
  const current = SPORT_ORDER.reduce((n, s) => n + (analysis.sports[s]?.recent_sessions_per_week ?? 0), 0);
  // Les sports pratiqués d'abord, puis les autres.
  const ordered = [...SPORT_ORDER].sort((a, b) => Number(!analysis.sports[a]) - Number(!analysis.sports[b]));

  function choose(sport: Sport, axis: Axis | null) {
    const next = { ...focus };
    if (axis) next[sport] = axis;
    else delete next[sport];
    setFocus(next);
    const count = Object.keys(next).length;
    if (sessions < count) setSessions(count);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const plan = await api.createBlock({ focus, sessions_per_week: Math.max(sessions, minSessions) });
      navigate(`/plans/${plan.id}`);
    } catch (e) {
      setError(errorMessage(e));
      setBusy(false);
    }
  }

  return (
    <>
      <Card title={`Vos ${analysis.weeks} dernières semaines`}>
        {SPORT_ORDER.every((s) => !analysis.sports[s]) ? (
          <p className="text-sm text-ink-2">
            Aucune activité récente.{" "}
            <Link to="/activites" className="text-accent underline">
              Importez vos activités
            </Link>{" "}
            pour un plan adapté, ou choisissez directement vos sports ci-dessous : le plan démarrera
            doucement.
          </p>
        ) : (
          <ul className="divide-y divide-border">
            {SPORT_ORDER.filter((s) => analysis.sports[s]).map((sport) => {
              const p = analysis.sports[sport] as SportProfile;
              return (
                <li key={sport} className="flex items-start justify-between gap-3 py-2 text-sm">
                  <div>
                    <p className="font-medium">
                      <span aria-hidden>{SPORTS[sport].icon}</span> {SPORTS[sport].label}
                    </p>
                    <p className="text-xs text-ink-3">{TREND_LABELS[p.trend]}</p>
                  </div>
                  <div className="text-right tabular-nums">
                    <p>
                      {p.sessions_per_week.toLocaleString("fr-FR")} séance
                      {p.sessions_per_week >= 2 ? "s" : ""}
                      /sem
                    </p>
                    <p className="text-xs text-ink-3">
                      {minutes(p.minutes_per_week)}/sem
                      {p.km_per_week ? ` · ${km(p.km_per_week)}/sem` : ""}
                    </p>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
        {analysis.others.length > 0 && (
          <p className="mt-3 text-xs text-ink-3">
            Aussi :{" "}
            {analysis.others
              .map((o) => `${OTHER_SPORT_LABELS[o.sport] ?? o.sport} (${o.sessions}×, ${minutes(o.minutes)})`)
              .join(", ")}
            . Comptés dans votre fatigue, sans séances planifiées.
          </p>
        )}
      </Card>

      <Card title="Que voulez-vous améliorer ?">
        <form onSubmit={submit} className="space-y-5">
          {ordered.map((sport) => {
            const axis = focus[sport] ?? null;
            const options: (Axis | null)[] = [null, ...SPORTS[sport].axes];
            return (
              <fieldset key={sport}>
                <legend className="mb-2 text-sm font-medium">
                  <span aria-hidden>{SPORTS[sport].icon}</span> {SPORTS[sport].label}
                </legend>
                <div className="flex flex-wrap gap-2">
                  {options.map((option) => (
                    <button
                      key={option ?? "none"}
                      type="button"
                      aria-pressed={axis === option}
                      onClick={() => choose(sport, option)}
                      className={`min-h-10 rounded-lg border px-3 text-sm ${
                        axis === option
                          ? "border-accent bg-accent text-accent-ink"
                          : "border-border bg-surface text-ink"
                      }`}
                    >
                      {option ? AXIS_LABELS[option] : "Pas au programme"}
                    </button>
                  ))}
                </div>
                {axis && <p className="mt-1 text-xs text-ink-3">{AXIS_HINTS[axis]}</p>}
              </fieldset>
            );
          })}

          <fieldset>
            <legend className="mb-2 text-sm font-medium text-ink-2">
              Séances par semaine, tous sports confondus
            </legend>
            <div className="flex items-center gap-3">
              <Button
                variant="secondary"
                aria-label="Une séance de moins"
                onClick={() => setSessions(Math.max(sessions - 1, minSessions))}
                disabled={sessions <= minSessions}
              >
                −
              </Button>
              <span className="w-8 text-center text-xl font-semibold tabular-nums" aria-live="polite">
                {Math.max(sessions, minSessions)}
              </span>
              <Button
                variant="secondary"
                aria-label="Une séance de plus"
                onClick={() => setSessions(Math.min(sessions + 1, 12))}
                disabled={sessions >= 12}
              >
                +
              </Button>
            </div>
            <p className="mt-1 text-xs text-ink-3">
              {current > 0 ? `Actuellement ~${Math.round(current)} par semaine. ` : ""}
              Au moins 2 par sport à améliorer pour progresser ; 2 séances intenses max par semaine.
            </p>
          </fieldset>

          {error && <Alert>{error}</Alert>}
          <div className="flex flex-wrap gap-2">
            <Button type="submit" disabled={busy || chosen.length === 0}>
              {busy ? "Calcul…" : "Générer mon bloc de 4 semaines"}
            </Button>
            <Link to="/" className={buttonClass("secondary")}>
              Annuler
            </Link>
          </div>
        </form>
      </Card>

      <p className="text-center text-sm">
        <Link to="/plans/course" className="text-ink-2 underline">
          Vous préparez une course à une date précise ? Plan course à pied
        </Link>
      </p>
    </>
  );
}
