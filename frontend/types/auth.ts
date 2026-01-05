import { z } from "zod";

export const userSchema = z.object({
  id: z.string(),
  email: z.string().email(),
  username: z.string(),
  role: z.string(),
  is_active: z.boolean().default(true),
  created_at: z.string().nullable().optional(),
});

export type User = z.infer<typeof userSchema>;

export const tenantSchema = z.object({
  id: z.string(),
  name: z.string(),
  subdomain: z.string().nullable().optional(),
  llm_provider: z.string().nullable().optional(),
  llm_model: z.string().nullable().optional(),
  is_active: z.boolean().default(true),
  created_at: z.string().nullable().optional(),
});

export type Tenant = z.infer<typeof tenantSchema>;

export const tokenResponseSchema = z.object({
  access_token: z.string(),
  token_type: z.string(),
  expires_in: z.number(),
  user: userSchema.nullable().optional(),
  tenant: tenantSchema.nullable().optional(),
});

export type TokenResponse = z.infer<typeof tokenResponseSchema>;
