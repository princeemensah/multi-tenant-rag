import { env } from "@/lib/env";
import { readSession } from "@/lib/session";

interface ApiError {
  status: number;
  message: string;
  details?: unknown;
}

type RequestOptions = Omit<RequestInit, "body" | "headers"> & {
  body?: unknown;
  headers?: HeadersInit;
  tenantId?: string;
  accessToken?: string;
};

const BASE_URL = env.NEXT_PUBLIC_BACKEND_URL.replace(/\/$/, "");

function buildUrl(path: string): string {
  if (path.startsWith("http")) {
    return path;
  }
  const normalized = path.startsWith("/") ? path : `/${path}`;
  return `${BASE_URL}${normalized}`;
}

async function request<TResponse>(
  path: string,
  options: RequestOptions = {}
): Promise<{ data: TResponse | null; error: ApiError | null }> {
  const { body, headers, tenantId, accessToken, ...init } = options;

  const isFormData =
    typeof FormData !== "undefined" && body instanceof FormData;

  const finalHeaders = new Headers(headers);
  finalHeaders.set("Accept", "application/json");

  if (!isFormData && body !== undefined && body !== null) {
    finalHeaders.set("Content-Type", "application/json");
  }

  if (tenantId) {
    finalHeaders.set("X-Tenant-ID", tenantId);
  } else {
    const session = readSession();
    if (session?.tenant?.id) {
      finalHeaders.set("X-Tenant-ID", session.tenant.id);
    }
  }

  if (accessToken) {
    finalHeaders.set("Authorization", `Bearer ${accessToken}`);
  } else {
    const session = readSession();
    if (session?.access_token) {
      finalHeaders.set("Authorization", `Bearer ${session.access_token}`);
    }
  }

  const payload =
    body !== undefined && body !== null
      ? (isFormData ? body : JSON.stringify(body))
      : undefined;

  const response = await fetch(buildUrl(path), {
    ...init,
    headers: finalHeaders,
    body: payload as BodyInit | undefined,
    cache: init.cache ?? "no-store",
  });

  const contentType = response.headers.get("Content-Type") ?? "";
  const isJson = contentType.includes("application/json");

  if (!response.ok) {
    const errorPayload = isJson ? await response.json().catch(() => null) : null;
    return {
      data: null,
      error: {
        status: response.status,
        message: response.statusText || "Request failed",
        details: errorPayload,
      },
    };
  }

  if (!isJson) {
    return { data: null, error: { status: response.status, message: "Unexpected content type" } };
  }

  const parsed = (await response.json()) as TResponse;
  return { data: parsed, error: null };
}

export const apiClient = {
  request,
  get: <TResponse>(path: string, options?: RequestOptions) =>
    request<TResponse>(path, { ...options, method: "GET" }),
  post: <TResponse>(path: string, options?: RequestOptions) =>
    request<TResponse>(path, { ...options, method: "POST" }),
  put: <TResponse>(path: string, options?: RequestOptions) =>
    request<TResponse>(path, { ...options, method: "PUT" }),
  patch: <TResponse>(path: string, options?: RequestOptions) =>
    request<TResponse>(path, { ...options, method: "PATCH" }),
  delete: <TResponse>(path: string, options?: RequestOptions) =>
    request<TResponse>(path, { ...options, method: "DELETE" }),
};
