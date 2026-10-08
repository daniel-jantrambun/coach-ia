import { type FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router";
import { api } from "../api";
import { duration, pace, parseTime, todayIso } from "../format";
import { Alert, Button, buttonClass, Card, errorMessage, Field } from "../ui";

const DISTANCES = [
  { label: "5 km", km: 5 },
  { label: "10 km", km: 10 },
  { label: "Semi", km: 21.1 },
  { label: "Marathon", km: 42.195 },
];

export function NewPlanPage() {
  const navigate = useNavigate();
  const [distance, setDistance] = useState(21.1);
  const [target, setTarget] = useState("1:45:00");
  const [raceDate, setRaceDate] = useState("");
  const [runs, setRuns] = useState(4);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const targetSeconds = parseTime(target);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!targetSeconds) {
      setError("Temps visé illisible : utilisez h:mm:ss (1:45:00) ou mm:ss (45:00)");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const plan = await api.createPlan({
        distance_km: distance,
        target_time_s: targetSeconds,
        race_date: raceDate,
        runs_per_week: runs,
      });
      navigate(`/plans/${plan.id}`);
    } catch (e) {
      setError(errorMessage(e));
      setBusy(false);
    }
  }

  return (
    <Card title="Préparer une course">
      <form onSubmit={submit} className="space-y-5">
        <fieldset>
          <legend className="mb-2 text-sm font-medium text-ink-2">Distance</legend>
          <div className="grid grid-cols-4 gap-2">
            {DISTANCES.map((d) => (
              <button
                key={d.km}
                type="button"
                aria-pressed={distance === d.km}
                onClick={() => setDistance(d.km)}
                className={`min-h-10 rounded-lg border text-sm ${
                  distance === d.km
                    ? "border-accent bg-accent text-accent-ink"
                    : "border-border bg-surface text-ink"
                }`}
              >
                {d.label}
              </button>
            ))}
          </div>
        </fieldset>

        <Field
          label="Temps visé"
          inputMode="numeric"
          value={target}
          onChange={(e) => setTarget(e.target.value)}
          hint={
            targetSeconds
              ? `${duration(targetSeconds)} → allure course ${pace(targetSeconds / distance)}`
              : "Format h:mm:ss ou mm:ss"
          }
          required
        />

        <Field
          label="Date de la course"
          type="date"
          min={todayIso()}
          value={raceDate}
          onChange={(e) => setRaceDate(e.target.value)}
          hint="Au moins 3 semaines ; idéalement 12 à 18 selon la distance."
          required
        />

        <fieldset>
          <legend className="mb-2 text-sm font-medium text-ink-2">Sorties par semaine</legend>
          <div className="grid grid-cols-4 gap-2">
            {[3, 4, 5, 6].map((n) => (
              <button
                key={n}
                type="button"
                aria-pressed={runs === n}
                onClick={() => setRuns(n)}
                className={`min-h-10 rounded-lg border text-sm ${
                  runs === n ? "border-accent bg-accent text-accent-ink" : "border-border bg-surface text-ink"
                }`}
              >
                {n}
              </button>
            ))}
          </div>
        </fieldset>

        {error && <Alert>{error}</Alert>}
        <div className="flex gap-2">
          <Button type="submit" disabled={busy}>
            {busy ? "Calcul…" : "Générer le plan"}
          </Button>
          <Link to="/plans/nouveau" className={buttonClass("secondary")}>
            Annuler
          </Link>
        </div>
      </form>
    </Card>
  );
}
