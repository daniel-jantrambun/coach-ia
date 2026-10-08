import { type FormEvent, useState } from "react";
import { useAuth } from "../auth";
import { Alert, Button, errorMessage, Field } from "../ui";

/** Premier lancement : aucun compte n'existe, on crée le compte administrateur. */
export function SetupPage() {
  const { setup } = useAuth();
  const [displayName, setDisplayName] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (password !== confirm) {
      setError("Les deux mots de passe ne correspondent pas");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await setup({ username: username.trim(), password, display_name: displayName.trim() || undefined });
    } catch (e) {
      setError(errorMessage(e));
      setBusy(false);
    }
  }

  return (
    <div className="grid min-h-dvh place-items-center px-4 py-8">
      <form
        onSubmit={submit}
        className="w-full max-w-sm space-y-4 rounded-xl border border-border bg-surface p-6"
      >
        <div>
          <h1 className="text-xl font-semibold">🏃 Bienvenue sur Savapav</h1>
          <p className="mt-1 text-sm text-ink-2">
            Créez le compte administrateur. Il pourra ensuite créer les comptes des autres membres de la
            famille.
          </p>
        </div>
        <Field label="Prénom" value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
        <Field
          label="Nom d'utilisateur"
          autoComplete="username"
          autoCapitalize="none"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          hint="Lettres, chiffres, . _ -"
          required
        />
        <Field
          label="Mot de passe"
          type="password"
          autoComplete="new-password"
          minLength={10}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          hint="10 caractères minimum"
          required
        />
        <Field
          label="Confirmation"
          type="password"
          autoComplete="new-password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          required
        />
        {error && <Alert>{error}</Alert>}
        <Button type="submit" className="w-full" disabled={busy}>
          {busy ? "Création…" : "Créer le compte administrateur"}
        </Button>
      </form>
    </div>
  );
}
