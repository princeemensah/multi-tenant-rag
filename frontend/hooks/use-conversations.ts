"use client";

import { useState } from "react";
import useSWR, { type Fetcher, type KeyedMutator } from "swr";

import { useTenant } from "@/hooks/use-tenant";
import { apiClient } from "@/lib/api-client";
import {
  conversationSessionListSchema,
  type ConversationSessionList,
} from "@/types/conversation";

interface UseConversationsOptions {
  page?: number;
  size?: number;
}

interface UseConversationsResult {
  data: ConversationSessionList | undefined;
  error: Error | undefined;
  isLoading: boolean;
  isValidating: boolean;
  page: number;
  size: number;
  mutate: KeyedMutator<ConversationSessionList>;
  setPage: (page: number) => void;
}

export function useConversations(
  options: UseConversationsOptions = {}
): UseConversationsResult {
  const initialPage = options.page ?? 1;
  const size = options.size ?? 20;
  const { tenantId } = useTenant();
  const [page, setPage] = useState(initialPage);

  const shouldFetch = Boolean(tenantId);
  type ConversationsKey = ["conversations", string, number, number];

  const fetcher: Fetcher<ConversationSessionList, ConversationsKey> = async ([
    ,
    tenant,
    currentPage,
    currentSize,
  ]) => {
    const skip = (currentPage - 1) * currentSize;
    const { data, error } = await apiClient.get<ConversationSessionList>(
      `/conversations?skip=${skip}&limit=${currentSize}`,
      { tenantId: tenant }
    );

    if (error || !data) {
      throw new Error(error?.message ?? "Failed to load conversations");
    }

    const parsed = conversationSessionListSchema.parse(data);
    return parsed;
  };

  const swr = useSWR<ConversationSessionList, Error>(
    shouldFetch ? ["conversations", tenantId as string, page, size] : null,
    fetcher,
    {
      keepPreviousData: true,
      revalidateOnFocus: false,
    }
  );

  return {
    data: swr.data,
    error: (swr.error as Error | undefined) ?? undefined,
    isLoading: swr.isLoading,
    isValidating: swr.isValidating,
    page,
    size,
    mutate: swr.mutate,
    setPage,
  };
}
