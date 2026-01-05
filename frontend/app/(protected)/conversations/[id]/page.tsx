"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useConversationMessages } from "@/hooks/use-conversation-messages";
import { useConversations } from "@/hooks/use-conversations";
import { useTenant } from "@/hooks/use-tenant";
import { apiClient } from "@/lib/api-client";
import {
  agentStreamEventSchema,
  type AgentAction,
  type AgentContext,
  type AgentGuardrail,
  type AgentIntent,
  type AgentStreamEvent,
} from "@/types/agent";

interface AgentStreamSnapshot {
  status: "idle" | "processing" | "complete" | "error";
  answer: string;
  contexts: AgentContext[];
  intent: AgentIntent | null;
  action: AgentAction | null;
  guardrails: AgentGuardrail | null;
  strategy?: string | null;
  subqueries: string[];
  model?: string | null;
  errorMessage?: string;
}

export default function ConversationDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const sessionId = params?.id ?? "";

  const { tenantId } = useTenant();
  const {
    data: sessionsData,
    mutate: mutateSessions,
  } = useConversations();
  const session = sessionsData?.sessions.find((item) => item.id === sessionId);

  const [renameValue, setRenameValue] = useState(session?.title ?? "");
  const [renameError, setRenameError] = useState<string | null>(null);
  const [isRenaming, setIsRenaming] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  useEffect(() => {
    setRenameValue(session?.title ?? "");
  }, [session?.title]);

  const {
    data: messagesData,
    error,
    isLoading,
    fetchMore,
    hasMore,
    mutate: mutateMessages,
  } = useConversationMessages({ sessionId });
  const [loadingMore, setLoadingMore] = useState(false);
  const [loadMoreError, setLoadMoreError] = useState<string | null>(null);
  const [messageContent, setMessageContent] = useState("");
  const [sendError, setSendError] = useState<string | null>(null);
  const [isSending, setIsSending] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const streamController = useRef<AbortController | null>(null);
  const [streamSnapshot, setStreamSnapshot] = useState<AgentStreamSnapshot | null>(null);

  const handleLoadMore = async () => {
    try {
      setLoadingMore(true);
      setLoadMoreError(null);
      await fetchMore();
    } catch (loadError) {
      const message = loadError instanceof Error ? loadError.message : "Unable to load more messages";
      setLoadMoreError(message);
    } finally {
      setLoadingMore(false);
    }
  };

  const handleSend = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!tenantId) {
      setSendError("Select a tenant before sending messages.");
      return;
    }

    const content = messageContent.trim();
    if (!content) {
      setSendError("Message cannot be empty.");
      return;
    }

    try {
      setIsSending(true);
      setIsStreaming(true);
      setSendError(null);
      setStreamSnapshot({
        status: "processing",
        answer: "",
        contexts: [],
        intent: null,
        action: null,
        guardrails: null,
        strategy: null,
        subqueries: [],
        model: null,
      });
      setMessageContent("");
      const controller = new AbortController();
      streamController.current = controller;
      let shouldRefresh = false;
      try {
        shouldRefresh = true;
        await apiClient.stream(`/agent/stream`, {
          method: "POST",
          tenantId,
          signal: controller.signal,
          headers: {
            Accept: "text/event-stream",
          },
          body: {
            query: content,
            session_id: sessionId,
            max_chunks: 6,
            score_threshold: 0.35,
            strategy: "informed",
          },
          onMessage: (chunk) => {
            let event: AgentStreamEvent | null = null;
            try {
              event = agentStreamEventSchema.parse(JSON.parse(chunk));
            } catch (parseError) {
              console.warn("Unparseable agent stream payload", parseError);
              return;
            }
            setStreamSnapshot((current) => {
              const base: AgentStreamSnapshot =
                current ?? {
                  status: "processing",
                  answer: "",
                  contexts: [],
                  intent: null,
                  action: null,
                  guardrails: null,
                  strategy: null,
                  subqueries: [],
                  model: null,
                };

              switch (event.type) {
                case "status":
                  return {
                    ...base,
                    status: event.state === "processing" ? "processing" : base.status,
                  };
                case "intent":
                  return {
                    ...base,
                    intent: event.intent,
                  };
                case "contexts":
                  return {
                    ...base,
                    contexts: event.contexts,
                  };
                case "action":
                  return {
                    ...base,
                    action: event.action,
                  };
                case "answer":
                  return {
                    ...base,
                    answer: event.text,
                    strategy: event.strategy ?? base.strategy,
                    subqueries: event.subqueries ?? base.subqueries,
                    model: event.model ?? base.model,
                    guardrails: event.guardrails ?? base.guardrails,
                    status: "complete",
                  };
                case "error":
                  setSendError(event.message);
                  return {
                    ...base,
                    status: "error",
                    errorMessage: event.message,
                  };
                case "done":
                  return {
                    ...base,
                    status: base.status === "error" ? "error" : "complete",
                  };
                default:
                  return base;
              }
            });
          },
          onError: (error) => {
            if (!(error instanceof DOMException && error.name === "AbortError")) {
              const message = error.message || "Failed to stream agent response";
              setSendError(message);
              setStreamSnapshot((current) =>
                current
                  ? {
                      ...current,
                      status: "error",
                      errorMessage: message,
                    }
                  : current
              );
            }
          },
          onDone: () => {
            setStreamSnapshot((current) =>
              current
                ? {
                    ...current,
                    status: current.status === "error" ? "error" : "complete",
                  }
                : current
            );
          },
        });
      } catch (streamError) {
        if (!(streamError instanceof DOMException && streamError.name === "AbortError")) {
          const message = streamError instanceof Error ? streamError.message : "Failed to send message";
          setSendError(message);
          setMessageContent(content);
          setStreamSnapshot((current) =>
            current
              ? {
                  ...current,
                  status: "error",
                  errorMessage: message,
                }
              : current
          );
        }
      } finally {
        streamController.current = null;
        if (shouldRefresh) {
          try {
            await mutateMessages();
            await mutateSessions();
            setStreamSnapshot(null);
          } catch (refreshError) {
            const message = refreshError instanceof Error ? refreshError.message : "Failed to refresh conversation";
            setSendError((current) => current ?? message);
          }
        }
        setIsStreaming(false);
        setIsSending(false);
      }
    } catch (mutationError) {
      const message = mutationError instanceof Error ? mutationError.message : "Failed to send message";
      setSendError(message);
      setMessageContent(content);
      streamController.current = null;
      setStreamSnapshot((current) =>
        current
          ? {
              ...current,
              status: "error",
              errorMessage: message,
            }
          : current
      );
      setIsStreaming(false);
      setIsSending(false);
    }
  };
  useEffect(() => {
    return () => {
      if (streamController.current) {
        streamController.current.abort();
        streamController.current = null;
      }
    };
  }, []);

  const streamPreview = useMemo(() => {
    if (!streamSnapshot) return null;

    const statusLabel =
      streamSnapshot.status === "processing"
        ? "Streaming…"
        : streamSnapshot.status === "error"
        ? "Error"
        : "Draft";

    const trimmedAnswer = streamSnapshot.answer.trim();
    const hasAnswer = trimmedAnswer.length > 0;
    const messageText = hasAnswer
      ? streamSnapshot.answer
      : streamSnapshot.status === "error"
      ? streamSnapshot.errorMessage ?? "Agent execution failed."
      : "Awaiting response from agent…";

    return (
      <li className="border-b bg-muted/30 p-4">
        <div className="flex items-center justify-between text-xs uppercase text-muted-foreground">
          <span>assistant</span>
          <span>{statusLabel}</span>
        </div>
        <p
          className={
            hasAnswer ? "mt-2 whitespace-pre-wrap text-sm text-foreground" : "mt-2 text-sm text-muted-foreground"
          }
        >
          {messageText}
        </p>
      </li>
    );
  }, [streamSnapshot]);

  const activeStreamWarnings = useMemo(() => streamSnapshot?.guardrails?.warnings ?? [], [streamSnapshot]);
  const activeStreamContexts = useMemo(() => streamSnapshot?.contexts ?? [], [streamSnapshot]);

  const handleRename = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!sessionId) return;

    const nextTitle = renameValue.trim();
    if (!nextTitle) {
      setRenameError("Title cannot be empty");
      return;
    }

    try {
      setIsRenaming(true);
      setRenameError(null);
      const { error: renameErr } = await apiClient.patch(`/conversations/${sessionId}`, {
        body: { title: nextTitle },
        tenantId: tenantId ?? undefined,
      });

      if (renameErr) {
        throw new Error(renameErr.message);
      }

      await mutateSessions();
    } catch (mutationError) {
      const message = mutationError instanceof Error ? mutationError.message : "Rename failed";
      setRenameError(message);
    } finally {
      setIsRenaming(false);
    }
  };

  const handleDelete = async () => {
    if (!sessionId) return;
    if (!window.confirm("Delete this conversation? This action cannot be undone.")) {
      return;
    }

    try {
      setIsDeleting(true);
      setDeleteError(null);
      const { error: deleteErr } = await apiClient.delete(`/conversations/${sessionId}`, {
        tenantId: tenantId ?? undefined,
      });

      if (deleteErr) {
        throw new Error(deleteErr.message);
      }

      await mutateSessions();
      router.replace("/conversations");
    } catch (mutationError) {
      const message = mutationError instanceof Error ? mutationError.message : "Delete failed";
      setDeleteError(message);
    } finally {
      setIsDeleting(false);
    }
  };

  if (!sessionId) {
    return (
      <section className="space-y-4">
        <header className="space-y-1">
          <h1 className="text-2xl font-semibold">Conversation Not Found</h1>
          <p className="text-sm text-muted-foreground">Invalid conversation identifier provided.</p>
        </header>
        <Button variant="outline" onClick={() => router.push("/conversations")}
        >
          Go back
        </Button>
      </section>
    );
  }

  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">{session?.title ?? "Conversation"}</h1>
          <p className="text-sm text-muted-foreground">
            {session
              ? `Created ${new Date(session.created_at).toLocaleString()} • ${session.message_count} messages`
              : "Session metadata is loading"}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" onClick={handleDelete} disabled={isDeleting}>
            {isDeleting ? "Deleting…" : "Delete"}
          </Button>
          <Button variant="outline" asChild>
            <Link href="/conversations">Back to list</Link>
          </Button>
        </div>
      </div>

      {deleteError ? (
        <div className="rounded-lg border bg-destructive/10 p-3 text-sm text-destructive">
          {deleteError}
        </div>
      ) : null}

      <div className="rounded-lg border bg-card p-4">
        <form className="flex flex-col gap-3 sm:flex-row sm:items-end" onSubmit={handleRename}>
          <div className="flex-1 space-y-2">
            <Label htmlFor="rename-title">Conversation title</Label>
            <Input
              id="rename-title"
              value={renameValue}
              onChange={(event) => setRenameValue(event.target.value)}
              disabled={isRenaming}
            />
          </div>
          <Button type="submit" disabled={isRenaming} className="sm:w-auto">
            {isRenaming ? "Saving…" : "Save title"}
          </Button>
        </form>
        {renameError ? <p className="mt-2 text-sm text-destructive">{renameError}</p> : null}
      </div>

      {error ? (
        <div className="rounded-lg border bg-destructive/10 p-4 text-sm text-destructive">
          Failed to load messages: {error.message}
        </div>
      ) : (
        <div className="space-y-3">
          <div className="rounded-lg border bg-card">
            <div className="max-h-[32rem] overflow-y-auto">
              <ul className="space-y-0">
                {isLoading && !messagesData ? (
                  Array.from({ length: 6 }).map((_, index) => (
                    <li key={`message-skeleton-${index}`} className="border-b p-4">
                      <div className="flex items-center justify-between">
                        <span className="h-4 w-24 animate-pulse rounded bg-muted" />
                        <span className="h-3 w-32 animate-pulse rounded bg-muted" />
                      </div>
                      <div className="mt-3 h-4 w-full animate-pulse rounded bg-muted" />
                      <div className="mt-2 h-4 w-3/4 animate-pulse rounded bg-muted" />
                    </li>
                  ))
                ) : messagesData?.messages.length ? (
                  <>
                    {messagesData.messages.map((message) => (
                      <li key={message.id} className="border-b p-4">
                        <div className="flex items-center justify-between text-xs uppercase text-muted-foreground">
                          <span>{message.role}</span>
                          <span>{new Date(message.created_at).toLocaleString()}</span>
                        </div>
                        <p className="mt-2 whitespace-pre-wrap text-sm text-foreground">
                          {message.content}
                        </p>
                      </li>
                    ))}
                    {streamSnapshot ? streamPreview : null}
                  </>
                ) : streamSnapshot ? (
                  streamPreview
                ) : (
                  <li className="p-6 text-sm text-muted-foreground">No messages available yet.</li>
                )}
              </ul>
            </div>
          </div>
          {streamSnapshot || activeStreamWarnings.length > 0 || activeStreamContexts.length > 0 ? (
            <div className="space-y-3">
              {streamSnapshot?.intent ? (
                <div className="rounded-lg border bg-card p-3 text-sm">
                  <p className="font-medium text-muted-foreground">Detected intent</p>
                  <p className="mt-1 text-foreground">
                    {streamSnapshot.intent.intent} · {(streamSnapshot.intent.confidence * 100).toFixed(0)}%
                  </p>
                  {streamSnapshot.intent.reasoning ? (
                    <p className="mt-1 text-muted-foreground">{streamSnapshot.intent.reasoning}</p>
                  ) : null}
                </div>
              ) : null}
              {(streamSnapshot?.strategy || streamSnapshot?.model || streamSnapshot?.subqueries.length) ? (
                <div className="rounded-lg border bg-card p-3 text-sm">
                  <p className="font-medium text-muted-foreground">Run details</p>
                  {streamSnapshot.strategy ? (
                    <p className="mt-1 text-foreground">Strategy: {streamSnapshot.strategy}</p>
                  ) : null}
                  {streamSnapshot.model ? (
                    <p className="mt-1 text-foreground">Model: {streamSnapshot.model}</p>
                  ) : null}
                  {streamSnapshot.subqueries.length ? (
                    <div className="mt-2">
                      <p className="text-xs font-medium text-muted-foreground">Subqueries</p>
                      <ul className="mt-1 space-y-1">
                        {streamSnapshot.subqueries.map((item, index) => (
                          <li key={`${item}-${index}`} className="rounded bg-muted/40 p-2 text-foreground">
                            {item}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                </div>
              ) : null}
              {activeStreamWarnings.length > 0 ? (
                <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
                  <p className="font-medium">Guardrail warnings</p>
                  <ul className="mt-2 list-disc space-y-1 pl-5">
                    {activeStreamWarnings.map((warning) => (
                      <li key={warning}>{warning}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
              {streamSnapshot?.action ? (
                <div className="rounded-lg border bg-card p-3 text-sm">
                  <p className="font-medium text-muted-foreground">Tool invocation</p>
                  <p className="mt-1 text-foreground">{streamSnapshot.action.tool}</p>
                  <p className="mt-1 text-muted-foreground">{streamSnapshot.action.result.detail}</p>
                </div>
              ) : null}
              {activeStreamContexts.length > 0 ? (
                <div className="rounded-lg border bg-card p-3 text-sm">
                  <p className="font-medium text-muted-foreground">Supporting context</p>
                  <ul className="mt-2 space-y-2">
                    {activeStreamContexts.slice(0, 3).map((context, index) => (
                      <li key={`${context.chunk_id ?? index}`} className="rounded border bg-background p-2">
                        <p className="text-xs uppercase text-muted-foreground">
                          {context.source ?? `Source ${index + 1}`} · score {context.score.toFixed(2)}
                        </p>
                        <p className="mt-1 text-sm text-foreground">{context.text}</p>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
          ) : null}
          {hasMore ? (
            <Button variant="outline" onClick={handleLoadMore} disabled={loadingMore}>
              {loadingMore ? "Loading…" : "Load earlier messages"}
            </Button>
          ) : null}
          {loadMoreError ? (
            <p className="text-sm text-destructive">{loadMoreError}</p>
          ) : null}
        </div>
      )}

      <div className="rounded-lg border bg-card p-4">
        <form className="space-y-3" onSubmit={handleSend}>
          <div className="space-y-2">
            <Label htmlFor="message-content">Message</Label>
            <Textarea
              id="message-content"
              placeholder="Write your update or question for the assistant…"
              value={messageContent}
              onChange={(event) => setMessageContent(event.target.value)}
              disabled={isSending || isDeleting}
            />
          </div>
          {sendError ? <p className="text-sm text-destructive">{sendError}</p> : null}
          <div className="flex items-center justify-between">
            <p className="text-xs text-muted-foreground">
              Messages are sent as the current user within the selected tenant context.
            </p>
            <Button type="submit" disabled={isSending || !tenantId}>
              {isStreaming ? "Streaming…" : isSending ? "Sending…" : "Send message"}
            </Button>
          </div>
        </form>
      </div>
    </section>
  );
}
