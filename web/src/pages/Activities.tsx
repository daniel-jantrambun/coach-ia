import { type ChangeEvent, useCallback, useEffect, useState } from "react";
import { Link } from "react-router";
import { type Activity, api, type GarminStatus, type LoadPoint } from "../api";
import { duration, km, pace } from "../format";
import { LoadChart } from "../LoadChart";
import { Alert, Button, buttonClass, Card, errorMessage, Spinner } from "../ui";

const SPORT_LABELS: Record<string, string> = {
  running: "Course",
  cycling: "Vélo",
  swimming: "Natation",
  walking: "Marche",
  hiking: "Randonnée",
  training: "Renforcement",
};

// Fraîcheur (TSB) : la couleur est doublée d'une icône et d'un libellé.
function freshness(tsb: number) {
  if (tsb > 5) return { label: "Frais", icon: "●", className: "text-good" };
  if (tsb >= -10) return { label: "Équilibré", icon: "●", className: "text-ink-2" };
  if (tsb >= -30) return { label: "En charge", icon: "▲", className: "text-warning" };
  return { label: "Fatigue élevée", icon: "■", className: "text-critical" };
}

export function ActivitiesPage() {
  const [activities, setActivities] = useState<Activity[] | null>(null);
  const [load, setLoad] = useState<LoadPoint[] | null>(null);
  const [garmin, setGarmin] = useState<GarminStatus | null>(null);
  const [message, setMessage] = useState<{ kind: "error" | "success"; text: string } | null>(null);
  const [busy, setBusy] = useState<"import" | "sync" | null>(null);

  const reload = useCallback(() => {
    Promise.all([api.activities(), api.load(), api.garminStatus()])
      .then(([a, l, g]) => {
        setActivities(a);
        setLoad(l);
        setGarmin(g);
      })
      .catch((e) => setMessage({ kind: "error", text: errorMessage(e) }));
  }, []);

  useEffect(reload, [reload]);

  async function importFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setBusy("import");
    setMessage(null);
    try {
      const { imported, skipped } = await api.importFile(file);
      setMessage({
        kind: "success",
        text: `${imported} activité(s) importée(s)${skipped ? `, ${skipped} fichier(s) ignoré(s)` : ""}.`,
      });
      reload();
    } catch (e) {
      setMessage({ kind: "error", text: errorMessage(e) });
    } finally {
      setBusy(null);
    }
  }

  async function sync() {
    setBusy("sync");
    setMessage(null);
    try {
      const { imported } = await api.garminSync();
      setMessage({ kind: "success", text: `Synchro Garmin terminée : ${imported} activité(s) à jour.` });
      reload();
    } catch (e) {
      setMessage({ kind: "error", text: errorMessage(e) });
    } finally {
      setBusy(null);
    }
  }

  const today = load?.at(-1);
  const status = today ? freshness(today.tsb) : null;

  return (
    <>
      {message && <Alert kind={message.kind}>{message.text}</Alert>}

      <Card title="Forme et fatigue">
        {load === null ? (
          <Spinner />
        ) : load.length === 0 || !today || !status ? (
          <p className="text-sm text-ink-2">
            Importez vos activités (avec fréquence cardiaque) pour suivre votre charge d'entraînement.
          </p>
        ) : (
          <div className="space-y-4">
            <div className="flex flex-wrap items-end gap-x-6 gap-y-2">
              <div>
                <p className="text-xs text-ink-3">Fraîcheur du jour</p>
                <p className="text-3xl font-semibold tabular-nums">
                  {today.tsb > 0 ? "+" : ""}
                  {Math.round(today.tsb)}
                </p>
              </div>
              <p className={`pb-1 text-sm font-medium ${status.className}`}>
                <span aria-hidden>{status.icon}</span> {status.label}
              </p>
              <p className="pb-1 text-xs text-ink-3">
                = forme − fatigue. Négatif : vous accumulez de la charge.
              </p>
            </div>
            {load.length > 1 && <LoadChart data={load} />}
          </div>
        )}
      </Card>

      <Card title="Ajouter des activités">
        <div className="flex flex-wrap gap-2">
          {garmin?.connected ? (
            <Button onClick={sync} disabled={busy !== null}>
              {busy === "sync" ? "Synchro…" : "Synchroniser Garmin"}
            </Button>
          ) : (
            <Link to="/profil" className={buttonClass("primary")}>
              Connecter Garmin
            </Link>
          )}
          <label className={`${buttonClass("secondary")} cursor-pointer`}>
            {busy === "import" ? "Import…" : "Importer un fichier"}
            <input
              type="file"
              accept=".fit,.zip"
              className="sr-only"
              onChange={importFile}
              disabled={busy !== null}
            />
          </label>
        </div>
        <p className="mt-2 text-xs text-ink-3">
          Fichier .fit, ou le .zip de l'export complet Garmin (Compte → Exporter vos données) tel quel.
        </p>
      </Card>

      <Card title="Dernières activités">
        {activities === null ? (
          <Spinner />
        ) : activities.length === 0 ? (
          <p className="text-sm text-ink-2">Aucune activité pour l'instant.</p>
        ) : (
          <ul className="divide-y divide-border">
            {activities.map((a) => (
              <li key={a.id} className="flex items-center justify-between gap-3 py-2 text-sm">
                <div>
                  <p>{SPORT_LABELS[a.sport] ?? a.sport}</p>
                  <p className="text-xs text-ink-3 first-letter:uppercase">
                    {new Date(a.start_time).toLocaleDateString("fr-FR", {
                      weekday: "short",
                      day: "numeric",
                      month: "short",
                      year: "numeric",
                    })}
                  </p>
                </div>
                <div className="text-right tabular-nums">
                  <p>
                    {a.distance_m ? km(a.distance_m / 1000) : ""} · {duration(a.duration_s)}
                  </p>
                  <p className="text-xs text-ink-3">
                    {a.sport === "running" && a.distance_m ? pace(a.duration_s / (a.distance_m / 1000)) : ""}
                    {a.avg_hr ? ` · ${Math.round(a.avg_hr)} bpm` : ""}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </>
  );
}
