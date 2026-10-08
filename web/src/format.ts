import type { SessionKind, Week } from "./api";

export const KIND_LABELS: Record<SessionKind, string> = {
  easy: "Footing",
  long: "Sortie longue",
  tempo: "Seuil",
  intervals: "Fractionné",
  strides: "Footing + lignes droites",
  race: "Course",
};

export const PHASE_LABELS: Record<Week["phase"], string> = {
  base: "Base",
  build: "Construction",
  taper: "Affûtage",
  race: "Semaine de course",
};

export function pace(secondsPerKm: number): string {
  const s = Math.round(secondsPerKm);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}/km`;
}

export function duration(seconds: number): string {
  const s = Math.round(seconds);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const rest = s % 60;
  return h > 0 ? `${h}h${String(m).padStart(2, "0")}` : `${m}:${String(rest).padStart(2, "0")}`;
}

export function km(value: number): string {
  return `${value.toLocaleString("fr-FR", { maximumFractionDigits: 1 })} km`;
}

// Les dates du plan sont des jours calendaires ("2026-10-13") : on les lit en heure locale.
export function parseDay(day: string): Date {
  const [y, m, d] = day.split("-").map(Number);
  return new Date(y, m - 1, d);
}

export function dayLabel(
  day: string,
  opts: Intl.DateTimeFormatOptions = { weekday: "short", day: "numeric", month: "short" },
) {
  return parseDay(day).toLocaleDateString("fr-FR", opts);
}

export function todayIso(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}

/** "1:45:00", "45:00" ou "45" (minutes) → secondes ; null si illisible. */
export function parseTime(value: string): number | null {
  const parts = value.trim().split(":");
  if (parts.some((p) => !/^\d+$/.test(p)) || parts.length > 3) return null;
  const nums = parts.map(Number);
  if (nums.length === 1) return nums[0] * 60;
  if (nums.length === 2) return nums[0] * 60 + nums[1];
  return nums[0] * 3600 + nums[1] * 60 + nums[2];
}

export function distanceLabel(distanceKm: number): string {
  if (Math.abs(distanceKm - 42.195) < 0.1) return "Marathon";
  if (Math.abs(distanceKm - 21.1) < 0.1) return "Semi-marathon";
  return km(distanceKm);
}
