import type {
  CreateRequestBody,
  CreateRequestResponse,
  MetricsSummary,
  OutcomeBody,
} from "./types";

const BASE_URL = import.meta.env.VITE_BACKEND_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(message: string, public status?: number) {
    super(message);
    this.name = "ApiError";
  }
}

async function asJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new ApiError(`${res.status} ${res.statusText}: ${body}`, res.status);
  }
  return res.json() as Promise<T>;
}

export async function createRequest(body: CreateRequestBody): Promise<CreateRequestResponse> {
  const res = await fetch(`${BASE_URL}/requests`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return asJson<CreateRequestResponse>(res);
}

export async function cancelRequest(requestId: string): Promise<void> {
  await fetch(`${BASE_URL}/requests/${requestId}`, { method: "DELETE" }).catch(() => {
    // best-effort — the request may already be complete, which is fine
  });
}

export async function reportOutcome(requestId: string, body: OutcomeBody): Promise<void> {
  const res = await fetch(`${BASE_URL}/requests/${requestId}/outcome`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  await asJson(res);
}

export async function fetchMetricsSummary(): Promise<MetricsSummary> {
  const res = await fetch(`${BASE_URL}/metrics/summary`);
  return asJson<MetricsSummary>(res);
}

export interface StreamHandlers {
  onToken: (text: string) => void;
  onComplete: (fullText: string) => void;
  onError: (message: string) => void;
}

/**
 * Opens the SSE stream for a request and wires named events (per
 * backend/main.py's `event: token|complete|error`). Returns the
 * EventSource so the caller can `.close()` it early on cancel/supersede.
 */
export function streamDraft(requestId: string, handlers: StreamHandlers): EventSource {
  const source = new EventSource(`${BASE_URL}/requests/${requestId}/stream`);

  source.addEventListener("token", (evt) => {
    const data = JSON.parse((evt as MessageEvent).data);
    handlers.onToken(data.text ?? "");
  });

  source.addEventListener("complete", (evt) => {
    const data = JSON.parse((evt as MessageEvent).data);
    handlers.onComplete(data.text ?? "");
    source.close();
  });

  source.addEventListener("error", (evt) => {
    const msgEvt = evt as MessageEvent;
    const message = msgEvt.data ? JSON.parse(msgEvt.data).message : "stream connection error";
    handlers.onError(message);
    source.close();
  });

  return source;
}
