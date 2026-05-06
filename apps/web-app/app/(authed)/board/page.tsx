import { ExceptionQueue } from '../../components/ExceptionQueue';
import { KanbanBoard } from '../../components/KanbanBoard';

export default function BoardPage() {
  return (
    <div className="flex h-[calc(100vh-3.25rem)] flex-col lg:h-screen lg:flex-row">
      <section className="flex min-h-0 min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-slate-200 bg-white px-4 py-3 sm:px-6">
          <div>
            <h1 className="text-lg font-semibold text-slate-900">Board</h1>
            <p className="text-xs text-slate-500">
              Drag cards across columns to update status. Blocked tasks live in the Exception Queue.
            </p>
          </div>
        </header>
        <div className="min-h-0 flex-1 overflow-auto">
          <KanbanBoard />
        </div>
      </section>
      <ExceptionQueue />
    </div>
  );
}
