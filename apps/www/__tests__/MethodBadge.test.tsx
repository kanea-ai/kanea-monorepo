import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

import { MethodBadge } from '../components/docs/MethodBadge';

describe('MethodBadge', () => {
  it.each([
    ['GET', 'emerald'],
    ['POST', 'indigo'],
    ['PATCH', 'amber'],
    ['PUT', 'amber'],
    ['DELETE', 'rose'],
  ] as const)('renders %s with the %s palette', (method, palette) => {
    render(<MethodBadge method={method} />);
    const el = screen.getByText(method);
    expect(el).toHaveAttribute('data-method', method);
    expect(el.className).toMatch(new RegExp(`bg-${palette}-100`));
    expect(el.className).toMatch(new RegExp(`text-${palette}-800`));
  });
});
