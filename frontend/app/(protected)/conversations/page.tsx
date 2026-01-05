"use client";

import { useMemo, useState, type FormEvent } from "react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useConversations } from "@/hooks/use-conversations";
import { useTenant } from "@/hooks/use-tenant";
import { apiClient } from "@/lib/api-client";

export default function ConversationsPage() {
  const { tenant, tenantId } = useTenant();
  const {
    data,
    error,
    isLoading,
    isValidating,
    page,
    size,
    mutate,
    setPage,
  } = useConversations();

  const [newTitle, setNewTitle] = useState("");
  const [createError, setCreateError] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);

  const handleCreate = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!tenantId) {
      setCreateError("Select a tenant before creating a conversation.");
      return;
    }

    const title = newTitle.trim() || undefined;

    try {
      setIsCreating(true);
      setCreateError(null);
      const { data: created, error: createErr } = await apiClient.post(
        "/conversations",
        {
          body: { title },
          tenantId,
        }
      );

      if (createErr || !created) {
        throw new Error(createErr?.message ?? "Failed to create conversation");
      }

      setNewTitle("");
      setPage(1);
      await mutate();
    } catch (submitError) {
      const message = submitError instanceof Error ? submitError.message : "Unexpected error";
      setCreateError(message);
    } finally {
      setIsCreating(false);
    }
  };

  const sessions = data?.sessions ?? [];
  const totalPages = data?.pages ?? 1;

  const subtitle = useMemo(() => {
    if (!tenantId) {
      return "Select a tenant to load conversation history.";
    }
    if (isLoading && !data) {
      return `Fetching conversations for ${tenant?.name ?? "your tenant"}…`;
    }
    return `Tracking ${data?.total ?? 0} conversations for ${tenant?.name ?? "this tenant"}.`;
  }, [tenantId, isLoading, data, tenant]);

  const canGoPrev = page > 1;
  const canGoNext = page < totalPages;

  return (
    <section className="space-y-4">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold">Conversations</h1>
        <p className="text-sm text-muted-foreground">{subtitle}</p>
      </header>

      <div className="rounded-lg border bg-card p-4">
        <form className="flex flex-col gap-3 sm:flex-row sm:items-end" onSubmit={handleCreate}>
          <div className="flex-1 space-y-2">
            <Label htmlFor="conversation-title">Session title</Label>
            <Input
              id="conversation-title"
              placeholder="e.g. Incident deep-dive"
              value={newTitle}
              onChange={(event) => setNewTitle(event.target.value)}
              disabled={!tenantId || isCreating}
            />
          </div>
          <Button
            type="submit"
            disabled={!tenantId || isCreating}
            className="sm:w-auto"
          >
            {isCreating ? "Creating…" : "New session"}
          </Button>
        </form>
        {createError ? (
          <p className="mt-2 text-sm text-destructive">{createError}</p>
        ) : null}
        {!tenantId ? (
          <p className="mt-2 text-xs text-muted-foreground">
            Choose a tenant to enable session creation.
          </p>
        ) : null}
      </div>

      {!tenantId ? (
        <div className="rounded-lg border border-dashed bg-card p-6 text-sm text-muted-foreground">
          Use the tenant switcher above to choose an organization context.
        </div>
      ) : error ? (
        <div className="rounded-lg border bg-destructive/10 p-4 text-sm text-destructive">
          Failed to load conversations: {error.message}
        </div>
      ) : (
        <div className="rounded-lg border bg-card">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[32rem] table-fixed">
              <thead>
                <tr className="border-b bg-muted/40 text-left text-xs uppercase text-muted-foreground">
                  <th className="px-4 py-3 font-medium">Title</th>
                  <th className="px-4 py-3 font-medium">Messages</th>
                  <th className="px-4 py-3 font-medium">Updated</th>
                  <th className="px-4 py-3 font-medium">Created</th>
                </tr>
              </thead>
              <tbody>
                {isLoading && !data ? (
                  Array.from({ length: 3 }).map((_, index) => (
                    <tr key={`skeleton-${index}`} className="animate-pulse border-b">
                      <td className="px-4 py-4">
                        <div className="h-4 w-2/3 rounded bg-muted" />
                      </td>
                      <td className="px-4 py-4">
                        <div className="h-4 w-12 rounded bg-muted" />
                      </td>
                      <td className="px-4 py-4">
                        <div className="h-4 w-24 rounded bg-muted" />
                      </td>
                      <td className="px-4 py-4">
                        <div className="h-4 w-24 rounded bg-muted" />
                      </td>
                    </tr>
                  ))
                ) : sessions.length === 0 ? (
                  <tr>
                    <td className="px-4 py-6 text-sm text-muted-foreground" colSpan={4}>
                      No conversations recorded yet.
                    </td>
                  </tr>
                ) : (
                  sessions.map((session) => (
                    <tr key={session.id} className="border-b last:border-b-0">
                      <td className="px-4 py-3 text-sm font-medium text-foreground">
                        <Link
                          href={`/conversations/${session.id}`}
                          className="underline-offset-4 hover:underline"
                        >
                          {session.title}
                        </Link>
                      </td>
                      <td className="px-4 py-3 text-sm text-muted-foreground">
                        {session.message_count}
                      </td>
                      <td className="px-4 py-3 text-sm text-muted-foreground">
                        {new Date(session.updated_at ?? session.created_at).toLocaleString()}
                      </td>
                      <td className="px-4 py-3 text-sm text-muted-foreground">
                        {new Date(session.created_at).toLocaleString()}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
          <footer className="flex items-center justify-between border-t px-4 py-3 text-xs text-muted-foreground">
            <span>
              Page {page} of {totalPages}
              {isValidating ? " • Refreshing…" : ""}
            </span>
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" disabled={!canGoPrev}
                onClick={() => canGoPrev && setPage(page - 1)}
              >
                Previous
              </Button>
              <Button variant="outline" size="sm" disabled={!canGoNext}
                onClick={() => canGoNext && setPage(page + 1)}
              >
                Next
              </Button>
            </div>
          </footer>
        </div>
      )}
    </section>
  );
}
