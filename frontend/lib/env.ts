import "dotenv/config";
import { createEnv } from "@t3-oss/env-nextjs";
import { z } from "zod";

export const env = createEnv({
  server: {
    NODE_ENV: z.enum(["development", "test", "production"]).default("development"),
    BACKEND_SERVICE_SECRET: z.string().min(1).optional(),
  },
  client: {
    NEXT_PUBLIC_BACKEND_URL: z.string().url().default("http://localhost:8000"),
  },
  experimental__runtimeEnv: {
    NEXT_PUBLIC_BACKEND_URL: process.env.NEXT_PUBLIC_BACKEND_URL,
  },
});
