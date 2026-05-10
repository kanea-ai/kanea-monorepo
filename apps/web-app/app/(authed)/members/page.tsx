import { redirect } from 'next/navigation';

// Phase 5 batch 2: /members merged into /directory. Keep the route
// alive so old bookmarks land somewhere sensible.
export default function MembersRedirect(): never {
  redirect('/directory');
}
