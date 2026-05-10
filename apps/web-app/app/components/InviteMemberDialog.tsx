'use client';

// Phase 5 batch 2: invite flow lives on the unified directory now.
// Wraps the existing useCreateInvite mutation in our standard <Modal>
// shell. Keeps the same "Invite queued for email delivery" reveal
// from the Phase 2 cleanup — Gmail will plug in later.

import { useEffect, useState, type FormEvent } from 'react';

import { ApiError, type InviteCreateResponse } from '../lib/api';
import { useCreateInvite } from '../lib/queries';
import { Modal } from './Modal';

export function InviteMemberDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const create = useCreateInvite();
  const [email, setEmail] = useState('');
  const [role, setRole] = useState<'WORKSPACE_ADMIN' | 'WORKSPACE_MEMBER'>('WORKSPACE_MEMBER');
  const [error, setError] = useState<string | null>(null);
  const [reveal, setReveal] = useState<InviteCreateResponse | null>(null);

  useEffect(() => {
    if (open) {
      setEmail('');
      setRole('WORKSPACE_MEMBER');
      setError(null);
      setReveal(null);
    }
  }, [open]);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      const out = await create.mutateAsync({ email: email.trim(), role });
      setReveal(out);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to create invite');
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      pending={create.isPending}
      title="Invite a member"
      subtitle={
        reveal
          ? 'The invite has been queued. We’ll email it shortly.'
          : 'Send an invite link to a teammate. They’ll join as the chosen role.'
      }
      footer={
        reveal ? (
          <button
            type="button"
            onClick={onClose}
            className="rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white shadow-sm hover:bg-indigo-700"
          >
            Done
          </button>
        ) : (
          <>
            <button
              type="button"
              onClick={onClose}
              disabled={create.isPending}
              className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60"
            >
              Cancel
            </button>
            <button
              type="submit"
              form="invite-member-form"
              disabled={create.isPending || email.trim() === ''}
              className="rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white shadow-sm hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {create.isPending ? 'Sending…' : 'Send invite'}
            </button>
          </>
        )
      }
    >
      {reveal ? (
        <div className="rounded-md border border-emerald-200 bg-emerald-50/60 px-3 py-3 text-sm">
          <p className="font-medium text-emerald-900">Invite queued for {reveal.email}.</p>
          <p className="mt-1 text-xs text-emerald-800">
            Expires {new Date(reveal.expires_at).toLocaleString()}.
          </p>
        </div>
      ) : (
        <form id="invite-member-form" onSubmit={onSubmit} className="space-y-3">
          <div>
            <label
              htmlFor="invite_email"
              className="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-600"
            >
              Email
            </label>
            <input
              id="invite_email"
              type="email"
              required
              value={email}
              placeholder="bob@example.com"
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
          </div>
          <div>
            <label
              htmlFor="invite_role"
              className="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-600"
            >
              Role
            </label>
            <select
              id="invite_role"
              value={role}
              onChange={(e) => setRole(e.target.value as 'WORKSPACE_ADMIN' | 'WORKSPACE_MEMBER')}
              className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            >
              <option value="WORKSPACE_MEMBER">Member</option>
              <option value="WORKSPACE_ADMIN">Admin</option>
            </select>
          </div>
          {error ? (
            <p role="alert" className="text-sm text-red-600">
              {error}
            </p>
          ) : null}
        </form>
      )}
    </Modal>
  );
}
