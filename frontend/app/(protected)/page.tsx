import { Button } from "@/components/ui/button";
import { env } from "@/lib/env";

interface HealthResponse {
  status: string;
  [key: string]: unknown;
}

interface HealthFetchResult {
  data: HealthResponse | null;
  error: { message: string; details?: unknown } | null;
}

async function fetchHealth(): Promise<HealthFetchResult> {
  const healthUrl = new URL("/health", env.NEXT_PUBLIC_BACKEND_URL).toString();

  try {
    const response = await fetch(healthUrl, { cache: "no-store" });

    if (!response.ok) {
      return {
        data: null,
        error: {
          message: `Request failed with status ${response.status}`,
          details: await response.json().catch(() => null),
        },
      };
    }

    const payload = (await response.json()) as HealthResponse;
    return { data: payload, error: null };
  } catch (error) {
    return {
      data: null,
      error: {
        message: error instanceof Error ? error.message : "Unexpected error",
      },
    };
  }
}

export default async function Home() {
  const { data, error } = await fetchHealth();

  const status = data?.status ?? "unreachable";
  const isHealthy = status.toLowerCase() === "healthy";

  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 p-6">
      <div className="flex flex-col items-center gap-2 text-center">
        <h1 className="text-3xl font-semibold">AI Operations Assistant</h1>
        <p className="text-muted-foreground">
          Multi-tenant RAG control plane bridging the FastAPI backend with a modern operator console.
        </p>
      </div>
      <div className="w-full max-w-md rounded-lg border bg-card p-6 shadow-sm">
        <h2 className="text-lg font-medium">Backend Health</h2>
        <p className={`mt-2 text-sm ${isHealthy ? "text-emerald-600" : "text-destructive"}`}>
          Status: {status}
        </p>
        {error ? (
          <p className="mt-2 text-sm text-muted-foreground">
            Error: {error.message}
            {error.details ? ` (${JSON.stringify(error.details)})` : ""}
          </p>
        ) : null}
        {data ? (
          <pre className="mt-4 max-h-48 overflow-auto rounded-md bg-muted p-3 text-xs text-muted-foreground">
            {JSON.stringify(data, null, 2)}
          </pre>
        ) : null}
      </div>
      <Button asChild>
        <a href="/docs" aria-label="View API documentation">
          View API docs
        </a>
      </Button>
    </main>
  );
}
