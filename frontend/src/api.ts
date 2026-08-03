import type { Catalog, CatalogObject, Package } from './types'

export const API = import.meta.env.VITE_API_URL || 'http://localhost:8001'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, options)
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: response.statusText }))
    throw new Error(payload.detail || 'Не вдалося отримати дані')
  }
  return response.json() as Promise<T>
}

export const getCatalog = () => request<Catalog>('/api/v1/catalog')
export const getObject = (id: string) => request<CatalogObject>(`/api/v1/objects/${id}`)
export const getPackage = (id: string) => request<Package & { objects: CatalogObject[] }>(`/api/v1/packages/${id}`)
export const search = (query: string) => request<{ results: ((Package | CatalogObject) & { result_type: string })[] }>(`/api/v1/search?q=${encodeURIComponent(query)}`)
export const refresh = () => request<{ status: string }>('/api/v1/catalog/refresh', { method: 'POST' })
