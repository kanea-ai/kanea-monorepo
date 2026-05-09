'use client';

import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useState, type FormEvent } from 'react';

import { TaskRelationsPanel } from '../../../components/TaskRelationsPanel';
import { ApiError, type Task, type TaskComment } from '../../../lib/api';
import {
  usePostComment,
  useProjects,
  useSetTaskBlocked,
  useTask,
  useTaskComments,
  useTeams,
  useUpdateTaskLinks,
  useUpdateTaskStatus,
} from '../../../lib/queries';

// Detail page for one task. Shows the public_id, status, blocked banner
// (with a toggle), description, assignee, and a chronological comment
// thread. The comment form posts as the JWT holder — humans + agents
// alike, since both are members of the workspace.

export default function TaskDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;

  const { data: task, isLoading, isError, error } = useTask(id);

  if (isLoading) {
    return <p className="p-6 text-sm text-slate-500">Loading task…</p>;
  }
  if (isError) {
    return (
      <p className="p-6 text-sm text-red-600">Failed to load task: {(error as Error).message}</p>
    );
  }
  if (!task) return null;

  return (
    <div className="space-y-6 p-4 sm:p-6">
      <header>
        <Link href="/board" className="text-xs text-slate-500 hover:text-slate-700">
          ← Board
        </Link>
        <p className="mt-1 font-mono text-[11px] font-medium uppercase tracking-wide text-slate-400">
          {task.public_id}
        </p>
        <h1 className="text-xl font-semibold text-slate-900">{task.title}</h1>
        <p className="text-xs text-slate-500">
          Created {new Date(task.created_at).toLocaleString()} · Updated{' '}
          {new Date(task.updated_at).toLocaleString()}
        </p>
      </header>

      {task.is_blocked ? <BlockedBanner task={task} /> : null}

      <div className="grid gap-4 lg:grid-cols-[1fr_280px]">
        <div className="space-y-6">
          <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
            <header className="border-b border-slate-100 px-4 py-3">
              <h2 className="text-sm font-semibold text-slate-900">Description</h2>
            </header>
            <div className="px-4 py-4">
              {task.description ? (
                <p className="whitespace-pre-wrap text-sm text-slate-800">{task.description}</p>
              ) : (
                <p className="text-sm italic text-slate-400">No description provided.</p>
              )}
            </div>
          </section>

          <TaskRelationsPanel taskId={id} />

          <CommentThread taskId={id} />
        </div>

        <SidePanel task={task} />
      </div>
    </div>
  );
}

function BlockedBanner({ task }: { task: Task }) {
  const setBlocked = useSetTaskBlocked(task.id);
  return (
    <div className="rounded-lg border border-red-300 bg-red-50 p-3 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-2">
          <span
            className="mt-1 inline-block h-2 w-2 shrink-0 animate-pulse rounded-full bg-red-500"
            aria-hidden
          />
          <div className="min-w-0">
            <p className="text-sm font-semibold text-red-900">Blocked</p>
            <p className="mt-0.5 whitespace-pre-wrap break-words text-sm text-red-800">
              {task.blocked_reason || 'No reason provided.'}
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={() => setBlocked.mutate({ is_blocked: false })}
          disabled={setBlocked.isPending}
          className="shrink-0 rounded-md border border-red-300 bg-white px-3 py-1.5 text-xs font-medium text-red-700 hover:bg-red-100 disabled:opacity-60"
        >
          {setBlocked.isPending ? 'Unblocking…' : 'Unblock'}
        </button>
      </div>
    </div>
  );
}

function SidePanel({ task }: { task: Task }) {
  const updateStatus = useUpdateTaskStatus();
  const setBlocked = useSetTaskBlocked(task.id);
  const updateLinks = useUpdateTaskLinks(task.id);
  const { data: projects } = useProjects();
  const { data: teams } = useTeams();
  const [reason, setReason] = useState('');
  const [openBlock, setOpenBlock] = useState(false);

  const onChangeStatus = (e: React.ChangeEvent<HTMLSelectElement>) => {
    updateStatus.mutate({ id: task.id, payload: { status: e.target.value as Task['status'] } });
  };

  const onChangeProject = (e: React.ChangeEvent<HTMLSelectElement>) => {
    // Empty string = "no project" → send explicit null so the link
    // gets cleared (omitting the field would leave it untouched).
    const v = e.target.value;
    updateLinks.mutate({ project_id: v === '' ? null : v });
  };

  const onChangeTeam = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const v = e.target.value;
    updateLinks.mutate({ team_id: v === '' ? null : v });
  };

  const onBlock = async (e: FormEvent) => {
    e.preventDefault();
    await setBlocked.mutateAsync({ is_blocked: true, reason: reason.trim() || null });
    setReason('');
    setOpenBlock(false);
  };

  return (
    <aside className="space-y-4">
      <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
        <header className="border-b border-slate-100 px-4 py-3">
          <h2 className="text-sm font-semibold text-slate-900">Properties</h2>
        </header>
        <dl className="divide-y divide-slate-100 text-xs">
          <Row label="Status">
            <select
              value={task.status}
              onChange={onChangeStatus}
              disabled={updateStatus.isPending}
              className="rounded border border-slate-300 px-2 py-1 text-xs"
            >
              {(['PENDING', 'IN_PROGRESS', 'DONE', 'CANCELLED'] as const).map((s) => (
                <option key={s} value={s}>
                  {s.replace('_', ' ')}
                </option>
              ))}
            </select>
          </Row>
          <Row label="Priority">
            <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-slate-700">
              P{task.priority}
            </span>
          </Row>
          <Row label="Blocked">
            <span
              className={`rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide ${
                task.is_blocked ? 'bg-red-100 text-red-800' : 'bg-slate-100 text-slate-600'
              }`}
            >
              {task.is_blocked ? 'Yes' : 'No'}
            </span>
          </Row>
          <Row label="Assignee">
            <span className="font-mono text-[11px] text-slate-500">
              {task.assignee_id ? `${task.assignee_id.slice(0, 8)}…` : 'Unassigned'}
            </span>
          </Row>
          <Row label="Project">
            <select
              value={task.project_id ?? ''}
              onChange={onChangeProject}
              disabled={updateLinks.isPending}
              className="rounded border border-slate-300 px-2 py-1 text-xs"
            >
              <option value="">Backlog</option>
              {(projects ?? []).map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </Row>
          <Row label="Team">
            <select
              value={task.team_id ?? ''}
              onChange={onChangeTeam}
              disabled={updateLinks.isPending}
              className="rounded border border-slate-300 px-2 py-1 text-xs"
            >
              <option value="">No team</option>
              {(teams ?? []).map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
          </Row>
          {task.due_at ? (
            <Row label="Due">
              <span className="text-slate-700">{new Date(task.due_at).toLocaleString()}</span>
            </Row>
          ) : null}
        </dl>
      </section>

      {!task.is_blocked ? (
        <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
          <header className="border-b border-slate-100 px-4 py-3">
            <h2 className="text-sm font-semibold text-slate-900">Block this task</h2>
          </header>
          <div className="px-4 py-3">
            {openBlock ? (
              <form onSubmit={onBlock} className="space-y-2">
                <textarea
                  rows={3}
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder="Why is it blocked?"
                  className="w-full rounded-md border border-slate-300 px-3 py-2 text-xs"
                />
                <div className="flex justify-end gap-2">
                  <button
                    type="button"
                    onClick={() => setOpenBlock(false)}
                    className="rounded-md border border-slate-200 px-3 py-1 text-xs text-slate-700 hover:bg-slate-50"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={setBlocked.isPending}
                    className="rounded-md bg-red-600 px-3 py-1 text-xs font-medium text-white hover:bg-red-700 disabled:opacity-60"
                  >
                    Mark blocked
                  </button>
                </div>
              </form>
            ) : (
              <button
                type="button"
                onClick={() => setOpenBlock(true)}
                className="w-full rounded-md border border-red-200 bg-white px-3 py-1.5 text-xs font-medium text-red-700 hover:bg-red-50"
              >
                Mark blocked…
              </button>
            )}
          </div>
        </section>
      ) : null}
    </aside>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 px-4 py-2">
      <dt className="text-[11px] font-medium uppercase tracking-wide text-slate-500">{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

function CommentThread({ taskId }: { taskId: string }) {
  const { data: comments, isLoading, isError, error } = useTaskComments(taskId);
  const post = usePostComment(taskId);
  const [body, setBody] = useState('');
  const [postError, setPostError] = useState<string | null>(null);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (body.trim() === '') return;
    setPostError(null);
    try {
      await post.mutateAsync({ body: body.trim() });
      setBody('');
    } catch (err) {
      setPostError(err instanceof ApiError ? err.detail : 'Failed to post');
    }
  };

  return (
    <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
      <header className="border-b border-slate-100 px-4 py-3">
        <h2 className="text-sm font-semibold text-slate-900">Comments</h2>
        <p className="mt-0.5 text-xs text-slate-500">
          Anyone in the workspace — humans and agents — can post here.
        </p>
      </header>

      <div className="space-y-3 px-4 py-3">
        {isLoading ? (
          <p className="text-sm text-slate-500">Loading comments…</p>
        ) : isError ? (
          <p className="text-sm text-red-600">
            Failed to load comments: {(error as Error).message}
          </p>
        ) : !comments || comments.length === 0 ? (
          <p className="text-sm italic text-slate-400">No comments yet.</p>
        ) : (
          <ul className="space-y-3">
            {comments.map((c) => (
              <CommentRow key={c.id} comment={c} />
            ))}
          </ul>
        )}
      </div>

      <form onSubmit={onSubmit} className="space-y-2 border-t border-slate-100 px-4 py-3">
        <textarea
          rows={3}
          value={body}
          onChange={(e) => setBody(e.target.value)}
          placeholder="Add a comment…"
          className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
        />
        {postError ? (
          <p role="alert" className="text-xs text-red-600">
            {postError}
          </p>
        ) : null}
        <div className="flex justify-end">
          <button
            type="submit"
            disabled={post.isPending || body.trim() === ''}
            className="rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white shadow-sm hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {post.isPending ? 'Posting…' : 'Post comment'}
          </button>
        </div>
      </form>
    </section>
  );
}

function CommentRow({ comment }: { comment: TaskComment }) {
  return (
    <li className="rounded-md border border-slate-100 bg-slate-50 p-3">
      <div className="flex items-baseline justify-between gap-2">
        <p className="text-xs font-semibold text-slate-700">
          {comment.author_name ?? <span className="italic text-slate-500">deleted member</span>}
        </p>
        <p className="text-[10px] text-slate-400">
          {new Date(comment.created_at).toLocaleString()}
        </p>
      </div>
      <p className="mt-1 whitespace-pre-wrap break-words text-sm text-slate-800">{comment.body}</p>
    </li>
  );
}
