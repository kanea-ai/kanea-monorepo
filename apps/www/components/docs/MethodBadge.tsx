type Method = 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE';

interface MethodBadgeProps {
  method: Method;
}

const palette: Record<Method, string> = {
  GET: 'bg-emerald-100 text-emerald-800',
  POST: 'bg-indigo-100 text-indigo-800',
  PATCH: 'bg-amber-100 text-amber-800',
  PUT: 'bg-amber-100 text-amber-800',
  DELETE: 'bg-rose-100 text-rose-800',
};

export function MethodBadge({ method }: MethodBadgeProps) {
  return (
    <span
      data-method={method}
      className={`inline-flex items-center rounded-md px-2 py-0.5 font-mono text-xs font-semibold ${palette[method]}`}
    >
      {method}
    </span>
  );
}
