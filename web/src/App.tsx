import { Navigate, NavLink, Route, Routes } from "react-router";
import { useAuth } from "./auth";
import { AccountsPage } from "./pages/Accounts";
import { ActivitiesPage } from "./pages/Activities";
import { ActivityDetailPage } from "./pages/ActivityDetail";
import { GraphsPage } from "./pages/Graphs";
import { LoginPage } from "./pages/Login";
import { NewBlockPage } from "./pages/NewBlock";
import { NewPlanPage } from "./pages/NewPlan";
import { PlanPage } from "./pages/Plan";
import { ProfilePage } from "./pages/Profile";
import { SetupPage } from "./pages/Setup";
import { Spinner } from "./ui";

const NAV = [
  { to: "/", label: "Mon plan", icon: "📅", admin: false },
  { to: "/activites", label: "Activités", icon: "📈", admin: false },
  { to: "/graphes", label: "Graphes", icon: "📊", admin: false },
  { to: "/comptes", label: "Comptes", icon: "👥", admin: true },
  { to: "/profil", label: "Profil", icon: "👤", admin: false },
];

export function App() {
  const { user, loading, needsSetup } = useAuth();

  if (loading) {
    return (
      <div className="grid min-h-dvh place-items-center">
        <Spinner />
      </div>
    );
  }
  if (!user) return needsSetup ? <SetupPage /> : <LoginPage />;

  const nav = NAV.filter((item) => !item.admin || user.is_admin);

  return (
    <div className="min-h-dvh pb-20 sm:pb-0">
      <header className="sticky top-0 z-10 border-b border-border bg-surface/90 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-3xl items-center justify-between px-4">
          <span className="font-semibold">🏃 Savapav</span>
          <nav className="hidden gap-1 sm:flex">
            {nav.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/"}
                className={({ isActive }) =>
                  `rounded-lg px-3 py-1.5 text-sm ${isActive ? "bg-surface-2 font-medium text-ink" : "text-ink-2 hover:text-ink"}`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
          <span className="text-sm text-ink-3 sm:hidden">{user.display_name}</span>
        </div>
      </header>

      <main className="mx-auto max-w-3xl space-y-4 px-4 py-4 sm:py-6">
        <Routes>
          <Route path="/" element={<PlanPage />} />
          <Route path="/plans/nouveau" element={<NewBlockPage />} />
          <Route path="/plans/course" element={<NewPlanPage />} />
          <Route path="/plans/:planId" element={<PlanPage />} />
          <Route path="/activites" element={<ActivitiesPage />} />
          <Route path="/activites/:activityId" element={<ActivityDetailPage />} />
          <Route path="/graphes" element={<GraphsPage />} />
          <Route path="/profil" element={<ProfilePage />} />
          {user.is_admin && <Route path="/comptes" element={<AccountsPage />} />}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>

      {/* Barre d'onglets en bas sur téléphone */}
      <nav
        className={`fixed inset-x-0 bottom-0 z-10 grid border-t border-border bg-surface pb-[env(safe-area-inset-bottom)] sm:hidden ${
          nav.length === 5 ? "grid-cols-5" : "grid-cols-4"
        }`}
      >
        {nav.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "/"}
            className={({ isActive }) =>
              `flex flex-col items-center gap-0.5 py-2 text-xs ${isActive ? "font-medium text-accent" : "text-ink-3"}`
            }
          >
            <span aria-hidden className="text-lg leading-none">
              {item.icon}
            </span>
            {item.label}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
