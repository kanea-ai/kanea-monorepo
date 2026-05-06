import { ExceptionQueue } from './components/ExceptionQueue';
import { KanbanBoard } from './components/KanbanBoard';

export default function Home() {
  return (
    <main className="flex h-screen w-full overflow-hidden">
      <div className="flex flex-1 flex-col overflow-hidden">
        <header className="flex items-center justify-between border-b border-slate-200 bg-white px-6 py-3">
          <h1 className="text-lg font-semibold text-slate-900">Kanea Board</h1>
        </header>
        <div className="flex-1 overflow-auto">
          <KanbanBoard />
        </div>
      </div>
      <ExceptionQueue />
    </main>
  );
}
