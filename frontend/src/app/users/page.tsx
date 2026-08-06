"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Trash2, UserPlus } from "lucide-react";
import { useState } from "react";
import { api, Role, UserCreate } from "@/lib/api";
import { Shell } from "@/components/shell";
import { Empty, ErrorBox, Loading, PageHeader, Status } from "@/components/ui";

const ROLES: Role[] = ["agent", "engineer", "lead", "admin"];

export default function UsersPage() {
  const qc = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<UserCreate>({
    email: "",
    password: "",
    full_name: "",
    role: "agent",
  });

  const users = useQuery({ queryKey: ["users"], queryFn: api.users });

  const create = useMutation({
    mutationFn: (data: UserCreate) => api.createUser(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["users"] });
      setShowForm(false);
      setForm({ email: "", password: "", full_name: "", role: "agent" });
    },
  });

  const remove = useMutation({
    mutationFn: (id: string) => api.deleteUser(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["users"] }),
  });

  return (
    <Shell>
      <PageHeader
        title="Users"
        description="User accounts and roles. Managing users is Admin-only."
      >
        <button className="btn-ghost" onClick={() => setShowForm((v) => !v)}>
          <UserPlus className="h-3.5 w-3.5" aria-hidden /> Add user
        </button>
      </PageHeader>

      {showForm && (
        <form
          className="card mb-4 grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-[1fr_1fr_1fr_120px_auto]"
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate(form);
          }}
        >
          <input
            className="input"
            placeholder="Full name"
            value={form.full_name}
            onChange={(e) => setForm({ ...form, full_name: e.target.value })}
            required
          />
          <input
            className="input"
            type="email"
            placeholder="Email"
            value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
            required
          />
          <input
            className="input"
            type="password"
            placeholder="Password"
            value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
            required
          />
          <select
            className="input"
            value={form.role}
            onChange={(e) => setForm({ ...form, role: e.target.value as Role })}
          >
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
          <div className="flex items-center gap-2">
            <button className="btn" type="submit" disabled={create.isPending}>
              {create.isPending ? "Saving…" : "Create"}
            </button>
            <button
              type="button"
              className="btn-ghost"
              onClick={() => setShowForm(false)}
            >
              Cancel
            </button>
          </div>
          {create.error != null && (
            <div className="sm:col-span-2 lg:col-span-5">
              <ErrorBox error={create.error} />
            </div>
          )}
        </form>
      )}

      {users.isLoading && <Loading />}
      {users.error != null && <ErrorBox error={users.error} />}
      {users.data?.length === 0 && (
        <Empty
          title="No users"
          hint="Create the first account to get started."
        />
      )}

      {!!users.data?.length && (
        <div className="card divide-y divide-line">
          {users.data.map((u) => (
            <div key={u.id} className="flex items-center gap-3 p-3">
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm text-ink">{u.full_name}</p>
                <p className="mt-0.5 font-mono text-micro text-faint">
                  {u.email}
                </p>
              </div>
              <Status value={u.role} />
              <button
                onClick={() => {
                  if (
                    window.confirm(`Delete user ${u.full_name} (${u.email})?`)
                  )
                    remove.mutate(u.id);
                }}
                aria-label={`Delete ${u.full_name}`}
                className="btn-ghost text-muted hover:text-danger"
              >
                <Trash2 className="h-3.5 w-3.5" aria-hidden />
              </button>
            </div>
          ))}
        </div>
      )}
    </Shell>
  );
}
