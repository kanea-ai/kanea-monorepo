import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

import { EntityDetailPanel } from '../app/components/EntityDetailPanel';
import type { AdminMemberStats, AdminUserDetail, AdminWorkspaceUserRow } from '../app/lib/api';

// ---------- shared fixtures ----------

const HUMAN_USER: AdminUserDetail = {
  id: 'user-1',
  email: 'alice@acme.io',
  full_name: 'Alice Example',
  is_superadmin: false,
  is_banned: false,
  sessions_invalidated_at: null,
  created_at: '2026-01-15T09:30:00Z',
  memberships: [
    {
      workspace_id: 'ws-1',
      workspace_name: 'Acme',
      workspace_slug: 'acme',
      member_id: 'm-1',
      role: 'WORKSPACE_OWNER',
      is_suspended: false,
    },
  ],
};

const MULTI_WS_USER: AdminUserDetail = {
  ...HUMAN_USER,
  id: 'user-multi',
  memberships: [
    ...HUMAN_USER.memberships,
    {
      workspace_id: 'ws-2',
      workspace_name: 'Bravo',
      workspace_slug: 'bravo',
      member_id: 'm-2',
      role: 'WORKSPACE_USER',
      is_suspended: false,
    },
  ],
};

const SUPERADMIN_USER: AdminUserDetail = {
  ...HUMAN_USER,
  id: 'user-su',
  email: 'root@kanea.ai',
  full_name: 'Root',
  is_superadmin: true,
  memberships: [],
};

const HUMAN_MEMBER: AdminWorkspaceUserRow = {
  member_id: 'm-1',
  user_id: 'user-1',
  email: 'alice@acme.io',
  full_name: 'Alice Example',
  type: 'HUMAN',
  role: 'WORKSPACE_USER',
  is_suspended: false,
  team_id: null,
  team_name: null,
  team_role: null,
  team_department_id: null,
  team_department_name: null,
  headed_department_id: null,
  headed_department_name: null,
};

const AGENT_MEMBER: AdminWorkspaceUserRow = {
  member_id: 'm-agent-1',
  user_id: null,
  email: null,
  full_name: 'Aria (Agent)',
  type: 'AGENT',
  role: 'WORKSPACE_USER',
  is_suspended: false,
  team_id: 't-1',
  team_name: 'Backend',
  team_role: 'MEMBER',
  team_department_id: null,
  team_department_name: null,
  headed_department_id: null,
  headed_department_name: null,
};

// ---------- mocks ----------
// Stubbing the query hooks keeps the test surface focused on the
// component. The real network layer is exercised by the API tests.

const banMutate = vi.fn();
const resetMutate = vi.fn();
const patchMemberMutate = vi.fn();

vi.mock('../app/lib/queries', () => ({
  useAdminUser: vi.fn(),
  useWorkspaceMember: vi.fn(),
  useWorkspaceUsers: vi.fn(),
  useMemberStats: vi.fn(),
  useSetUserBanned: () => ({ mutateAsync: banMutate, isPending: false }),
  useForcePasswordReset: () => ({ mutateAsync: resetMutate, isPending: false }),
  usePatchWorkspaceMember: () => ({ mutateAsync: patchMemberMutate, isPending: false }),
}));

import {
  useAdminUser,
  useMemberStats,
  useWorkspaceMember,
  useWorkspaceUsers,
} from '../app/lib/queries';

function withClient(children: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

function stubUser(user: AdminUserDetail | undefined) {
  (useAdminUser as any).mockReturnValue({
    data: user,
    isLoading: false,
    isError: false,
  });
}

function stubMember(member: AdminWorkspaceUserRow | undefined) {
  (useWorkspaceMember as any).mockReturnValue({
    data: member,
    isLoading: false,
    isError: false,
  });
}

function stubMembersList(items: AdminWorkspaceUserRow[]) {
  (useWorkspaceUsers as any).mockReturnValue({
    data: { items, total: items.length },
    isLoading: false,
  });
}

function stubStats(stats: AdminMemberStats | undefined) {
  (useMemberStats as any).mockReturnValue({ data: stats, isLoading: stats == null });
}

beforeEach(() => {
  banMutate.mockReset();
  resetMutate.mockReset();
  patchMemberMutate.mockReset();
  stubUser(undefined);
  stubMember(undefined);
  stubMembersList([]);
  stubStats(undefined);
});

// ---------- user entry — global identity + auto-picked workspace ----------

describe('EntityDetailPanel — user entry mode', () => {
  it('renders identity, memberships, and the auto-picked workspace section', () => {
    stubUser(HUMAN_USER);
    stubMember(HUMAN_MEMBER);
    render(
      withClient(
        <EntityDetailPanel entry={{ kind: 'user', userId: 'user-1' }} onClose={() => {}} />,
      ),
    );
    expect(screen.getByRole('heading', { name: 'Alice Example' })).toBeInTheDocument();
    expect(screen.getByText('Acme')).toBeInTheDocument();
    // Single workspace auto-picks; the workspace-scoped Edit button
    // becomes available without showing a picker.
    expect(screen.queryByLabelText(/active workspace/i)).toBeNull();
    expect(screen.getByRole('button', { name: /^edit$/i })).toBeInTheDocument();
  });

  it('shows a workspace picker for multi-workspace humans', async () => {
    const user = userEvent.setup();
    stubUser(MULTI_WS_USER);
    stubMember(HUMAN_MEMBER);
    render(
      withClient(
        <EntityDetailPanel entry={{ kind: 'user', userId: 'user-multi' }} onClose={() => {}} />,
      ),
    );
    const picker = screen.getByLabelText(/active workspace/i) as HTMLSelectElement;
    expect(picker).toBeInTheDocument();
    expect(within(picker).getByRole('option', { name: /acme/i })).toBeInTheDocument();
    expect(within(picker).getByRole('option', { name: /bravo/i })).toBeInTheDocument();
    await user.selectOptions(picker, 'ws-2');
    // After switching, the panel re-resolves the workspace-scoped queries.
    // (The fetch hooks are stubbed so we just assert the picker reflects the choice.)
    expect(picker.value).toBe('ws-2');
  });

  it('ban flow requires typing the email before confirm', async () => {
    const user = userEvent.setup();
    stubUser(HUMAN_USER);
    stubMember(HUMAN_MEMBER);
    render(
      withClient(
        <EntityDetailPanel entry={{ kind: 'user', userId: 'user-1' }} onClose={() => {}} />,
      ),
    );
    await user.click(screen.getByRole('button', { name: /ban user/i }));
    const confirmBtn = screen.getAllByRole('button', { name: /ban user/i }).at(-1)!;
    expect(confirmBtn).toBeDisabled();
    const input = screen.getByRole('textbox');
    await user.type(input, HUMAN_USER.email);
    expect(confirmBtn).toBeEnabled();
    await user.click(confirmBtn);
    expect(banMutate).toHaveBeenCalledWith({
      userId: HUMAN_USER.id,
      payload: { is_banned: true },
    });
  });

  it('superadmin shows the cannot-ban-via-UI message and no Ban button', () => {
    stubUser(SUPERADMIN_USER);
    render(
      withClient(
        <EntityDetailPanel entry={{ kind: 'user', userId: 'user-su' }} onClose={() => {}} />,
      ),
    );
    expect(screen.getByText(/superadmins cannot be banned/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /ban user/i })).toBeNull();
  });

  it('force password reset shows the simulated email preview on success', async () => {
    const user = userEvent.setup();
    stubUser(HUMAN_USER);
    stubMember(HUMAN_MEMBER);
    resetMutate.mockResolvedValueOnce({
      user_id: HUMAN_USER.id,
      sessions_invalidated_at: '2026-05-31T12:00:00Z',
      simulated_email: 'TO: alice@acme.io\nSubject: Reset',
    });
    render(
      withClient(
        <EntityDetailPanel entry={{ kind: 'user', userId: 'user-1' }} onClose={() => {}} />,
      ),
    );
    await user.click(screen.getByRole('button', { name: /force reset/i }));
    expect(await screen.findByText(/simulated recovery email/i)).toBeInTheDocument();
    expect(screen.getByText(/TO: alice@acme.io/)).toBeInTheDocument();
  });
});

// ---------- workspace-member entry — same panel from the workspaces drill-down ----------

describe('EntityDetailPanel — workspace-member entry mode', () => {
  it('renders the same superset (global + workspace) for a HUMAN', () => {
    stubMember(HUMAN_MEMBER);
    stubUser(HUMAN_USER);
    render(
      withClient(
        <EntityDetailPanel
          entry={{ kind: 'workspace-member', workspaceId: 'ws-1', memberId: 'm-1' }}
          onClose={() => {}}
        />,
      ),
    );
    // Workspace-scoped sections.
    expect(screen.getByRole('button', { name: /^edit$/i })).toBeInTheDocument();
    // Global sections fetched via member.user_id.
    expect(screen.getByRole('button', { name: /ban user/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /force reset/i })).toBeInTheDocument();
  });

  it('hides the human-only sections for an AGENT', () => {
    stubMember(AGENT_MEMBER);
    render(
      withClient(
        <EntityDetailPanel
          entry={{ kind: 'workspace-member', workspaceId: 'ws-1', memberId: 'm-agent-1' }}
          onClose={() => {}}
        />,
      ),
    );
    expect(screen.getByText('AGENT')).toBeInTheDocument();
    // No global ban / reset / memberships for agents.
    expect(screen.queryByRole('button', { name: /ban user/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /force reset/i })).toBeNull();
    expect(screen.queryByText(/workspaces/i)).toBeNull();
  });

  it('is read-only by default; Edit reveals the hierarchy editor', async () => {
    const user = userEvent.setup();
    stubMember(HUMAN_MEMBER);
    render(
      withClient(
        <EntityDetailPanel
          entry={{ kind: 'workspace-member', workspaceId: 'ws-1', memberId: 'm-1' }}
          onClose={() => {}}
        />,
      ),
    );
    expect(screen.queryByRole('button', { name: /team member/i })).toBeNull();
    await user.click(screen.getByRole('button', { name: /^edit$/i }));
    expect(screen.getByRole('button', { name: /team member/i })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /^cancel$/i }));
    expect(screen.queryByRole('button', { name: /team member/i })).toBeNull();
  });

  it('rbac.canEdit=false disables Edit and surfaces the tooltip', () => {
    stubMember(HUMAN_MEMBER);
    render(
      withClient(
        <EntityDetailPanel
          entry={{ kind: 'workspace-member', workspaceId: 'ws-1', memberId: 'm-1' }}
          rbac={{ canEdit: false, disabledReason: 'Ask the WORKSPACE_OWNER.' }}
          onClose={() => {}}
        />,
      ),
    );
    const editBtn = screen.getByRole('button', { name: /^edit$/i });
    expect(editBtn).toBeDisabled();
    expect(editBtn).toHaveAttribute('title', 'Ask the WORKSPACE_OWNER.');
  });

  it('save on an agent uses the member-id-keyed PATCH', async () => {
    const user = userEvent.setup();
    stubMember(AGENT_MEMBER);
    render(
      withClient(
        <EntityDetailPanel
          entry={{ kind: 'workspace-member', workspaceId: 'ws-1', memberId: 'm-agent-1' }}
          onClose={() => {}}
        />,
      ),
    );
    await user.click(screen.getByRole('button', { name: /^edit$/i }));
    await user.click(screen.getByRole('button', { name: /unassigned/i }));
    await user.click(screen.getByRole('button', { name: /^save$/i }));
    expect(patchMemberMutate).toHaveBeenCalledTimes(1);
    expect(patchMemberMutate).toHaveBeenCalledWith({
      memberId: AGENT_MEMBER.member_id,
      payload: expect.objectContaining({
        team_id: null,
        team_role: null,
        department_id: null,
      }),
    });
  });

  it('Edit exposes workspace_role + priority editors; save forwards them', async () => {
    const user = userEvent.setup();
    stubMember(HUMAN_MEMBER);
    render(
      withClient(
        <EntityDetailPanel
          entry={{ kind: 'workspace-member', workspaceId: 'ws-1', memberId: 'm-1' }}
          onClose={() => {}}
        />,
      ),
    );
    await user.click(screen.getByRole('button', { name: /^edit$/i }));
    await user.selectOptions(screen.getByLabelText(/workspace role/i), 'WORKSPACE_ADMIN');
    const prio = screen.getByLabelText(/^priority$/i);
    await user.clear(prio);
    await user.type(prio, '7');
    await user.click(screen.getByRole('button', { name: /^save$/i }));
    const call = patchMemberMutate.mock.calls[0][0];
    expect(call.payload.workspace_role).toBe('WORKSPACE_ADMIN');
    expect(call.payload.priority).toBe(7);
  });

  it('renders team + department selects when the workspace listing provides options', async () => {
    const user = userEvent.setup();
    stubMember(HUMAN_MEMBER);
    stubMembersList([
      {
        ...HUMAN_MEMBER,
        member_id: 'm-x',
        team_id: 't-1',
        team_name: 'Backend',
        team_department_id: 'd-1',
        team_department_name: 'Engineering',
      },
    ]);
    render(
      withClient(
        <EntityDetailPanel
          entry={{ kind: 'workspace-member', workspaceId: 'ws-1', memberId: 'm-1' }}
          onClose={() => {}}
        />,
      ),
    );
    await user.click(screen.getByRole('button', { name: /^edit$/i }));
    await user.click(screen.getByRole('button', { name: /team member/i }));
    const teamSelect = screen.getByLabelText(/^team$/i) as HTMLSelectElement;
    expect(teamSelect.tagName).toBe('SELECT');
    expect(within(teamSelect).getByRole('option', { name: 'Backend' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /department head/i }));
    const deptSelect = screen.getByLabelText(/department to head/i) as HTMLSelectElement;
    expect(deptSelect.tagName).toBe('SELECT');
    expect(within(deptSelect).getByRole('option', { name: 'Engineering' })).toBeInTheDocument();
  });

  it('warns + gates Save when promoting onto a team that already has a MANAGER', async () => {
    const user = userEvent.setup();
    const sittingManager: AdminWorkspaceUserRow = {
      ...HUMAN_MEMBER,
      member_id: 'm-other',
      full_name: 'Carol the Manager',
      team_id: 't-1',
      team_name: 'Backend',
      team_role: 'MANAGER',
    };
    stubMember(HUMAN_MEMBER);
    stubMembersList([sittingManager, HUMAN_MEMBER]);
    render(
      withClient(
        <EntityDetailPanel
          entry={{ kind: 'workspace-member', workspaceId: 'ws-1', memberId: 'm-1' }}
          onClose={() => {}}
        />,
      ),
    );
    await user.click(screen.getByRole('button', { name: /^edit$/i }));
    await user.click(screen.getByRole('button', { name: /team member/i }));
    await user.selectOptions(screen.getByLabelText(/^team$/i), 't-1');
    await user.selectOptions(screen.getByLabelText(/^team role$/i), 'MANAGER');
    expect(screen.getByText(/Carol the Manager/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /^save$/i }));
    expect(patchMemberMutate).not.toHaveBeenCalled();
    await user.click(screen.getByRole('checkbox', { name: /replace the current/i }));
    await user.click(screen.getByRole('button', { name: /^save$/i }));
    expect(patchMemberMutate).toHaveBeenCalledTimes(1);
  });

  it('stats card renders when the stats endpoint returns data', () => {
    stubMember(AGENT_MEMBER);
    stubStats({
      assigned_count: 3,
      completed_count: 14,
      avg_resolution_seconds: 600,
      accuracy_percent: 4.5,
      last_activity_at: '2026-05-30T10:00:00Z',
      total_tokens_used: 1234,
    });
    render(
      withClient(
        <EntityDetailPanel
          entry={{ kind: 'workspace-member', workspaceId: 'ws-1', memberId: 'm-agent-1' }}
          onClose={() => {}}
        />,
      ),
    );
    expect(screen.getByText('Assigned')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getByText('14')).toBeInTheDocument();
    expect(screen.getByText('1,234')).toBeInTheDocument();
  });
});
