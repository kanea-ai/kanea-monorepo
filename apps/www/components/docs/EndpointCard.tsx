import type { ReactNode } from 'react';
import { MethodBadge } from './MethodBadge';

interface EndpointCardProps {
  method: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE';
  path: string;
  // Plain-language audience label, e.g. "Signed in", "Workspace admin",
  // "Agent". Never an internal dependency name.
  auth: string;
  // One-line purpose.
  summary: string;
  // Optional request / response examples.
  children?: ReactNode;
}

export function EndpointCard({ method, path, auth, summary, children }: EndpointCardProps) {
  return (
    <div className="my-5 overflow-hidden rounded-md border border-slate-200 bg-white">
      <div className="flex flex-wrap items-center gap-3 border-b border-slate-200 bg-slate-50 px-4 py-3">
        <MethodBadge method={method} />
        <code className="font-mono text-sm text-slate-800">{path}</code>
        <span className="ml-auto text-xs font-medium text-slate-500">{auth}</span>
      </div>
      <div className="space-y-3 px-4 py-3 text-sm text-slate-700">
        <p className="m-0">{summary}</p>
        {children}
      </div>
    </div>
  );
}
