import {
  Check,
  Copy,
  Home,
  Link2,
  Loader2,
  Trash2,
  UserPlus,
} from "lucide-react";
import { useState, type FormEvent } from "react";
import useSWR from "swr";
import {
  createInvitation,
  getHousehold,
  listHouseholdUsers,
  listInvitations,
  removeHouseholdUser,
  renameHousehold,
  revokeInvitation,
  setUserRole,
} from "../../lib/api/household";
import type { HouseholdRole, HouseholdUser } from "../../lib/types/household";
import { INPUT_CLASS } from "../../lib/utils";

const ROLES: HouseholdRole[] = ["admin", "member", "viewer"];

/**
 * Household administration: rename, member list with role management, and
 * the invitation flow. Everything except the household name is admin-only —
 * non-admins get the read-only name card and a 403-backed empty state.
 */
export function HouseholdSection() {
  const { data: household } = useSWR("/household", getHousehold);
  const isAdmin = household?.my_role === "admin";

  return (
    <section
      aria-label="Household"
      className="space-y-3 rounded-xl border border-border bg-card p-5 shadow-sm"
    >
      <h2 className="flex items-center gap-2 text-sm font-semibold">
        <Home className="size-4 text-primary" aria-hidden />
        Household {household ? `· ${household.my_role}` : ""}
      </h2>
      <NameCard />
      {isAdmin && <MembersCard />}
      {isAdmin && <InvitesCard />}
    </section>
  );
}

function NameCard() {
  const { data: household, mutate } = useSWR("/household", getHousehold);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  if (!household) return null;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await renameHousehold({ name });
      await mutate();
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Rename failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="flex items-end gap-2">
      <label className="flex-1 space-y-1.5 text-sm font-medium">
        Household name
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder={household.name}
          className={INPUT_CLASS}
        />
      </label>
      <button
        type="submit"
        disabled={busy || !name.trim()}
        className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-60"
      >
        {busy ? (
          <Loader2 className="size-4 animate-spin" aria-hidden />
        ) : saved ? (
          <Check className="size-4" aria-hidden />
        ) : null}
        Rename
      </button>
      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
    </form>
  );
}

function MembersCard() {
  const {
    data: users,
    error,
    mutate,
  } = useSWR("/household/users", listHouseholdUsers);

  if (error) {
    return (
      <p className="text-sm text-muted-foreground">
        Member management requires the household admin role.
      </p>
    );
  }
  if (!users) return null;

  async function changeRole(user: HouseholdUser, role: HouseholdRole) {
    await setUserRole(user.user_id, role);
    await mutate();
  }

  async function remove(user: HouseholdUser) {
    if (!window.confirm(`Remove ${user.username} from the household?`)) return;
    await removeHouseholdUser(user.user_id);
    await mutate();
  }

  return (
    <div className="space-y-2">
      <p className="text-sm font-medium">Members</p>
      <ul className="divide-y divide-border rounded-lg border border-border">
        {users.map((user) => (
          <li key={user.user_id} className="flex items-center gap-3 px-3 py-2">
            <span className="flex-1 text-sm">
              {user.username}
              {user.is_primary && (
                <span className="ml-2 text-xs text-muted-foreground">
                  owner
                </span>
              )}
            </span>
            <label className="sr-only" htmlFor={`role-${user.user_id}`}>
              Role for {user.username}
            </label>
            <select
              id={`role-${user.user_id}`}
              value={user.role}
              disabled={user.is_primary}
              onChange={(e) =>
                void changeRole(user, e.target.value as HouseholdRole)
              }
              className="rounded-lg border border-input bg-background px-2 py-1 text-xs"
            >
              {ROLES.map((role) => (
                <option key={role} value={role}>
                  {role}
                </option>
              ))}
            </select>
            <button
              type="button"
              aria-label={`Remove ${user.username}`}
              disabled={user.is_primary}
              onClick={() => void remove(user)}
              className="rounded-lg p-1.5 text-danger transition-colors hover:bg-danger/10 disabled:opacity-30"
            >
              <Trash2 className="size-4" aria-hidden />
            </button>
          </li>
        ))}
      </ul>
      <p className="text-xs text-muted-foreground">
        Viewers are read-only: they can browse records and chat but cannot
        change anything.
      </p>
    </div>
  );
}

function InvitesCard() {
  const { data: invitations, mutate } = useSWR(
    "/household/users/invitations",
    listInvitations,
  );
  const [role, setRole] = useState<HouseholdRole>("member");
  const [created, setCreated] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function invite() {
    setBusy(true);
    setError(null);
    try {
      const invitation = await createInvitation(role);
      setCreated(invitation.token);
      await mutate();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create invite.");
    } finally {
      setBusy(false);
    }
  }

  async function copyToken() {
    if (!created) return;
    await navigator.clipboard.writeText(created);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  const pending = (invitations ?? []).filter((i) => !i.accepted);

  return (
    <div className="space-y-2">
      <p className="text-sm font-medium">Invitations</p>
      <div className="flex items-end gap-2">
        <label className="space-y-1.5 text-sm font-medium">
          Role for the next invite
          <select
            value={role}
            onChange={(e) => setRole(e.target.value as HouseholdRole)}
            className="rounded-lg border border-input bg-background px-2 py-1.5 text-sm"
          >
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          onClick={() => void invite()}
          disabled={busy}
          className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-60"
        >
          {busy ? (
            <Loader2 className="size-4 animate-spin" aria-hidden />
          ) : (
            <UserPlus className="size-4" aria-hidden />
          )}
          Create invite
        </button>
      </div>

      {created && (
        <div className="space-y-1 rounded-lg border border-border bg-background p-3">
          <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Link2 className="size-3.5" aria-hidden />
            Share this token — it works once and expires in 7 days. It won't be
            shown again.
          </p>
          <div className="flex items-center gap-2">
            <code className="flex-1 break-all rounded bg-muted px-2 py-1 font-mono text-xs">
              {created}
            </code>
            <button
              type="button"
              onClick={() => void copyToken()}
              aria-label="Copy invitation token"
              className="rounded-lg p-1.5 transition-colors hover:bg-muted"
            >
              {copied ? (
                <Check className="size-4 text-primary" aria-hidden />
              ) : (
                <Copy className="size-4" aria-hidden />
              )}
            </button>
          </div>
        </div>
      )}

      {pending.length > 0 && (
        <ul className="divide-y divide-border rounded-lg border border-border">
          {pending.map((invitation) => (
            <li
              key={invitation.id}
              className="flex items-center gap-3 px-3 py-2 text-sm"
            >
              <span className="flex-1">
                {invitation.role} · expires{" "}
                {new Date(invitation.expires_at).toLocaleDateString()}
              </span>
              <button
                type="button"
                aria-label="Revoke invitation"
                onClick={() =>
                  void revokeInvitation(invitation.id).then(() => mutate())
                }
                className="rounded-lg p-1.5 text-danger transition-colors hover:bg-danger/10"
              >
                <Trash2 className="size-4" aria-hidden />
              </button>
            </li>
          ))}
        </ul>
      )}
      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
    </div>
  );
}
