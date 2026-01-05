import { z } from "zod";

export const documentSchema = z.object({
  id: z.string(),
  tenant_id: z.string(),
  filename: z.string(),
  original_filename: z.string(),
  content_type: z.string(),
  file_size: z.number(),
  status: z.string(),
  total_chunks: z.number(),
  processed_chunks: z.number(),
  title: z.string().nullable().optional(),
  summary: z.string().nullable().optional(),
  language: z.string(),
  word_count: z.number(),
  collection_name: z.string().nullable().optional(),
  embedding_model: z.string().nullable().optional(),
  doc_metadata: z.record(z.string(), z.unknown()).default({}),
  tags: z.array(z.string()),
  uploaded_at: z.string(),
  processed_at: z.string().nullable().optional(),
  created_at: z.string(),
});

export type Document = z.infer<typeof documentSchema>;

export const documentListSchema = z.object({
  documents: z.array(documentSchema),
  total: z.number(),
  page: z.number(),
  size: z.number(),
  pages: z.number(),
});

export type DocumentList = z.infer<typeof documentListSchema>;
