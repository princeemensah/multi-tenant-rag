"use client";

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

type StreamOptions = RequestOptions & {
  method?: string;
  onMessage: (data: string) => void;
  onDone?: () => void;
  onError?: (error: Error) => void;
};

const BASE_URL = env.NEXT_PUBLIC_BACKEND_URL.replace(/\/$/, "");

function buildUrl(path: string): string {
  if (path.startsWith("http")) {
    return path;
  }
  const normalized = path.startsWith("/") ? path : `/${path}`;
  return `${BASE_URL}${normalized}`;
}

function prepareRequest(path: string, options: RequestOptions = {}): { url: string; init: RequestInit } {
  const { body, headers, tenantId, accessToken, ...init } = options;

  const isFormData =
    typeof FormData !== "undefined" && body instanceof FormData;

  const finalHeaders = new Headers(headers);
  if (!finalHeaders.has("Accept")) {
    finalHeaders.set("Accept", "application/json");
  }

  if (!isFormData && body !== undefined && body !== null && !finalHeaders.has("Content-Type")) {
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
      ? (isFormData ? (body as BodyInit) : (JSON.stringify(body) as BodyInit))
      : undefined;

  const initWithDefaults: RequestInit = {
    ...init,
    headers: finalHeaders,
    body: payload,
  };

  if (!initWithDefaults.cache) {
    initWithDefaults.cache = "no-store";
  }

  return { url: buildUrl(path), init: initWithDefaults };
}

async function request<TResponse>(
  path: string,
  options: RequestOptions = {}
): Promise<{ data: TResponse | null; error: ApiError | null }> {
  const { url, init } = prepareRequest(path, options);

  const response = await fetch(url, init);

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

async function stream(
  path: string,
  options: StreamOptions
): Promise<void> {
  const { onMessage, onDone, onError, ...rest } = options;
  const { url, init } = prepareRequest(path, rest);

  if (init.headers instanceof Headers) {
    init.headers.set("Accept", "text/event-stream");
  }

  try {
    const response = await fetch(url, init);
    if (!response.ok) {
      const message = response.statusText || "Stream request failed";
      const error = new Error(message);
      if (onError) onError(error);
      throw error;
    }

    if (!response.body) {
      const error = new Error("Streaming response body unavailable");
      if (onError) onError(error);
      throw error;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    const handlePayload = (segment: string) => {
      const payload = segment
        .split("\n")
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.replace(/^data:\s?/, ""))
        .join("\n");

      if (!payload) {
        return;
      }

      if (payload === "[DONE]") {
        if (onDone) onDone();
        throw new Error("__STREAM_COMPLETE__");
      }

      if (payload === "[ERROR]") {
        const error = new Error("Stream reported error");
        if (onError) onError(error);
        throw error;
      }

      onMessage(payload);
    };

    const flushBuffer = (force = false) => {
      let boundary = buffer.indexOf("\n\n");
      while (boundary !== -1) {
        const rawEvent = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        handlePayload(rawEvent);
        boundary = buffer.indexOf("\n\n");
      }
      if (force && buffer.trim()) {
        handlePayload(buffer);
        buffer = "";
      }
    };

    try {
      // eslint-disable-next-line no-constant-condition
      while (true) {
        const { value, done } = await reader.read();
        if (done) {
          flushBuffer(true);
          if (onDone) onDone();
          break;
        }
        buffer += decoder.decode(value, { stream: true });
        flushBuffer();
      }
    } catch (innerError) {
      if (innerError instanceof Error && innerError.message === "__STREAM_COMPLETE__") {
        return;
      }
      if (onError) onError(innerError as Error);
      throw innerError;
    } finally {
      reader.releaseLock();
    }
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      if (onError) onError(error);
      throw error;
    }
    if (onError) onError(error as Error);
    throw error;
  }
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
  stream,
};
