import { redirect } from 'next/navigation';

// Phase 5 batch 2 follow-up: the standalone agents list is gone. The
// unified /directory replaces it. /agents/[id] (the agent detail page
// with stats + key rotation) stays as-is — links from the directory
// row still land there.
export default function AgentsRedirect(): never {
  redirect('/directory');
}
