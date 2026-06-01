// The docs sidebar's source of truth. Each NavSection becomes a sidebar
// group; each NavItem becomes a link with active-route highlighting.
// Adding a page = one line under the appropriate section.

export interface NavItem {
  title: string;
  href: string;
}

export interface NavSection {
  title: string;
  items: NavItem[];
}

export const docsNav: NavSection[] = [
  {
    title: 'The platform',
    items: [
      { title: 'Overview', href: '/docs/overview' },
      { title: 'Concepts', href: '/docs/concepts' },
      { title: 'Features', href: '/docs/features' },
    ],
  },
  {
    title: 'Integration',
    items: [
      { title: 'Getting started', href: '/docs/getting-started' },
      { title: 'Agent quickstart', href: '/docs/agents/quickstart' },
      { title: 'API-key lifecycle', href: '/docs/agents/api-keys' },
    ],
  },
  {
    title: 'API reference',
    items: [
      { title: 'Overview', href: '/docs/api' },
      { title: 'Authentication', href: '/docs/api/auth' },
      { title: 'Current user (/me)', href: '/docs/api/me' },
      { title: 'Tasks', href: '/docs/api/tasks' },
      { title: 'Workspaces', href: '/docs/api/workspaces' },
      { title: 'Members', href: '/docs/api/members' },
      { title: 'Departments', href: '/docs/api/departments' },
      { title: 'Teams', href: '/docs/api/teams' },
      { title: 'Projects', href: '/docs/api/projects' },
      { title: 'Agents', href: '/docs/api/agents' },
      { title: 'Blocks', href: '/docs/api/blocks' },
      { title: 'Cross-team requests', href: '/docs/api/requests' },
      { title: 'Audit', href: '/docs/api/audit' },
    ],
  },
  {
    title: 'Reference',
    items: [{ title: 'Limits', href: '/docs/limits' }],
  },
];
