export async function apiJson<T = any>(
  url: string,
  init?: RequestInit,
  timeoutMs = 35000
): Promise<T> {
  const method = (init?.method || "GET").toUpperCase();

  async function attempt(): Promise<T> {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), timeoutMs);
    try {
      const res = await fetch(url, { ...init, signal: ctrl.signal });
      const raw = await res.text();
      let data: any = null;
      if (raw) {
        try {
          data = JSON.parse(raw);
        } catch {
          data = null;
        }
      }
      if (!res.ok) {
        const msg =
          data?.detail ||
          data?.message ||
          `HTTP ${res.status}: ${(raw || res.statusText).slice(0, 140)}`;
        throw new Error(msg);
      }
      if (data === null && raw) {
        throw new Error(`Invalid JSON response from ${url}`);
      }
      return data as T;
    } catch (err: any) {
      if (err?.name === "AbortError") {
        throw new Error(`Request timed out after ${Math.round(timeoutMs / 1000)}s`);
      }
      throw err;
    } finally {
      clearTimeout(timer);
    }
  }

  try {
    return await attempt();
  } catch (err: any) {
    if (method === "GET" && err instanceof TypeError) {
      await new Promise((r) => setTimeout(r, 600));
      return await attempt();
    }
    throw err;
  }
}
