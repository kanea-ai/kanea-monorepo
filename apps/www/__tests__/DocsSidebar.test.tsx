import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

import { DocsSidebar } from '../components/docs/DocsSidebar';
import type { NavSection } from '../lib/docs/nav';

const mockPathname = vi.fn<[], string>();

vi.mock('next/navigation', () => ({
  usePathname: () => mockPathname(),
}));

const SECTIONS: NavSection[] = [
  {
    title: 'Introduction',
    items: [
      { title: 'Overview', href: '/docs' },
      { title: 'Concepts', href: '/docs/concepts' },
    ],
  },
];

describe('DocsSidebar', () => {
  it('renders every nav item under its section heading', () => {
    mockPathname.mockReturnValue('/docs');
    render(<DocsSidebar sections={SECTIONS} />);

    expect(screen.getByText('Introduction')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Overview' })).toHaveAttribute('href', '/docs');
    expect(screen.getByRole('link', { name: 'Concepts' })).toHaveAttribute(
      'href',
      '/docs/concepts',
    );
  });

  it('marks the current route as the active page', () => {
    mockPathname.mockReturnValue('/docs/concepts');
    render(<DocsSidebar sections={SECTIONS} />);

    const active = screen.getByRole('link', { name: 'Concepts' });
    expect(active).toHaveAttribute('aria-current', 'page');

    const inactive = screen.getByRole('link', { name: 'Overview' });
    expect(inactive).not.toHaveAttribute('aria-current');
  });

  it('applies the active style class to the current route only', () => {
    mockPathname.mockReturnValue('/docs');
    render(<DocsSidebar sections={SECTIONS} />);

    expect(screen.getByRole('link', { name: 'Overview' }).className).toMatch(/text-indigo-700/);
    expect(screen.getByRole('link', { name: 'Concepts' }).className).not.toMatch(/text-indigo-700/);
  });
});
