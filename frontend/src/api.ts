import type { Catalog, CatalogObject, Package, Principal } from "./types";

export const API = import.meta.env.VITE_API_URL || "";
let apiKey = "";
export const setApiKey = (value: string) => {
  apiKey = value;
};
export async function authorizedBlobUrl(path: string): Promise<string> {
  const headers = new Headers();
  if (apiKey) headers.set("Authorization", `Bearer ${apiKey}`);
  const response = await fetch(`${API}${path}`, { headers });
  if (!response.ok)
    throw new Error("Не вдалося завантажити захищений перегляд");
  return URL.createObjectURL(await response.blob());
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const headers = new Headers(options?.headers);
  if (apiKey) headers.set("Authorization", `Bearer ${apiKey}`);
  if (options?.body && !headers.has("Content-Type"))
    headers.set("Content-Type", "application/json");
  const response = await fetch(`${API}${path}`, { ...options, headers });
  if (!response.ok) {
    const payload = await response
      .json()
      .catch(() => ({ detail: response.statusText }));
    throw new Error(payload.detail || "Не вдалося отримати дані");
  }
  return response.json() as Promise<T>;
}

export const getCatalog = () => request<Catalog>("/api/v1/catalog");
export const getObject = (id: string) =>
  request<CatalogObject>(`/api/v1/objects/${id}`);
export const getObjectByPath = (kind: string, path: string) =>
  request<CatalogObject>(`/api/v1/by-path/${kind}/${encodeURI(path)}`);
export const getPackage = (id: string) =>
  request<Package & { objects: CatalogObject[] }>(`/api/v1/packages/${id}`);
export const search = (query: string) =>
  request<{ results: ((Package | CatalogObject) & { result_type: string })[] }>(
    `/api/v1/search?q=${encodeURIComponent(query)}`,
  );
export const refresh = () =>
  request<{ status: string }>("/api/v1/catalog/refresh", { method: "POST" });
export const authenticate = (key: string) => {
  setApiKey(key);
  return request<Principal>("/api/v1/auth/me");
};
export const createDownloadTicket = (objectId: string) =>
  request<{ ticket: string; expires_in: number }>("/api/v1/download-tickets", {
    method: "POST",
    body: JSON.stringify({ object_id: objectId }),
  });
export const getAdminKeys = () =>
  request<{
    keys: Array<{
      key_id: string;
      name: string;
      role: string;
      created_at: number;
      revoked_at?: number;
    }>;
  }>("/api/v1/admin/keys");
export const createAdminKey = (name: string, role: "user" | "admin") =>
  request<{ key: string; key_id: string; name: string; role: string }>(
    "/api/v1/admin/keys",
    { method: "POST", body: JSON.stringify({ name, role }) },
  );
export const revokeAdminKey = (keyId: string) =>
  request<{ status: string }>(`/api/v1/admin/keys/${keyId}/revoke`, {
    method: "POST",
  });
export const getAudit = () =>
  request<{ entries: Array<Record<string, string | number>> }>(
    "/api/v1/admin/audit",
  );
export const getAdminSyncRuns = () =>
  request<{ runs: Array<Record<string, string | number>> }>(
    "/api/v1/admin/sync-runs",
  );
