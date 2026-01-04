"use client";

import {
  useMemo,
  useState,
  type ChangeEvent,
  type FormEvent,
} from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useDocuments } from "@/hooks/use-documents";
import { useTenant } from "@/hooks/use-tenant";
import { apiClient } from "@/lib/api-client";

const STATUS_OPTIONS: Array<{ value: string | null; label: string }> = [
  { value: null, label: "All statuses" },
  { value: "uploaded", label: "Uploaded" },
  { value: "processing", label: "Processing" },
  { value: "processed", label: "Processed" },
  { value: "failed", label: "Failed" },
];

function formatBytes(size: number): string {
  if (!Number.isFinite(size) || size <= 0) {
    return "0 B";
  }
  const units = ["B", "KB", "MB", "GB"];
  const exponent = Math.min(Math.floor(Math.log(size) / Math.log(1024)), units.length - 1);
  const value = size / Math.pow(1024, exponent);
  return `${value.toFixed(value >= 10 || exponent === 0 ? 0 : 1)} ${units[exponent]}`;
}

export default function DocumentsPage() {
  const { tenant, tenantId } = useTenant();
  const {
    data,
    error,
    isLoading,
    isValidating,
    page,
    size,
    statusFilter,
    mutate,
    setPage,
    setStatusFilter,
  } = useDocuments();

  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [tags, setTags] = useState("");
  const [metadata, setMetadata] = useState("");
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadSuccess, setUploadSuccess] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const documents = data?.documents ?? [];
  const totalPages = data?.pages ?? 1;

  const subtitle = useMemo(() => {
    if (!tenantId) {
      return "Select a tenant to review uploaded knowledge bases.";
    }
    if (isLoading && !data) {
      return `Loading documents for ${tenant?.name ?? "your tenant"}…`;
    }
    return `Managing ${data?.total ?? 0} documents for ${tenant?.name ?? "this tenant"}.`;
  }, [tenantId, isLoading, data, tenant]);

  const canGoPrev = page > 1;
  const canGoNext = page < totalPages;

  const handleFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    const selected = event.target.files?.[0] ?? null;
    setFile(selected);
  };

  const handleUpload = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!tenantId) {
      setUploadError("Select a tenant before uploading documents.");
      return;
    }
    if (!file) {
      setUploadError("Choose a file to upload.");
      return;
    }

    let parsedMetadata: Record<string, unknown> | undefined;
    if (metadata.trim()) {
      try {
        parsedMetadata = JSON.parse(metadata);
        if (parsedMetadata === null || typeof parsedMetadata !== "object" || Array.isArray(parsedMetadata)) {
          throw new Error("Metadata must be a JSON object");
        }
      } catch (metaError) {
        const message = metaError instanceof Error ? metaError.message : "Invalid metadata payload";
        setUploadError(message);
        return;
      }
    }

    const tagValues = tags
      .split(",")
      .map((value) => value.trim())
      .filter(Boolean);

    const payload = new FormData();
    payload.append("file", file);
    if (title.trim()) {
      payload.append("title", title.trim());
    }
    if (tagValues.length > 0) {
      payload.append("tags", JSON.stringify(tagValues));
    }
    if (parsedMetadata) {
      payload.append("metadata", JSON.stringify(parsedMetadata));
    }

    try {
      setIsUploading(true);
      setUploadError(null);
      setUploadSuccess(null);
      const { data: created, error: uploadErr } = await apiClient.post(
        "/documents/upload",
        {
          body: payload,
          tenantId,
        }
      );

      if (uploadErr) {
        throw new Error(uploadErr.message || "Failed to upload document");
      }

      if (!created) {
        throw new Error("Upload succeeded but no document returned");
      }

      setUploadSuccess("Document upload queued for processing.");
      setFile(null);
      setTitle("");
      setTags("");
      setMetadata("");
      setPage(1);
      await mutate();
    } catch (submitError) {
      const message =
        submitError instanceof Error ? submitError.message : "Unexpected upload error";
      setUploadError(message);
    } finally {
      setIsUploading(false);
    }
  };

  const handleDelete = async (documentId: string) => {
    if (!tenantId) {
      setDeleteError("Select a tenant before deleting documents.");
      return;
    }

    try {
      setDeletingId(documentId);
      setDeleteError(null);
      const { error: deleteErr } = await apiClient.delete(`/documents/${documentId}`, {
        tenantId,
      });

      if (deleteErr) {
        throw new Error(deleteErr.message || "Failed to delete document");
      }

      await mutate();
    } catch (actionError) {
      const message =
        actionError instanceof Error ? actionError.message : "Unexpected delete error";
      setDeleteError(message);
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <section className="space-y-4">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold">Documents</h1>
        <p className="text-sm text-muted-foreground">{subtitle}</p>
      </header>

      <div className="rounded-lg border bg-card p-4">
        <form className="grid gap-4 md:grid-cols-2" onSubmit={handleUpload}>
          <div className="space-y-2">
            <Label htmlFor="document-file">Attach file</Label>
            <Input
              id="document-file"
              type="file"
              accept=".pdf,.txt,.md,.docx"
              onChange={handleFileChange}
              disabled={!tenantId || isUploading}
            />
            <p className="text-xs text-muted-foreground">
              Supported formats: PDF, DOCX, Markdown, and plain text (max 25 MB).
            </p>
          </div>

          <div className="space-y-2">
            <Label htmlFor="document-title">Title (optional)</Label>
            <Input
              id="document-title"
              placeholder="e.g. On-call handbook"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              disabled={!tenantId || isUploading}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="document-tags">Tags (comma separated)</Label>
            <Input
              id="document-tags"
              placeholder="runbooks, onboarding, compliance"
              value={tags}
              onChange={(event) => setTags(event.target.value)}
              disabled={!tenantId || isUploading}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="document-metadata">Metadata JSON (optional)</Label>
            <Textarea
              id="document-metadata"
              rows={4}
              placeholder='{"document_type": "runbook", "created_at": "2024-01-15"}'
              value={metadata}
              onChange={(event) => setMetadata(event.target.value)}
              disabled={!tenantId || isUploading}
            />
          </div>

          <div className="md:col-span-2 flex items-center gap-2">
            <Button type="submit" disabled={!tenantId || isUploading}>
              {isUploading ? "Uploading…" : "Upload document"}
            </Button>
            {uploadError ? (
              <span className="text-sm text-destructive">{uploadError}</span>
            ) : null}
            {uploadSuccess ? (
              <span className="text-sm text-emerald-600">{uploadSuccess}</span>
            ) : null}
            {!tenantId ? (
              <span className="text-xs text-muted-foreground">
                Choose a tenant to enable uploads.
              </span>
            ) : null}
          </div>
        </form>
      </div>

      {!tenantId ? (
        <div className="rounded-lg border border-dashed bg-card p-6 text-sm text-muted-foreground">
          Use the tenant switcher above to choose an organization context.
        </div>
      ) : error ? (
        <div className="rounded-lg border bg-destructive/10 p-4 text-sm text-destructive">
          Failed to load documents: {error.message}
        </div>
      ) : (
        <div className="rounded-lg border bg-card">
          <div className="flex flex-col gap-3 border-b px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="text-xs text-muted-foreground">
              Page {page} of {totalPages}
              {isValidating ? " • Refreshing…" : ""}
            </div>
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
              <label className="flex items-center gap-2 text-xs text-muted-foreground">
                Status
                <select
                  className="h-8 rounded border bg-background px-2 text-sm"
                  value={statusFilter ?? ""}
                  onChange={(event) =>
                    setStatusFilter(event.target.value ? event.target.value : null)
                  }
                  disabled={isLoading && !data}
                >
                  {STATUS_OPTIONS.map((option) => (
                    <option key={option.label} value={option.value ?? ""}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={!canGoPrev}
                  onClick={() => canGoPrev && setPage(page - 1)}
                >
                  Previous
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={!canGoNext}
                  onClick={() => canGoNext && setPage(page + 1)}
                >
                  Next
                </Button>
              </div>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full min-w-[40rem] table-fixed">
              <thead>
                <tr className="border-b bg-muted/40 text-left text-xs uppercase text-muted-foreground">
                  <th className="px-4 py-3 font-medium">Title</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 font-medium">Tags</th>
                  <th className="px-4 py-3 font-medium">Uploaded</th>
                  <th className="px-4 py-3 font-medium">Size</th>
                  <th className="px-4 py-3 font-medium">Chunks</th>
                  <th className="px-4 py-3 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {isLoading && !data ? (
                  Array.from({ length: 3 }).map((_, index) => (
                    <tr key={`skeleton-${index}`} className="animate-pulse border-b">
                      <td className="px-4 py-4">
                        <div className="h-4 w-3/4 rounded bg-muted" />
                      </td>
                      <td className="px-4 py-4">
                        <div className="h-4 w-16 rounded bg-muted" />
                      </td>
                      <td className="px-4 py-4">
                        <div className="h-4 w-24 rounded bg-muted" />
                      </td>
                      <td className="px-4 py-4">
                        <div className="h-4 w-24 rounded bg-muted" />
                      </td>
                      <td className="px-4 py-4">
                        <div className="h-4 w-16 rounded bg-muted" />
                      </td>
                      <td className="px-4 py-4">
                        <div className="h-4 w-12 rounded bg-muted" />
                      </td>
                      <td className="px-4 py-4">
                        <div className="h-8 w-20 rounded bg-muted" />
                      </td>
                    </tr>
                  ))
                ) : documents.length === 0 ? (
                  <tr>
                    <td className="px-4 py-6 text-sm text-muted-foreground" colSpan={7}>
                      No documents uploaded yet.
                    </td>
                  </tr>
                ) : (
                  documents.map((document) => (
                    <tr key={document.id} className="border-b last:border-b-0">
                      <td className="px-4 py-3 text-sm font-medium text-foreground">
                        {document.title || document.original_filename}
                      </td>
                      <td className="px-4 py-3 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                        {document.status}
                      </td>
                      <td className="px-4 py-3 text-sm text-muted-foreground">
                        {document.tags.length > 0 ? document.tags.join(", ") : "—"}
                      </td>
                      <td className="px-4 py-3 text-sm text-muted-foreground">
                        {new Date(document.uploaded_at).toLocaleString()}
                      </td>
                      <td className="px-4 py-3 text-sm text-muted-foreground">
                        {formatBytes(document.file_size)}
                      </td>
                      <td className="px-4 py-3 text-sm text-muted-foreground">
                        {document.total_chunks}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <Button
                          variant="outline"
                          size="sm"
                          className="text-destructive hover:text-destructive"
                          disabled={deletingId === document.id}
                          onClick={() => handleDelete(document.id)}
                        >
                          {deletingId === document.id ? "Deleting…" : "Delete"}
                        </Button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
          {deleteError ? (
            <div className="border-t px-4 py-2 text-sm text-destructive">{deleteError}</div>
          ) : null}
        </div>
      )}
    </section>
  );
}
