export function isTerminalJobStatus(status: unknown): boolean {
  if (typeof status !== "string" || !status) return false;
  return ["done", "error", "stopped", "complete", "completed", "failed"].includes(status.toLowerCase());
}

export async function wait(ms: number, signal?: AbortSignal): Promise<void> {
  if (signal?.aborted) {
    throw new DOMException("Aborted", "AbortError");
  }
  await new Promise<void>((resolve, reject) => {
    const timer = setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    const onAbort = () => {
      clearTimeout(timer);
      reject(new DOMException("Aborted", "AbortError"));
    };
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}

export async function pollJob<T extends { status?: string }>(
  fetchStatus: () => Promise<T>,
  onTick: (job: T) => void,
  opts?: { intervalMs?: number; signal?: AbortSignal },
): Promise<T> {
  const intervalMs = opts?.intervalMs ?? 4000;
  for (;;) {
    if (opts?.signal?.aborted) {
      throw new DOMException("Aborted", "AbortError");
    }
    const job = await fetchStatus();
    onTick(job);
    if (isTerminalJobStatus(job.status)) return job;
    await wait(intervalMs, opts?.signal);
  }
}
