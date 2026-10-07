"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { createTask, createTaskFromUrl } from "@/lib/api";

export function NewTaskForm() {
  const router = useRouter();
  const [mode, setMode] = useState<"url" | "manual">("url");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const data = new FormData(e.currentTarget);
    try {
      let task;
      if (mode === "url") {
        task = await createTaskFromUrl(
          String(data.get("issue_url") || ""),
          String(data.get("language") || "python"),
        );
      } else {
        task = await createTask({
          github_owner: String(data.get("github_owner") || ""),
          github_repo: String(data.get("github_repo") || ""),
          issue_number: Number(data.get("issue_number") || 1),
          language: String(data.get("language") || "python"),
          issue_title: String(data.get("issue_title") || "") || undefined,
          issue_body: String(data.get("issue_body") || "") || undefined,
          synthetic: data.get("synthetic") === "on",
        });
      }
      router.push(`/tasks/${task.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create task");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="form-grid" onSubmit={onSubmit}>
      <div className="actions">
        <button
          type="button"
          className={`btn ${mode === "url" ? "btn-primary" : "btn-ghost"}`}
          onClick={() => setMode("url")}
        >
          From issue URL
        </button>
        <button
          type="button"
          className={`btn ${mode === "manual" ? "btn-primary" : "btn-ghost"}`}
          onClick={() => setMode("manual")}
        >
          Manual / synthetic
        </button>
      </div>

      {mode === "url" ? (
        <label>
          GitHub issue URL
          <input
            name="issue_url"
            required
            placeholder="https://github.com/owner/repo/issues/42"
          />
        </label>
      ) : (
        <>
          <div className="grid-2" style={{ gap: "0.75rem" }}>
            <label>
              Owner
              <input name="github_owner" required placeholder="octocat" />
            </label>
            <label>
              Repo
              <input name="github_repo" required placeholder="hello-world" />
            </label>
          </div>
          <label>
            Issue number
            <input name="issue_number" type="number" min={1} defaultValue={1} required />
          </label>
          <label>
            Title (optional for synthetic)
            <input name="issue_title" placeholder="Bug: off-by-one in parser" />
          </label>
          <label>
            Body
            <textarea name="issue_body" placeholder="Acceptance criteria / reproduction steps" />
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <input name="synthetic" type="checkbox" />
            Synthetic mode (skip live GitHub fetch / use fixture when configured)
          </label>
        </>
      )}

      <label>
        Language
        <select name="language" defaultValue="python">
          <option value="python">Python</option>
          <option value="typescript">TypeScript</option>
          <option value="javascript">JavaScript</option>
        </select>
      </label>

      {error ? <p className="error">{error}</p> : null}
      <button className="btn btn-primary" disabled={busy} type="submit">
        {busy ? "Queuing…" : "Queue repair agent"}
      </button>
    </form>
  );
}