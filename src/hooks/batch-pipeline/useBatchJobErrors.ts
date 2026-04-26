export function toErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message.trim()) return error.message;
  if (typeof error === "string" && error.trim()) return error;
  return fallback;
}

export function normalizeProgress(progress: number): number {
  if (!Number.isFinite(progress) || progress < 0) return 0;
  if (progress > 1) return Math.min(1, progress / 100);
  return Math.min(1, progress);
}

export function isCompleteStatus(status: string): boolean {
  return status === "complete" || status === "done" || status === "success" || status === "succeeded";
}

export function isErrorStatus(status: string): boolean {
  return status === "error" || status === "failed" || status === "failure";
}

export function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
