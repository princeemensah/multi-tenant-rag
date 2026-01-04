import { z } from "zod";

export const conversationSessionSchema = z.object({
  id: z.string(),
  tenant_id: z.string(),
  created_by_id: z.string().nullable().optional(),
  title: z.string(),
  message_count: z.number(),
  created_at: z.string(),
  updated_at: z.string().nullable().optional(),
});

export type ConversationSession = z.infer<typeof conversationSessionSchema>;

export const conversationSessionListSchema = z.object({
  sessions: z.array(conversationSessionSchema),
  total: z.number(),
  page: z.number(),
  size: z.number(),
  pages: z.number(),
});

export type ConversationSessionList = z.infer<typeof conversationSessionListSchema>;

export const conversationMessageSchema = z.object({
  id: z.string(),
  conversation_id: z.string(),
  tenant_id: z.string(),
  author_id: z.string().nullable().optional(),
  role: z.string(),
  content: z.string(),
  metadata: z.record(z.string(), z.unknown()).default({}),
  sequence: z.number(),
  created_at: z.string(),
});

export type ConversationMessage = z.infer<typeof conversationMessageSchema>;

export const conversationMessageListSchema = z.object({
  session_id: z.string(),
  messages: z.array(conversationMessageSchema),
  remaining: z.number().nullable().optional(),
  next_before: z.number().nullable().optional(),
});

export type ConversationMessageList = z.infer<typeof conversationMessageListSchema>;
