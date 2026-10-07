"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { reviewTask, retryTask } from "@/lib/api";

export function ReviewActions({ taskId }: { taskId: string }) {
  const router = useRouter();
  const [comments, setComments] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function act(decision: "approved" | "rejected" | "needs_changes") {
    setBusy(true);
    setError(null);
    try {
      await reviewTask(taskId, decision, comments || undefined);
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Review failed");
    } finally {
      setBusy(false);
    }
  }

  async function onRetry() {
    setBusy(true);
    setError(null);
    try {
      await retryTask(taskId);
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Retry failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack">
      <label>
        Reviewer notes
        <textarea
          value={comments}
          onChange={(e) => setComments(e.target.value)}
          placeholder="Optional notes for the audit trail"
        />
      </label>
      <div className="actions">
        <button className="btn btn-primary" disabled={busy} onClick={() => act("approved")}>
          Approve patch
        </button>
        <button className="btn btn-ghost" disabled={busy} onClick={() => act("needs_changes")}>
          Needs changes
        </button>
        <button className="btn btn-ghost" disabled={busy} onClick={() => act("rejected")}>
          Reject
        </button>
        <button className="btn btn-ghost" disabled={busy} onClick={onRetry}>
          Re-run agent
        </button>
      </div>
      {error ? <p className="error">{error}</p> : null}
    </div>
  );
}