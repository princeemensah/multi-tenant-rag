"use client";

import { useMemo } from "react";

import { useAuthContext } from "@/components/providers/auth-provider";

export function useAuth() {
  const context = useAuthContext();

  return useMemo(
    () => ({
      ...context,
      accessToken: context.session?.access_token ?? null,
      user: context.session?.user ?? null,
      tenant: context.session?.tenant ?? null,
    }),
    [context]
  );
}
