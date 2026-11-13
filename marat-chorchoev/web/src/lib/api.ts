import { clearSession, getSession } from "./session";

export const API_BASE = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
export const API = `${API_BASE}/api/v1`;

export interface FieldError {
  field: string;
  message: string;
}

export class ApiError extends Error {
  status: number;
  code: string;
  details: unknown;
  requestId?: string;

  constructor(status: number, code: string, message: string, details?: unknown, requestId?: string) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
    this.requestId = requestId;
  }

  /** Server-side field errors keyed by field name. */
  get fields(): Record<string, string> {
    const list = (this.details as { fields?: FieldError[] } | undefined)?.fields ?? [];
    return Object.fromEntries(list.map((f) => [f.field, f.message]));
  }
}

type QueryValue = string | number | boolean | null | undefined | (string | number)[];
export type Query = Record<string, QueryValue>;

export function buildQuery(query?: Query): string {
  if (!query) return "";
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === "") continue;
    if (Array.isArray(value)) value.forEach((v) => params.append(key, String(v)));
    else params.set(key, String(value));
  }
  const text = params.toString();
  return text ? `?${text}` : "";
}

export interface RequestOptions {
  body?: unknown;
  form?: FormData;
  query?: Query;
  headers?: Record<string, string>;
  signal?: AbortSignal;
}

function authHeaders(): Record<string, string> {
  const session = getSession();
  const headers: Record<string, string> = {};
  if (session) {
    headers.Authorization = `Bearer ${session.token}`;
    if (session.orgId) headers["X-Organization-ID"] = session.orgId;
  }
  return headers;
}

export async function raw(method: string, path: string, opts: RequestOptions = {}): Promise<Response> {
  const headers: Record<string, string> = { ...authHeaders(), ...opts.headers };
  let body: BodyInit | undefined;
  if (opts.form) {
    body = opts.form;
  } else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  try {
    return await fetch(`${API}${path}${buildQuery(opts.query)}`, {
      method,
      headers,
      body,
      signal: opts.signal,
      cache: "no-store",
    });
  } catch (error) {
    if ((error as Error).name === "AbortError") throw error;
    throw new ApiError(0, "NETWORK_ERROR", "Cannot reach the server. Check your connection and try again.");
  }
}

export async function request<T>(method: string, path: string, opts: RequestOptions = {}): Promise<T> {
  const response = await raw(method, path, opts);
  const text = await response.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = null;
  }
  if (!response.ok) {
    const err = (data as { error?: { code: string; message: string; details?: unknown }; request_id?: string } | null) ?? {};
    // An expired or revoked session ends the local session so every screen redirects to sign-in.
    if (response.status === 401 && path !== "/auth/login") clearSession();
    throw new ApiError(
      response.status,
      err.error?.code ?? "HTTP_ERROR",
      err.error?.message ?? `Request failed (${response.status}).`,
      err.error?.details,
      err.request_id,
    );
  }
  return data as T;
}

export const api = {
  get: <T>(path: string, query?: Query, signal?: AbortSignal) => request<T>("GET", path, { query, signal }),
  post: <T>(path: string, body: unknown = {}, headers?: Record<string, string>) =>
    request<T>("POST", path, { body, headers }),
  put: <T>(path: string, body: unknown) => request<T>("PUT", path, { body }),
  patch: <T>(path: string, body: unknown) => request<T>("PATCH", path, { body }),
  del: <T>(path: string) => request<T>("DELETE", path),
  upload: <T>(path: string, form: FormData) => request<T>("POST", path, { form }),
};

/** Fetch an authorized file and expose it as an object URL (plain links are not authorized). */
export async function fetchBlobUrl(contentUrl: string): Promise<string> {
  const response = await raw("GET", contentUrl.replace(/^\/api\/v1/, ""));
  if (!response.ok) throw new ApiError(response.status, "FILE_ERROR", "Could not load the file.");
  return URL.createObjectURL(await response.blob());
}

export function newCommandId(prefix = "web"): string {
  const random =
    typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : String(Math.random()).slice(2);
  return `${prefix}-${random}`;
}
