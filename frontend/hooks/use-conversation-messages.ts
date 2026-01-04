"use client";

import useSWR, { type KeyedMutator } from "swr";

import { apiClient } from "@/lib/api-client";
import {
  conversationMessageListSchema,
  type ConversationMessageList,
} from "@/types/conversation";
import { useTenant } from "@/hooks/use-tenant";

interface UseConversationMessagesOptions {
  sessionId: string;
  limit?: number;
}

interface UseConversationMessagesResult {
  data: ConversationMessageList | undefined;
  error: Error | undefined;
  isLoading: boolean;
  isValidating: boolean;
  mutate: KeyedMutator<ConversationMessageList>;
  fetchMore: () => Promise<void>;
  hasMore: boolean;
}

export function useConversationMessages({
  sessionId,
  limit = 50,
}: UseConversationMessagesOptions): UseConversationMessagesResult {
  const { tenantId } = useTenant();

  const swr = useSWR<ConversationMessageList>(
    tenantId ? ["conversation-messages", tenantId, sessionId, limit] : null,
    async ([, tenant, id, pageSize]) => {
      const { data, error } = await apiClient.get<ConversationMessageList>(
        `/conversations/${id}/messages?limit=${pageSize}`,
        { tenantId: tenant as string }
      );

      if (error || !data) {
        throw new Error(error?.message ?? "Failed to load conversation messages");
      }

      return conversationMessageListSchema.parse(data);
    },
    {
      keepPreviousData: true,
      revalidateOnFocus: false,
    }
  );

  const fetchMore = async () => {
    if (!swr.data?.next_before) {
      return;
    }

    const { data, error } = await apiClient.get<ConversationMessageList>(
      `/conversations/${sessionId}/messages?limit=${limit}&before_sequence=${swr.data.next_before}`,
      { tenantId: tenantId ?? undefined }
    );

    if (error || !data) {
      throw new Error(error?.message ?? "Failed to load more messages");
    }

    const parsed = conversationMessageListSchema.parse(data);
    swr.mutate((current) => {
      if (!current) {
        return parsed;
      }

      return {
        ...parsed,
        messages: [...current.messages, ...parsed.messages],
      };
    }, false);
  };

  return {
    data: swr.data,
    error: (swr.error as Error | undefined) ?? undefined,
    isLoading: swr.isLoading,
    isValidating: swr.isValidating,
    mutate: swr.mutate,
    fetchMore,
    hasMore: Boolean(swr.data?.next_before),
  };
}
