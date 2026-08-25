export type HealthResponse = { status: string; service: string };
export type DataStatusResponse = { status: string; processed_directory: string; required_files: Record<string, { path: string; exists: boolean }> };

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

async function get<T>(path: string): Promise<T> {
  if (!apiBaseUrl) throw new Error("NEXT_PUBLIC_API_BASE_URL is not configured");
  const response = await fetch(`${apiBaseUrl}${path}`, { headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error(`API request failed: ${response.status}`);
  return response.json() as Promise<T>;
}

export const apiClient = { health: () => get<HealthResponse>("/api/v1/health"), dataStatus: () => get<DataStatusResponse>("/api/v1/data/status") };