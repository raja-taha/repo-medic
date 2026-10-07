import Link from "next/link";
import { listTasks } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";

export const dynamic = "force-dynamic";

export default async function TasksPage() {
  let tasks = [];
  let error: string | null = null;
  try {
    tasks = await listTasks();
  } catch (err) {
    error = err instanceof Error ? err.message : "Failed to load tasks";
  }

  return (
    <main className="section">
      <h2>Review queue</h2>
      <p className="lede">Every repair lands here with diff, evidence, and a PR draft.</p>
      {error ? (
        <div className="panel error">{error}</div>
      ) : (
        <div className="task-list">
          {tasks.length === 0 ? (
            <div className="panel meta">No tasks yet. Start a repair from the home page.</div>
          ) : (
            tasks.map((task) => (
              <Link key={task.id} href={`/tasks/${task.id}`} className="task-row">
                <div>
                  <h3>{task.issue_title || `${task.github_owner}/${task.github_repo}#${task.issue_number}`}</h3>
                  <div className="meta">
                    {task.github_owner}/{task.github_repo}#{task.issue_number} · {task.language} ·{" "}
                    {new Date(task.created_at).toLocaleString()}
                  </div>
                </div>
                <StatusBadge status={task.status} />
              </Link>
            ))
          )}
        </div>
      )}
    </main>
  );
}