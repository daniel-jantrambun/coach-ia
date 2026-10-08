import { type FormEvent, useState } from "react";
import { useAuth } from "../auth";
import { Alert, Button, errorMessage, Field } from "../ui";

export function LoginPage() {
  const { login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(username.trim(), password);
    } catch (e) {
      setError(errorMessage(e));
      setBusy(false);
    }
  }

  return (
    <div className="grid min-h-dvh place-items-center px-4">
      <form
        onSubmit={submit}
        className="w-full max-w-sm space-y-4 rounded-xl border border-border bg-surface p-6"
      >
        <div>
          <h1 className="text-xl font-semibold">🏃 Coach IA</h1>
          <p className="mt-1 text-sm text-ink-2">Connectez-vous avec le compte créé pour vous.</p>
        </div>
        <Field
          label="Nom d'utilisateur"
          autoComplete="username"
          autoCapitalize="none"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          required
        />
        <Field
          label="Mot de passe"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
        {error && <Alert>{error}</Alert>}
        <Button type="submit" className="w-full" disabled={busy}>
          {busy ? "Connexion…" : "Se connecter"}
        </Button>
      </form>
    </div>
  );
}
