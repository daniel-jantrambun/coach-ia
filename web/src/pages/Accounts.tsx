import { type FormEvent, useCallback, useEffect, useState } from "react";
import { type Account, api } from "../api";
import { useUser } from "../auth";
import { Alert, Button, Card, errorMessage, Field, Spinner } from "../ui";

type Message = { kind: "error" | "success"; text: string } | null;

/** Administration des comptes de la famille (admins uniquement). */
export function AccountsPage() {
  const [accounts, setAccounts] = useState<Account[] | null>(null);
  const [message, setMessage] = useState<Message>(null);

  const reload = useCallback(() => {
    api
      .accounts()
      .then(setAccounts)
      .catch((e) => setMessage({ kind: "error", text: errorMessage(e) }));
  }, []);

  useEffect(reload, [reload]);

  return (
    <>
      {message && <Alert kind={message.kind}>{message.text}</Alert>}
      <Card title={accounts ? `Comptes (${accounts.length})` : "Comptes"}>
        {accounts === null ? (
          <Spinner />
        ) : (
          <ul className="divide-y divide-border">
            {accounts.map((account) => (
              <AccountRow key={account.id} account={account} onChange={reload} onMessage={setMessage} />
            ))}
          </ul>
        )}
      </Card>
      <NewAccountCard onCreated={reload} onMessage={setMessage} />
    </>
  );
}

function AccountRow({
  account,
  onChange,
  onMessage,
}: {
  account: Account;
  onChange: () => void;
  onMessage: (m: Message) => void;
}) {
  const me = useUser();
  const isMe = account.id === me.id;
  const [mode, setMode] = useState<"idle" | "password" | "delete">("idle");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  async function run(action: () => Promise<void>, success: string) {
    setBusy(true);
    onMessage(null);
    try {
      await action();
      onMessage({ kind: "success", text: success });
      setMode("idle");
      setPassword("");
      onChange();
    } catch (e) {
      onMessage({ kind: "error", text: errorMessage(e) });
    } finally {
      setBusy(false);
    }
  }

  const resetPassword = (event: FormEvent) => {
    event.preventDefault();
    run(
      () => api.resetPassword(account.id, password),
      `Mot de passe de ${account.display_name} modifié. Transmettez-le-lui ; ses sessions ont été fermées.`,
    );
  };

  return (
    <li className="space-y-3 py-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="font-medium">
            {account.display_name}
            {account.is_admin && (
              <span className="ml-2 rounded bg-surface-2 px-1.5 py-0.5 text-xs font-normal text-ink-2">
                Admin
              </span>
            )}
            {isMe && <span className="ml-2 text-xs font-normal text-ink-3">(vous)</span>}
          </p>
          <p className="text-xs text-ink-3">
            @{account.username} · {account.activities} activité{account.activities > 1 ? "s" : ""} ·{" "}
            {account.plans} plan{account.plans > 1 ? "s" : ""}
          </p>
          <p className="text-xs text-ink-3">
            Garmin :{" "}
            {account.garmin_connected
              ? account.garmin_error
                ? "⚠ dernière synchro en échec"
                : account.last_sync_at
                  ? `synchro le ${new Date(account.last_sync_at).toLocaleDateString("fr-FR")}`
                  : "connecté"
              : "non connecté"}
          </p>
        </div>
        {mode === "idle" && (
          <div className="flex gap-2">
            {!isMe && (
              <Button variant="secondary" onClick={() => setMode("password")}>
                Mot de passe
              </Button>
            )}
            {!isMe && (
              <Button variant="danger" onClick={() => setMode("delete")}>
                Supprimer
              </Button>
            )}
          </div>
        )}
      </div>

      {mode === "password" && (
        <form onSubmit={resetPassword} className="space-y-3 rounded-lg bg-surface-2 p-3">
          <Field
            label={`Nouveau mot de passe pour ${account.display_name}`}
            type="text"
            autoComplete="off"
            minLength={10}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            hint="10 caractères minimum. Affiché en clair pour pouvoir le transmettre."
            required
          />
          <div className="flex gap-2">
            <Button type="submit" disabled={busy}>
              Enregistrer
            </Button>
            <Button variant="secondary" onClick={() => setMode("idle")} disabled={busy}>
              Annuler
            </Button>
          </div>
        </form>
      )}

      {mode === "delete" && (
        <div className="space-y-3 rounded-lg border border-critical/40 p-3">
          <p className="text-sm">
            Supprimer le compte de <strong>{account.display_name}</strong> ? Ses activités, ses plans et sa
            connexion Garmin seront définitivement effacés.
          </p>
          <div className="flex gap-2">
            <Button
              variant="danger"
              disabled={busy}
              onClick={() =>
                run(() => api.deleteAccount(account.id), `Compte de ${account.display_name} supprimé.`)
              }
            >
              {busy ? "Suppression…" : "Supprimer définitivement"}
            </Button>
            <Button variant="secondary" onClick={() => setMode("idle")} disabled={busy}>
              Annuler
            </Button>
          </div>
        </div>
      )}
    </li>
  );
}

function NewAccountCard({
  onCreated,
  onMessage,
}: {
  onCreated: () => void;
  onMessage: (m: Message) => void;
}) {
  const [displayName, setDisplayName] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [isAdmin, setIsAdmin] = useState(false);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    onMessage(null);
    try {
      const user = await api.createAccount({
        username: username.trim(),
        password,
        display_name: displayName.trim() || undefined,
        is_admin: isAdmin,
      });
      onMessage({
        kind: "success",
        text: `Compte de ${user.display_name} créé. Transmettez-lui son nom d'utilisateur (${user.username}) et son mot de passe.`,
      });
      setDisplayName("");
      setUsername("");
      setPassword("");
      setIsAdmin(false);
      onCreated();
    } catch (e) {
      onMessage({ kind: "error", text: errorMessage(e) });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title="Nouveau compte">
      <form onSubmit={submit} className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Prénom" value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
          <Field
            label="Nom d'utilisateur"
            autoComplete="off"
            autoCapitalize="none"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            hint="Lettres, chiffres, . _ -"
            required
          />
        </div>
        <Field
          label="Mot de passe"
          type="text"
          autoComplete="off"
          minLength={10}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          hint="10 caractères minimum. Affiché en clair pour pouvoir le transmettre ; la personne pourra le changer."
          required
        />
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            className="size-4 accent-[var(--accent)]"
            checked={isAdmin}
            onChange={(e) => setIsAdmin(e.target.checked)}
          />
          Administrateur (peut gérer les comptes)
        </label>
        <Button type="submit" disabled={busy}>
          {busy ? "Création…" : "Créer le compte"}
        </Button>
      </form>
    </Card>
  );
}
