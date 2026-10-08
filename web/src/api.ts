// Client de l'API FastAPI (même origine : le cookie de session suit automatiquement).

export type User = {
  id: number;
  username: string;
  display_name: string;
  hr_rest: number;
  hr_max: number;
  is_admin: boolean;
};

export type NewUser = { username: string; password: string; display_name?: string; is_admin?: boolean };

export type Account = {
  id: number;
  username: string;
  display_name: string;
  is_admin: boolean;
  created_at: string;
  garmin_connected: boolean;
  last_sync_at: string | null;
  garmin_error: string | null;
  activities: number;
  plans: number;
};

export type SessionKind = "easy" | "long" | "tempo" | "intervals" | "strides" | "race";

export type Session = {
  date: string;
  kind: SessionKind;
  distance_km: number;
  pace_s_per_km: number;
  reps: number | null;
  rep_m: number | null;
  recovery_s: number | null;
};

export type Week = {
  index: number;
  start: string;
  phase: "base" | "build" | "taper" | "race";
  volume_km: number;
  deload: boolean;
  sessions: Session[];
  text: string | null;
};

export type Goal = {
  distance_km: number;
  target_time_s: number;
  race_date: string;
  runs_per_week: number;
};

export type Plan = {
  id: number;
  created_at: string;
  goal: Goal;
  current_weekly_km: number;
  weeks: Week[];
  paces: Record<string, number>;
  warnings: string[];
  narrating: boolean;
  narrate_error: string | null;
};

export type PlanSummary = { id: number; created_at: string; goal: Goal };

export type Activity = {
  id: string;
  sport: string;
  start_time: string;
  duration_s: number;
  distance_m: number | null;
  avg_hr: number | null;
};

export type LoadPoint = { day: string; load: number; ctl: number; atl: number; tsb: number };

export type GarminStatus = {
  connected: boolean;
  connected_at?: string;
  last_sync_at?: string | null;
  last_error?: string | null;
};

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

// Appelé sur une réponse 401 : l'application renvoie vers l'écran de connexion.
let onUnauthorized = () => {};
export function setUnauthorizedHandler(handler: () => void) {
  onUnauthorized = handler;
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method, credentials: "same-origin" };
  if (body instanceof FormData) {
    init.body = body;
  } else if (body !== undefined) {
    init.body = JSON.stringify(body);
    init.headers = { "Content-Type": "application/json" };
  }
  const response = await fetch(`/api${path}`, init);
  if (!response.ok) {
    if (response.status === 401 && path !== "/login") onUnauthorized();
    let message = `Erreur ${response.status}`;
    try {
      const data = await response.json();
      if (typeof data.detail === "string") message = data.detail;
      else if (Array.isArray(data.detail)) message = "Valeurs invalides, vérifiez le formulaire";
    } catch {
      // réponse sans JSON : on garde le message générique
    }
    throw new ApiError(response.status, message);
  }
  return (response.status === 204 ? undefined : await response.json()) as T;
}

export const api = {
  setupStatus: () => request<{ needs_setup: boolean }>("GET", "/setup"),
  setup: (account: NewUser) => request<User>("POST", "/setup", account),
  login: (username: string, password: string) => request<User>("POST", "/login", { username, password }),
  logout: () => request<void>("POST", "/logout"),
  me: () => request<User>("GET", "/me"),
  updateMe: (fields: Partial<Pick<User, "display_name" | "hr_rest" | "hr_max">>) =>
    request<User>("PATCH", "/me", fields),
  changePassword: (current_password: string, new_password: string) =>
    request<void>("POST", "/me/password", { current_password, new_password }),

  garminStatus: () => request<GarminStatus>("GET", "/me/garmin"),
  garminConnect: (email: string, password: string) =>
    request<{ status: "connected" | "needs_mfa" }>("POST", "/me/garmin", { email, password }),
  garminMfa: (code: string) => request<{ status: "connected" }>("POST", "/me/garmin/mfa", { code }),
  garminDisconnect: () => request<void>("DELETE", "/me/garmin"),
  garminSync: () => request<{ imported: number; skipped: number }>("POST", "/me/garmin/sync"),

  accounts: () => request<Account[]>("GET", "/admin/users"),
  createAccount: (account: NewUser) => request<User>("POST", "/admin/users", account),
  deleteAccount: (id: number) => request<void>("DELETE", `/admin/users/${id}`),
  resetPassword: (id: number, new_password: string) =>
    request<void>("POST", `/admin/users/${id}/password`, { new_password }),

  activities: (limit = 50) => request<Activity[]>("GET", `/activities?limit=${limit}`),
  importFile: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<{ imported: number; skipped: number }>("POST", "/activities/import", form);
  },
  load: (days = 120) => request<LoadPoint[]>("GET", `/load?days=${days}`),

  plans: () => request<PlanSummary[]>("GET", "/plans"),
  plan: (id: number) => request<Plan>("GET", `/plans/${id}`),
  createPlan: (goal: Goal) => request<Plan>("POST", "/plans", goal),
  narrate: (id: number) => request<{ status: string }>("POST", `/plans/${id}/narrate`),
};
