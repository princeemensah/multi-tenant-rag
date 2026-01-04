"use client";

import { useCallback, type ReactNode } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/hooks/use-auth";
import { MainNav } from "@/components/layout/main-nav";
import { TenantSwitcher } from "@/components/layout/tenant-switcher";

interface AppShellProps {
  children: ReactNode;
}

export function AppShell({ children }: AppShellProps) {
  const router = useRouter();
  const { user, logout } = useAuth();

  const handleLogout = useCallback(() => {
    logout();
    router.replace("/login");
  }, [logout, router]);

  return (
    <div className="flex min-h-screen flex-col bg-muted/20">
      <header className="border-b bg-background">
        <div className="mx-auto flex w-full max-w-5xl flex-col gap-3 p-4">
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div className="flex flex-col gap-2 md:flex-row md:items-center md:gap-4">
              <div>
                <p className="text-lg font-semibold">AI Operations Assistant</p>
                <p className="text-xs text-muted-foreground">Operate securely across tenants</p>
              </div>
              <TenantSwitcher />
            </div>
            <div className="flex items-center gap-4 text-right">
              <div className="hidden sm:block">
                <p className="text-sm font-medium">{user?.username ?? user?.email ?? "User"}</p>
                <p className="text-xs text-muted-foreground">{user?.email ?? ""}</p>
              </div>
              <Button variant="outline" onClick={handleLogout}>
                Sign out
              </Button>
            </div>
          </div>
          <MainNav />
        </div>
      </header>
      <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-6 p-6">
        {children}
      </main>
    </div>
  );
}
