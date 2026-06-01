import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

import { EndpointCard } from '../components/docs/EndpointCard';

describe('EndpointCard', () => {
  it('renders method badge, path, audience label and summary', () => {
    render(
      <EndpointCard
        method="POST"
        path="/api/v1/agents/exchange"
        auth="Agent API key"
        summary="Exchange an agent API key for a short-lived JWT."
      />,
    );

    expect(screen.getByText('POST')).toHaveAttribute('data-method', 'POST');
    expect(screen.getByText('/api/v1/agents/exchange')).toBeInTheDocument();
    expect(screen.getByText('Agent API key')).toBeInTheDocument();
    expect(
      screen.getByText('Exchange an agent API key for a short-lived JWT.'),
    ).toBeInTheDocument();
  });

  it('renders children below the summary when provided', () => {
    render(
      <EndpointCard method="GET" path="/api/v1/me" auth="Signed in" summary="Current user.">
        <p>Example response body.</p>
      </EndpointCard>,
    );
    expect(screen.getByText('Example response body.')).toBeInTheDocument();
  });
});
