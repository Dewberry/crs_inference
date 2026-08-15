import { useQuery } from "@tanstack/react-query";

async function fetchHealth(): Promise<{ status: string }> {
  const res = await fetch("/api/health");
  if (!res.ok) throw new Error(`API responded ${res.status}`);
  return res.json();
}

export default function App() {
  const health = useQuery({ queryKey: ["health"], queryFn: fetchHealth });

  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="border-b px-8 py-4">
        <h1 className="text-2xl font-semibold tracking-tight">CRS Finder</h1>
        <p className="text-sm text-muted-foreground mt-0.5">
          Identify the coordinate reference system that best places your geometry into a target dataset.
        </p>
      </header>

      <main className="px-8 py-10 max-w-3xl">
        <p className="text-muted-foreground text-sm">
          Application skeleton — upload form and results will appear here.
        </p>
      </main>

      {/* Dev-only connectivity indicator */}
      <div className="fixed bottom-3 right-4 text-xs text-muted-foreground">
        API:{" "}
        {health.isLoading
          ? "checking…"
          : health.isError
            ? "unavailable"
            : health.data?.status}
      </div>
    </div>
  );
}
