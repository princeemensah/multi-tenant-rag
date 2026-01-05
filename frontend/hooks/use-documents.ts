"use client";

import { useCallback, useState } from "react";
import useSWR, { type Fetcher, type KeyedMutator } from "swr";

import { useTenant } from "@/hooks/use-tenant";
import { apiClient } from "@/lib/api-client";
import { documentListSchema, type DocumentList } from "@/types/document";

interface UseDocumentsOptions {
  page?: number;
  size?: number;
  status?: string | null;
}

interface UseDocumentsResult {
  data: DocumentList | undefined;
  error: Error | undefined;
  isLoading: boolean;
  isValidating: boolean;
  page: number;
  size: number;
  statusFilter: string | null;
  mutate: KeyedMutator<DocumentList>;
  setPage: (page: number) => void;
  setStatusFilter: (status: string | null) => void;
}

export function useDocuments(
  options: UseDocumentsOptions = {}
): UseDocumentsResult {
  const initialPage = options.page ?? 1;
  const size = options.size ?? 20;
  const { tenantId } = useTenant();
  const [page, setPage] = useState(initialPage);
  const [statusFilter, setStatusFilterState] = useState<string | null>(
    options.status ?? null
  );

  const shouldFetch = Boolean(tenantId);
  type DocumentsKey = ["documents", string, number, number, string | null];

  const fetcher: Fetcher<DocumentList, DocumentsKey> = async ([
    ,
    tenant,
    currentPage,
    currentSize,
    status,
  ]) => {
    const skip = (currentPage - 1) * currentSize;
    const params = new URLSearchParams({
      skip: String(skip),
      limit: String(currentSize),
    });

    if (status) {
      params.set("status_filter", status);
    }

    const { data, error } = await apiClient.get<DocumentList>(
      `/documents?${params.toString()}`,
      { tenantId: tenant }
    );

    if (error || !data) {
      throw new Error(error?.message ?? "Failed to load documents");
    }

    return documentListSchema.parse(data);
  };

  const swr = useSWR<DocumentList, Error>(
    shouldFetch ? ["documents", tenantId as string, page, size, statusFilter] : null,
    fetcher,
    {
      keepPreviousData: true,
      revalidateOnFocus: false,
    }
  );

  const setStatusFilter = useCallback(
    (status: string | null) => {
      setPage(1);
      setStatusFilterState(status);
    },
    []
  );

  return {
    data: swr.data,
    error: (swr.error as Error | undefined) ?? undefined,
    isLoading: swr.isLoading,
    isValidating: swr.isValidating,
    page,
    size,
    statusFilter,
    mutate: swr.mutate,
    setPage,
    setStatusFilter,
  };
}
