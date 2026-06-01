import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

import { Callout } from '../components/docs/Callout';

describe('Callout', () => {
  it('renders the title and body content', () => {
    render(
      <Callout variant="info" title="Heads up">
        <p>Body text</p>
      </Callout>,
    );
    expect(screen.getByText('Heads up')).toBeInTheDocument();
    expect(screen.getByText('Body text')).toBeInTheDocument();
  });

  it('defaults to the info variant when none is given', () => {
    render(<Callout>Default body</Callout>);
    expect(screen.getByRole('note')).toHaveAttribute('data-variant', 'info');
  });

  it('stamps the data-variant attribute for each variant', () => {
    const { rerender } = render(<Callout variant="warning">x</Callout>);
    expect(screen.getByRole('note')).toHaveAttribute('data-variant', 'warning');

    rerender(<Callout variant="note">x</Callout>);
    expect(screen.getByRole('note')).toHaveAttribute('data-variant', 'note');

    rerender(<Callout variant="info">x</Callout>);
    expect(screen.getByRole('note')).toHaveAttribute('data-variant', 'info');
  });

  it('omits the title block when no title is provided', () => {
    render(<Callout variant="info">Only body</Callout>);
    expect(screen.getByText('Only body')).toBeInTheDocument();
    expect(screen.queryByText('Heads up')).toBeNull();
  });
});
