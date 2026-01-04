"use client";

import { useState, useEffect, FormEvent, ChangeEvent } from "react";
import { useRouter } from "next/navigation";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { apiClient } from "@/lib/api-client";
import { tokenResponseSchema } from "@/types/auth";
import { useAuth } from "@/hooks/use-auth";

const loginSchema = z.object({
  email: z.string().email({ message: "Enter a valid email" }),
  password: z.string().min(8, { message: "Password must be at least 8 characters" }),
  tenant_identifier: z.string().optional(),
});

type LoginValues = z.infer<typeof loginSchema>;

interface LoginFormProps {
  redirectTo?: string;
}

export function LoginForm({ redirectTo = "/" }: LoginFormProps) {
  const router = useRouter();
  const { saveSession, isAuthenticated, loading } = useAuth();
  const [values, setValues] = useState<LoginValues>({
    email: "",
    password: "",
    tenant_identifier: "",
  });
  const [errors, setErrors] = useState<Partial<Record<keyof LoginValues, string>>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSuccess, setIsSuccess] = useState(false);

  useEffect(() => {
    if (!loading && isAuthenticated) {
      router.replace(redirectTo);
    }
  }, [isAuthenticated, loading, redirectTo, router]);

  const handleChange = (field: keyof LoginValues) =>
    (event: ChangeEvent<HTMLInputElement>) => {
      setValues((current) => ({ ...current, [field]: event.target.value }));
      setErrors((current) => ({ ...current, [field]: undefined }));
      setFormError(null);
      setIsSuccess(false);
    };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setIsSubmitting(true);
    setFormError(null);
    setIsSuccess(false);

    const parsed = loginSchema.safeParse({
      ...values,
      tenant_identifier: values.tenant_identifier?.trim() || undefined,
    });

    if (!parsed.success) {
      const fieldErrors: Partial<Record<keyof LoginValues, string>> = {};
      parsed.error.issues.forEach((issue) => {
        const field = issue.path[0] as keyof LoginValues;
        fieldErrors[field] = issue.message;
      });
      setErrors(fieldErrors);
      setIsSubmitting(false);
      return;
    }

    const { data, error } = await apiClient.post("/auth/login", {
      body: parsed.data,
    });

    if (error || !data) {
      setFormError(error?.message ?? "Unable to log in");
      setIsSubmitting(false);
      return;
    }

    const tokenResult = tokenResponseSchema.safeParse(data);
    if (!tokenResult.success) {
      setFormError("Unexpected response from server");
      setIsSubmitting(false);
      return;
    }

    saveSession(tokenResult.data);

    setIsSuccess(true);
    setIsSubmitting(false);
    router.push(redirectTo);
  };

  return (
    <form className="space-y-6" onSubmit={handleSubmit} noValidate>
      <div className="space-y-2">
        <Label htmlFor="email">Email</Label>
        <Input
          id="email"
          type="email"
          autoComplete="email"
          value={values.email}
          onChange={handleChange("email")}
          required
        />
        {errors.email ? <p className="text-sm text-destructive">{errors.email}</p> : null}
      </div>

      <div className="space-y-2">
        <Label htmlFor="password">Password</Label>
        <Input
          id="password"
          type="password"
          autoComplete="current-password"
          value={values.password}
          onChange={handleChange("password")}
          required
        />
        {errors.password ? <p className="text-sm text-destructive">{errors.password}</p> : null}
      </div>

      <div className="space-y-2">
        <Label htmlFor="tenant">Tenant Identifier</Label>
        <Input
          id="tenant"
          placeholder="subdomain or tenant ID"
          value={values.tenant_identifier}
          onChange={handleChange("tenant_identifier")}
        />
        <p className="text-xs text-muted-foreground">
          Optional: provide your tenant subdomain or ID if multiple tenants share the same email.
        </p>
        {errors.tenant_identifier ? (
          <p className="text-sm text-destructive">{errors.tenant_identifier}</p>
        ) : null}
      </div>

      {formError ? <p className="text-sm text-destructive">{formError}</p> : null}
      {isSuccess ? (
        <p className="text-sm text-emerald-600">Authenticated successfully. Redirecting…</p>
      ) : null}

      <Button type="submit" className="w-full" disabled={isSubmitting}>
        {isSubmitting ? "Signing in…" : "Sign in"}
      </Button>
    </form>
  );
}
