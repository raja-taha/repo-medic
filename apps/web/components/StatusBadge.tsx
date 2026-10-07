import type { TaskStatus } from "@/lib/api";

export function StatusBadge({ status }: { status: TaskStatus }) {
  return <span className={`badge ${status}`}>{status.replaceAll("_", " ")}</span>;
}