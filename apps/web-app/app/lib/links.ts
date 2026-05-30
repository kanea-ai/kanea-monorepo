// Centralised entity-link builders. Every clickable cross-entity
// reference in the app should route through one of these helpers so
// the URL shape stays consistent and a future move to dedicated
// detail routes (e.g. /directory/users/[id]) is a one-file diff.
//
// Today the user / team / department surfaces are deep-linked into
// existing list pages via query params:
//
//   - /directory?member=<id>   → opens MemberDetailDialog
//   - /teams?open=<id>         → opens TeamDetailDrawer
//   - /departments?open=<id>   → opens DepartmentDetailDrawer
//
// The link helpers are stable; if we later cut over to nested routes
// we only update them here.

/** Route to a user's detail surface. */
export function userHref(memberId: string): string {
  return `/directory?member=${encodeURIComponent(memberId)}`;
}

/** Route to a team's detail surface. */
export function teamHref(teamId: string): string {
  return `/teams?open=${encodeURIComponent(teamId)}`;
}

/** Route to a department's detail surface. */
export function departmentHref(departmentId: string): string {
  return `/departments?open=${encodeURIComponent(departmentId)}`;
}
