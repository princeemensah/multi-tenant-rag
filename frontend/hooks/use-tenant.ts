"use client";

import { useMemo } from "react";

import { useAuth } from "@/hooks/use-auth";

export function useTenant() {
  const { tenant, setActiveTenant } = useAuth();

  return useMemo(
    () => ({
      tenant,
      tenantId: tenant?.id ?? null,
      tenantSubdomain: tenant?.subdomain ?? null,
      setActiveTenant,
    }),
    [tenant, setActiveTenant]
  );
}
