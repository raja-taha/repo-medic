const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export type TaskStatus =
  | "queued"
  | "cloning"
  | "indexing"
  | "reproducing"
  | "planning"
  | "patching"
  | "verifying"
  | "awaiting_review"
  | "approved"
  | "rejected"
  | "failed"
  | "cancelled";

export interface TaskSummary {
  id: string;
  github_owner: string;
  github_repo: string;
  issue_number: number;
  issue_url?: string | null;
  language: string;
  status: TaskStatus;
  error_message?: string | null;
  created_at: string;
  updated_at: string;
  issue_title?: string | null;
}

export interface TaskDetail extends TaskSummary {
  workspace_path?: string | null;
  commit_sha?: string | null;
  issue?: {
    title: string;
    body: string;
    labels: string[];
    author?: string | null;
    acceptance_criteria: Array<{ id?: string; text: string; verified?: boolean }>;
  } | null;
  checklist_items: Array<{
    id: string;
    ordinal: number;
    text: string;
    completed: boolean;
    evidence_note?: string | null;
  }>;
  patch_plan?: {
    summary: string;
    rationale: string;
    steps: string[];
    target_files: string[];
    risk_notes?: string | null;
  } | null;
  patch_attempts: Array<{
    id: string;
    attempt_number: number;
    unified_diff: string;
    files_changed: string[];
    success: boolean;
    validation_errors: string[];
    created_at: string;
  }>;
  evidence: Array<{
    id: string;
    kind: string;
    command?: string | null;
    exit_code?: number | null;
    stdout: string;
    stderr: string;
    passed?: boolean | null;
    created_at: string;
  }>;
  traces: Array<{
    id: string;
    step: string;
    tool_name?: string | null;
    duration_ms?: number | null;
    created_at: string;
    input_payload: Record<string, unknown>;
    output_payload: Record<string, unknown>;
  }>;
  pr_summary?: {
    title: string;
    body: string;
    test_plan: string[];
  } | null;
  review?: {
    decision: string;
    reviewer: string;
    comments?: string | null;
    created_at: string;
  } | null;
  code_index_stats?: { file_count: number; symbol_count: number } | null;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
    cache: "no-store",
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Request failed: ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export function listTasks() {
  return request<TaskSummary[]>("/api/v1/tasks");
}

export function getTask(id: string) {
  return request<TaskDetail>(`/api/v1/tasks/${id}`);
}

export function createTask(body: {
  github_owner: string;
  github_repo: string;
  issue_number: number;
  language?: string;
  issue_title?: string;
  issue_body?: string;
  synthetic?: boolean;
}) {
  return request<TaskDetail>("/api/v1/tasks", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function createTaskFromUrl(issue_url: string, language = "python") {
  return request<TaskDetail>("/api/v1/tasks/from-url", {
    method: "POST",
    body: JSON.stringify({ issue_url, language }),
  });
}

export function reviewTask(
  id: string,
  decision: "approved" | "rejected" | "needs_changes",
  comments?: string,
) {
  return request<TaskDetail>(`/api/v1/tasks/${id}/review`, {
    method: "POST",
    body: JSON.stringify({ decision, comments, reviewer: "human" }),
  });
}

export function retryTask(id: string) {
  return request<TaskDetail>(`/api/v1/tasks/${id}/retry`, { method: "POST" });
}

export function diffDownloadUrl(id: string) {
  return `${API_BASE}/api/v1/tasks/${id}/diff/raw`;
}