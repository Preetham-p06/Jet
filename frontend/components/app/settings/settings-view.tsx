"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { Check, Copy, KeyRound, UserPlus, X } from "lucide-react";
import { endpoints, type InviteCreated, type Role, type Workspace } from "@/lib/api/endpoints";
import { fieldErrorOf } from "@/lib/api/errors";
import { useApi, useMutation } from "@/lib/api/hooks";
import { cn } from "@/lib/utils";
import { useCan, useMe } from "../me-provider";
import { fmtDate, fmtRelative, humanize } from "../fmt";
import { Btn, ErrorState, Field, InlineError, LoadingBlock, Panel, Pill, TableScroll, inputCls, selectCls, tdCls, thCls } from "../ui";

const ROLES: Role[] = ["admin", "broker", "assistant"];

export function SettingsView() {
  const isAdmin = useCan("workspace.admin");
  const usersAdmin = useCan("users.admin");
  return (
    <div className="mt-8 grid grid-cols-1 gap-5 lg:grid-cols-2">
      <WorkspacePanel editable={isAdmin} />
      <PasswordPanel />
      {usersAdmin && <UsersPanel />}
      {usersAdmin && <InvitesPanel />}
    </div>
  );
}

function WorkspacePanel({ editable }: { editable: boolean }) {
  const router = useRouter();
  const ws = useApi("workspace", () => endpoints.workspace());
  return (
    <Panel title="Workspace" sub={editable ? "Applies to every trip in this workspace." : "Only admins can change these."}>
      {ws.loading ? (
        <LoadingBlock rows={3} />
      ) : ws.error && !ws.data ? (
        <ErrorState error={ws.error} onRetry={ws.reload} />
      ) : ws.data ? (
        <WorkspaceForm
          key={ws.data.updated_at}
          ws={ws.data}
          editable={editable}
          onSaved={(w) => {
            ws.setData(() => w);
            router.refresh();
          }}
        />
      ) : null}
    </Panel>
  );
}

function WorkspaceForm({ ws, editable, onSaved }: { ws: Workspace; editable: boolean; onSaved: (w: Workspace) => void }) {
  const [name, setName] = useState(ws.name);
  const [threshold, setThreshold] = useState(ws.review_threshold);
  const [markup, setMarkup] = useState(String(ws.default_markup_pct));
  const [saved, setSaved] = useState(false);
  const save = useMutation(endpoints.patchWorkspace);
  const m = Number(markup);
  const markupOk = markup !== "" && Number.isFinite(m) && m >= 0 && m <= 50;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const w = await save.run({ name: name.trim(), review_threshold: threshold, default_markup_pct: markup });
    if (w) {
      setSaved(true);
      onSaved(w);
    }
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-5">
      <Field label="Workspace name" htmlFor="ws-name" error={fieldErrorOf(save.error, "name")}>
        <input id="ws-name" value={name} disabled={!editable} onChange={(e) => setName(e.target.value)} className={inputCls} required />
      </Field>
      <Field
        label={`Review threshold · ${threshold}%`}
        htmlFor="ws-threshold"
        error={fieldErrorOf(save.error, "review_threshold")}
        hint="Fields extracted below this confidence go to the review queue and must be locked before a proposal."
      >
        <div className="flex items-center gap-3">
          <span className="font-mono text-[11px] text-fg-dim">50</span>
          <input
            id="ws-threshold"
            type="range"
            min={50}
            max={100}
            step={1}
            value={threshold}
            disabled={!editable}
            onChange={(e) => setThreshold(Number(e.target.value))}
            className="flex-1 accent-[#59d9ff]"
          />
          <span className="font-mono text-[11px] text-fg-dim">100</span>
        </div>
      </Field>
      <Field label="Default markup %" htmlFor="ws-markup" hint="0–50. Pre-fills new proposals; brokers can change it per proposal." error={fieldErrorOf(save.error, "default_markup_pct")}>
        <input
          id="ws-markup"
          inputMode="decimal"
          value={markup}
          disabled={!editable}
          onChange={(e) => setMarkup(e.target.value)}
          className={cn(inputCls, "tabular w-28 font-mono", !markupOk && "border-amber/50")}
        />
      </Field>
      <InlineError error={save.error} shownInline={["name", "review_threshold", "default_markup_pct"]} />
      {editable && (
        <div className="flex items-center justify-end gap-3">
          {saved && !save.pending && <span className="inline-flex items-center gap-1 text-xs text-green"><Check className="h-3.5 w-3.5" aria-hidden="true" /> Saved</span>}
          <Btn type="submit" tone="primary" pending={save.pending} disabled={!markupOk || !name.trim()}>
            Save settings
          </Btn>
        </div>
      )}
    </form>
  );
}

function PasswordPanel() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [done, setDone] = useState(false);
  const [local, setLocal] = useState<string | null>(null);
  const change = useMutation(endpoints.changePassword);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setLocal(null);
    setDone(false);
    if (next.length < 10) return setLocal("Use at least 10 characters.");
    if (next !== confirm) return setLocal("The new passwords don't match.");
    if (await change.run(current, next)) {
      setDone(true);
      setCurrent("");
      setNext("");
      setConfirm("");
    }
  }

  return (
    <Panel title="Change password" sub="Signs out your other sessions.">
      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        <Field label="Current password" htmlFor="pw-cur" error={fieldErrorOf(change.error, "current_password")}>
          <input id="pw-cur" type="password" autoComplete="current-password" required value={current} onChange={(e) => setCurrent(e.target.value)} className={inputCls} />
        </Field>
        <Field label="New password" htmlFor="pw-new" error={fieldErrorOf(change.error, "new_password")}>
          <input id="pw-new" type="password" autoComplete="new-password" required value={next} onChange={(e) => setNext(e.target.value)} className={inputCls} />
        </Field>
        <Field label="Confirm new password" htmlFor="pw-confirm">
          <input id="pw-confirm" type="password" autoComplete="new-password" required value={confirm} onChange={(e) => setConfirm(e.target.value)} className={inputCls} />
        </Field>
        {local && <p role="alert" className="text-xs text-amber">{local}</p>}
        <InlineError error={change.error} shownInline={["current_password", "new_password"]} />
        <div className="flex items-center justify-end gap-3">
          {done && <span className="inline-flex items-center gap-1 text-xs text-green"><Check className="h-3.5 w-3.5" aria-hidden="true" /> Password changed</span>}
          <Btn type="submit" pending={change.pending}>
            <KeyRound className="h-3.5 w-3.5" aria-hidden="true" /> Change password
          </Btn>
        </div>
      </form>
    </Panel>
  );
}

function UsersPanel() {
  const me = useMe();
  const users = useApi("users", () => endpoints.users());
  const patch = useMutation(async (id: string, body: { role?: Role; is_active?: boolean }) => {
    const u = await endpoints.patchUser(id, body);
    users.setData((prev) => prev && { ...prev, items: prev.items.map((x) => (x.id === u.id ? u : x)) });
    return u;
  });

  return (
    <Panel title="Users & roles" sub="Assistants can ingest and organise; brokers review, resolve and propose; admins manage the workspace." className="lg:col-span-2" bodyClassName="p-0 sm:p-0">
      {users.loading ? (
        <div className="p-5"><LoadingBlock rows={3} /></div>
      ) : users.error && !users.data ? (
        <div className="p-5"><ErrorState error={users.error} onRetry={users.reload} /></div>
      ) : (
        <>
          <TableScroll className="px-5 pt-3">
            <table className="w-full min-w-[620px] border-separate border-spacing-0 text-[13px]">
              <thead>
                <tr>
                  <th className={thCls}>User</th>
                  <th className={thCls}>Role</th>
                  <th className={thCls}>Last login</th>
                  <th className={thCls}>Status</th>
                </tr>
              </thead>
              <tbody>
                {(users.data?.items ?? []).map((u) => {
                  const self = u.id === me.user.id;
                  return (
                    <tr key={u.id} className={cn(!u.is_active && "opacity-55")}>
                      <td className={tdCls}>
                        <p className="text-fg">{u.full_name}{self && <span className="ml-1.5 text-xs text-fg-dim">(you)</span>}</p>
                        <p className="text-xs text-fg-dim">{u.email}</p>
                      </td>
                      <td className={tdCls}>
                        <select
                          aria-label={`Role for ${u.full_name}`}
                          value={u.role}
                          disabled={patch.pending}
                          onChange={(e) => patch.run(u.id, { role: e.target.value as Role })}
                          className={cn(selectCls, "h-8 w-36 text-[12.5px]")}
                        >
                          {ROLES.map((r) => (
                            <option key={r} value={r}>{humanize(r)}</option>
                          ))}
                        </select>
                      </td>
                      <td className={cn(tdCls, "text-fg-dim")}>{u.last_login_at ? fmtRelative(u.last_login_at) : "Never"}</td>
                      <td className={tdCls}>
                        <Btn size="xs" tone={u.is_active ? "ghost" : "default"} disabled={self || patch.pending} onClick={() => patch.run(u.id, { is_active: !u.is_active })}>
                          {u.is_active ? "Deactivate" : "Reactivate"}
                        </Btn>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </TableScroll>
          <InlineError error={patch.error} className="px-5 pb-4" />
        </>
      )}
    </Panel>
  );
}

function InvitesPanel() {
  const invites = useApi("invites", () => endpoints.invites());
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("broker");
  const [created, setCreated] = useState<InviteCreated | null>(null);
  const [copied, setCopied] = useState(false);
  const create = useMutation(endpoints.createInvite);
  const revoke = useMutation(endpoints.revokeInvite);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const res = await create.run({ email: email.trim(), role });
    if (res) {
      setCreated(res);
      setEmail("");
      invites.reload();
    }
  }

  const link = created
    ? /^https?:\/\//.test(created.invite_url)
      ? created.invite_url
      : typeof window !== "undefined"
        ? `${window.location.origin}${created.invite_url}`
        : created.invite_url
    : null;

  return (
    <Panel title="Invites" sub="No email is sent. Copy the link and share it yourself; it's shown once and expires in 7 days." className="lg:col-span-2">
      <form onSubmit={onSubmit} className="flex flex-col gap-3 sm:flex-row sm:items-end">
        <Field label="Email" htmlFor="inv-email" className="flex-1" error={fieldErrorOf(create.error, "email")}>
          <input id="inv-email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} className={inputCls} placeholder="colleague@brokerage.com" />
        </Field>
        <Field label="Role" htmlFor="inv-role" error={fieldErrorOf(create.error, "role")}>
          <select id="inv-role" value={role} onChange={(e) => setRole(e.target.value as Role)} className={cn(selectCls, "sm:w-40")}>
            {ROLES.map((r) => (
              <option key={r} value={r}>{humanize(r)}</option>
            ))}
          </select>
        </Field>
        <Btn type="submit" tone="primary" size="md" pending={create.pending}>
          <UserPlus className="h-4 w-4" aria-hidden="true" /> Create invite link
        </Btn>
      </form>
      <InlineError error={create.error} shownInline={["email", "role"]} className="mt-2" />

      {created && link && (
        <div role="status" className="mt-4 flex flex-col gap-2 rounded-xl border border-cyan/25 bg-cyan/[0.04] p-3 sm:flex-row sm:items-center">
          <div className="min-w-0 flex-1">
            <p className="text-xs text-fg-muted">
              Invite for {created.email} ({humanize(created.role)}) · expires {fmtDate(created.expires_at)}
            </p>
            <p className="mt-0.5 truncate font-mono text-[12px] text-ice">{link}</p>
          </div>
          <Btn
            onClick={async () => {
              try {
                await navigator.clipboard.writeText(link);
                setCopied(true);
              } catch {
                window.prompt("Copy the invite link", link);
              }
            }}
          >
            {copied ? <Check className="h-3.5 w-3.5 text-green" aria-hidden="true" /> : <Copy className="h-3.5 w-3.5" aria-hidden="true" />}
            {copied ? "Copied" : "Copy"}
          </Btn>
        </div>
      )}

      <div className="mt-5">
        {invites.loading ? (
          <LoadingBlock rows={2} />
        ) : invites.error && !invites.data ? (
          <ErrorState error={invites.error} onRetry={invites.reload} />
        ) : !invites.data?.items.length ? (
          <p className="text-sm text-fg-dim">No invites yet.</p>
        ) : (
          <ul className="divide-y divide-line rounded-xl border border-line">
            {invites.data.items.map((i) => (
              <li key={i.id} className="flex flex-wrap items-center gap-3 px-3 py-2.5 text-[13px]">
                <span className="min-w-0 flex-1 truncate text-fg">{i.email}</span>
                <Pill>{humanize(i.role)}</Pill>
                <Pill tone={i.state === "pending" ? "cyan" : i.state === "accepted" ? "green" : "neutral"}>{humanize(i.state)}</Pill>
                <span className="text-xs text-fg-dim">{i.state === "pending" ? `expires ${fmtDate(i.expires_at)}` : fmtDate(i.created_at)}</span>
                {i.state === "pending" && (
                  <Btn
                    size="xs"
                    tone="ghost"
                    aria-label={`Revoke invite for ${i.email}`}
                    onClick={async () => {
                      await revoke.run(i.id);
                      invites.reload();
                    }}
                  >
                    <X className="h-3.5 w-3.5" aria-hidden="true" /> Revoke
                  </Btn>
                )}
              </li>
            ))}
          </ul>
        )}
        <InlineError error={revoke.error} className="mt-2" />
      </div>
    </Panel>
  );
}
