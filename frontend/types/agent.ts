import { z } from "zod";

export const agentGuardrailSchema = z.object({
  warnings: z.array(z.string()).default([]),
  has_warnings: z.boolean().default(false),
  info: z.record(z.string(), z.any()).default({}),
});

export type AgentGuardrail = z.infer<typeof agentGuardrailSchema>;

export const agentIntentSchema = z.object({
  intent: z.string(),
  confidence: z.number().min(0).max(1),
  reasoning: z.string().optional(),
  entities: z.array(z.string()).default([]),
  requested_action: z.string().nullable().optional(),
  raw_response: z.string().nullable().optional(),
});

export type AgentIntent = z.infer<typeof agentIntentSchema>;

export const agentContextSchema = z.object({
  chunk_id: z.string().nullable().optional(),
  document_id: z.string().nullable().optional(),
  score: z.number().default(0),
  text: z.string(),
  source: z.string().nullable().optional(),
});

export type AgentContext = z.infer<typeof agentContextSchema>;

export const agentToolResultSchema = z.object({
  status: z.string(),
  detail: z.string(),
  data: z.record(z.string(), z.any()).default({}),
});

export const agentActionSchema = z.object({
  tool: z.string(),
  arguments: z.record(z.string(), z.any()).default({}),
  result: agentToolResultSchema,
});

export type AgentAction = z.infer<typeof agentActionSchema>;

export const agentStreamEventSchema = z.discriminatedUnion("type", [
  z.object({
    type: z.literal("status"),
    state: z.string(),
    session_id: z.string().optional(),
    conversation_turn: z.number().optional(),
  }),
  z.object({
    type: z.literal("intent"),
    intent: agentIntentSchema,
    session_id: z.string().optional(),
  }),
  z.object({
    type: z.literal("contexts"),
    contexts: z.array(agentContextSchema),
    session_id: z.string().optional(),
  }),
  z.object({
    type: z.literal("action"),
    action: agentActionSchema,
    session_id: z.string().optional(),
  }),
  z.object({
    type: z.literal("answer"),
    text: z.string(),
    strategy: z.string().optional(),
    subqueries: z.array(z.string()).optional(),
    model: z.string().nullable().optional(),
    guardrails: agentGuardrailSchema.optional(),
    session_id: z.string().optional(),
  }),
  z.object({
    type: z.literal("done"),
    session_id: z.string().optional(),
  }),
  z.object({
    type: z.literal("error"),
    message: z.string(),
    session_id: z.string().optional(),
  }),
]);

export type AgentStreamEvent = z.infer<typeof agentStreamEventSchema>;
