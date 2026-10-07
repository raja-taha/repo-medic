import Link from "next/link";
import { notFound } from "next/navigation";
import { ReviewActions } from "@/components/ReviewActions";
import { StatusBadge } from "@/components/StatusBadge";
import { diffDownloadUrl, getTask } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function TaskDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  let task;
  try {
    task = await getTask(id);
  } catch {
    notFound();
  }

  const latestPatch = [...task.patch_attempts].sort(
    (a, b) => b.attempt_number - a.attempt_number,
  )[0];

  return (
    <main className="section">
      <div className="detail-header">
        <div>
          <p className="meta">
            <Link href="/tasks">← Queue</Link>
          </p>
          <h1>{task.issue?.title || task.issue_title || "Repair task"}</h1>
          <p className="meta">
            {task.github_owner}/{task.github_repo}#{task.issue_number}
            {task.issue_url ? (
              <>
                {" · "}
                <a href={task.issue_url} target="_blank" rel="noreferrer">
                  GitHub
                </a>
              </>
            ) : null}
            {task.commit_sha ? ` · ${task.commit_sha.slice(0, 7)}` : ""}
          </p>
        </div>
        <StatusBadge status={task.status} />
      </div>

      <div className="stack">
        {task.error_message ? <div className="panel error">{task.error_message}</div> : null}

        <div className="grid-2">
          <div className="panel stack">
            <h3 style={{ margin: 0, fontFamily: "var(--font-display)" }}>Issue</h3>
            <pre className="mono" style={{ maxHeight: 260 }}>
              {task.issue?.body || "No issue body"}
            </pre>
            <h3 style={{ margin: 0, fontFamily: "var(--font-display)" }}>Checklist</h3>
            <ul className="steps">
              {(task.checklist_items.length
                ? task.checklist_items
                : (task.issue?.acceptance_criteria || []).map((c, i) => ({
                    id: String(i),
                    ordinal: i,
                    text: c.text,
                    completed: !!c.verified,
                  }))
              ).map((item) => (
                <li key={item.id}>
                  <span className="dot" />
                  <span>
                    {item.completed ? "✓ " : ""}
                    {item.text}
                  </span>
                </li>
              ))}
            </ul>
          </div>

          <div className="panel stack">
            <h3 style={{ margin: 0, fontFamily: "var(--font-display)" }}>Patch plan</h3>
            {task.patch_plan ? (
              <>
                <p style={{ margin: 0 }}>{task.patch_plan.summary}</p>
                <p className="meta">{task.patch_plan.rationale}</p>
                <ol>
                  {task.patch_plan.steps.map((step) => (
                    <li key={step}>{step}</li>
                  ))}
                </ol>
                <p className="meta">Targets: {(task.patch_plan.target_files || []).join(", ") || "—"}</p>
              </>
            ) : (
              <p className="meta">Plan not ready yet.</p>
            )}
            {task.code_index_stats ? (
              <p className="meta">
                Indexed {task.code_index_stats.file_count} files /{" "}
                {task.code_index_stats.symbol_count} symbols
              </p>
            ) : null}
          </div>
        </div>

        <div className="panel stack">
          <div className="actions" style={{ justifyContent: "space-between" }}>
            <h3 style={{ margin: 0, fontFamily: "var(--font-display)" }}>Unified diff</h3>
            {latestPatch ? (
              <a className="btn btn-ghost" href={diffDownloadUrl(task.id)}>
                Download .patch
              </a>
            ) : null}
          </div>
          <pre className="mono">{latestPatch?.unified_diff || "No diff yet — agent still running."}</pre>
        </div>

        <div className="grid-2">
          <div className="panel stack">
            <h3 style={{ margin: 0, fontFamily: "var(--font-display)" }}>Evidence</h3>
            {task.evidence.length === 0 ? (
              <p className="meta">Waiting for sandbox evidence…</p>
            ) : (
              task.evidence.map((ev) => (
                <div key={ev.id}>
                  <div className="meta">
                    {ev.kind} · exit {ev.exit_code ?? "—"} ·{" "}
                    {ev.passed == null ? "n/a" : ev.passed ? "passed" : "failed"}
                  </div>
                  {ev.command ? <div className="meta">{ev.command}</div> : null}
                  <pre className="mono" style={{ maxHeight: 180 }}>
                    {(ev.stdout || ev.stderr || "").slice(0, 4000) || "(empty)"}
                  </pre>
                </div>
              ))
            )}
          </div>

          <div className="panel stack">
            <h3 style={{ margin: 0, fontFamily: "var(--font-display)" }}>PR summary</h3>
            {task.pr_summary ? (
              <>
                <strong>{task.pr_summary.title}</strong>
                <pre className="mono" style={{ maxHeight: 220 }}>
                  {task.pr_summary.body}
                </pre>
                <ul>
                  {task.pr_summary.test_plan.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </>
            ) : (
              <p className="meta">PR draft pending.</p>
            )}

            <h3 style={{ margin: 0, fontFamily: "var(--font-display)" }}>Agent trace</h3>
            <ul className="steps">
              {task.traces.map((tr) => (
                <li key={tr.id}>
                  <span className="dot" />
                  <span>
                    {tr.step}
                    {tr.tool_name ? ` · ${tr.tool_name}` : ""}
                    {tr.duration_ms != null ? ` · ${tr.duration_ms}ms` : ""}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </div>

        <div className="panel">
          <h3 style={{ marginTop: 0, fontFamily: "var(--font-display)" }}>Human review</h3>
          <ReviewActions taskId={task.id} />
          {task.review ? (
            <p className="meta" style={{ marginTop: "1rem" }}>
              Last decision: {task.review.decision} by {task.review.reviewer}
              {task.review.comments ? ` — ${task.review.comments}` : ""}
            </p>
          ) : null}
        </div>
      </div>
    </main>
  );
}