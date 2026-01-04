"use client";

import { useEffect, useMemo, useState } from "react";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { ChevronsUpDown, Check } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/hooks/use-auth";
import { cn } from "@/lib/utils";
import type { Tenant } from "@/types/auth";
import { apiClient } from "@/lib/api-client";

export function TenantSwitcher() {
  const { tenant, setActiveTenant } = useAuth();
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    async function fetchTenants() {
      setLoading(true);
      setError(null);
      const { data, error: fetchError } = await apiClient.get<Tenant[]>("/auth/tenants");
      if (!active) return;

      if (fetchError || !data) {
        setError(fetchError?.message ?? "Unable to load tenants");
        setLoading(false);
        return;
      }

      setTenants(data);
      setLoading(false);
    }

    fetchTenants();

    return () => {
      active = false;
    };
  }, []);

  const sortedTenants = useMemo(() => {
    const list = [...tenants];
    if (tenant && !list.find((entry) => entry.id === tenant.id)) {
      list.unshift(tenant);
    }
    return list;
  }, [tenant, tenants]);

  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <Button
          variant="outline"
          className="flex items-center gap-2"
          aria-label="Select tenant"
        >
          <span className="truncate max-w-[10rem]">
            {tenant?.name ?? (loading ? "Loading tenants…" : "Select tenant")}
          </span>
          <ChevronsUpDown className="h-4 w-4 opacity-60" />
        </Button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Content
        align="start"
        sideOffset={4}
        className="min-w-[14rem] rounded-md border bg-popover p-1 text-sm shadow-md"
      >
        {error ? (
          <div className="px-2 py-2 text-xs text-destructive">{error}</div>
        ) : null}
        <DropdownMenu.Label className="px-2 py-1.5 text-xs text-muted-foreground">
          Tenants
        </DropdownMenu.Label>
        <DropdownMenu.Separator className="my-1 h-px bg-border" />
        {sortedTenants.length === 0 && !loading ? (
          <DropdownMenu.Item disabled className="px-2 py-2 text-xs text-muted-foreground">
            No tenants available
          </DropdownMenu.Item>
        ) : null}
        {sortedTenants.map((entry) => {
          const isActive = tenant?.id === entry.id;
          return (
            <DropdownMenu.Item
              key={entry.id}
              className={cn(
                "flex cursor-pointer select-none items-center gap-2 rounded-sm px-2 py-2 outline-none transition-colors",
                isActive ? "bg-secondary text-secondary-foreground" : "hover:bg-muted"
              )}
              onSelect={(event) => {
                event.preventDefault();
                setActiveTenant(entry);
              }}
            >
              <Check
                className={cn("h-4 w-4", isActive ? "opacity-100" : "opacity-0")}
              />
              <span className="flex-1 truncate">{entry.name}</span>
              <span className="text-xs text-muted-foreground">{entry.subdomain ?? ""}</span>
            </DropdownMenu.Item>
          );
        })}
        <DropdownMenu.Separator className="my-1 h-px bg-border" />
        <DropdownMenu.Item
          className="flex cursor-pointer select-none items-center gap-2 rounded-sm px-2 py-2 text-xs text-muted-foreground outline-none transition-colors hover:bg-muted"
          onSelect={(event) => {
            event.preventDefault();
            setActiveTenant(null);
          }}
        >
          Clear tenant selection
        </DropdownMenu.Item>
        <DropdownMenu.Separator className="my-1 h-px bg-border" />
      </DropdownMenu.Content>
    </DropdownMenu.Root>
  );
}
