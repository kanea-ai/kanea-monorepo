import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

import { TableOfContents, type Heading } from '../components/docs/TableOfContents';

describe('TableOfContents', () => {
  it('renders nothing when there are no headings', () => {
    const { container } = render(<TableOfContents headings={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders one link per supplied heading, pointing to the heading id', () => {
    const headings: Heading[] = [
      { id: 'overview', text: 'Overview', level: 2 },
      { id: 'auth', text: 'Authentication', level: 2 },
      { id: 'auth-keys', text: 'Keys', level: 3 },
    ];
    render(<TableOfContents headings={headings} />);

    expect(screen.getByRole('link', { name: 'Overview' })).toHaveAttribute('href', '#overview');
    expect(screen.getByRole('link', { name: 'Authentication' })).toHaveAttribute('href', '#auth');
    expect(screen.getByRole('link', { name: 'Keys' })).toHaveAttribute('href', '#auth-keys');
  });

  it('indents h3 entries one level deeper than h2 entries', () => {
    const headings: Heading[] = [
      { id: 'top', text: 'Top', level: 2 },
      { id: 'sub', text: 'Sub', level: 3 },
    ];
    render(<TableOfContents headings={headings} />);

    const topItem = screen.getByRole('link', { name: 'Top' }).parentElement;
    const subItem = screen.getByRole('link', { name: 'Sub' }).parentElement;
    expect(topItem?.className ?? '').not.toMatch(/ml-3/);
    expect(subItem?.className ?? '').toMatch(/ml-3/);
  });

  it('extracts h2 / h3 headings from the scope element when no list is supplied', () => {
    const root = document.createElement('div');
    root.id = 'doc-content';
    root.innerHTML = `
      <h2 id="alpha">Alpha</h2>
      <h3 id="alpha-detail">Alpha Detail</h3>
      <h2>No Id Skipped</h2>
      <h2 id="beta">Beta</h2>
    `;
    document.body.appendChild(root);

    render(<TableOfContents />);

    expect(screen.getByRole('link', { name: 'Alpha' })).toHaveAttribute('href', '#alpha');
    expect(screen.getByRole('link', { name: 'Alpha Detail' })).toHaveAttribute(
      'href',
      '#alpha-detail',
    );
    expect(screen.getByRole('link', { name: 'Beta' })).toHaveAttribute('href', '#beta');
    expect(screen.queryByRole('link', { name: 'No Id Skipped' })).toBeNull();

    document.body.removeChild(root);
  });
});
