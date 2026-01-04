"use client";

import { tokenResponseSchema, type TokenResponse } from "@/types/auth";

const STORAGE_KEY = "mt-rag-session";

type StoredSession = TokenResponse;

function isBrowser() {
  return typeof window !== "undefined";
}

export function readSession(): StoredSession | null {
  if (!isBrowser()) {
    return null;
  }

  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (!raw) {
    return null;
  }

  try {
    const parsed = JSON.parse(raw);
    const result = tokenResponseSchema.safeParse(parsed);
    if (!result.success) {
      console.warn("Invalid session payload found in storage", result.error);
      window.localStorage.removeItem(STORAGE_KEY);
      return null;
    }
    return result.data;
  } catch (error) {
    console.error("Failed to parse session payload", error);
    window.localStorage.removeItem(STORAGE_KEY);
    return null;
  }
}

export function writeSession(session: StoredSession) {
  if (!isBrowser()) {
    return;
  }
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
}

export function clearSession() {
  if (!isBrowser()) {
    return;
  }
  window.localStorage.removeItem(STORAGE_KEY);
}

export { STORAGE_KEY };
