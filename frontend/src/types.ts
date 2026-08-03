export type Package = {
  id: string
  path: string
  name: string
  description: string
  source_url: string
  web_url?: string
  category: string
  status: string
}

export type CatalogObject = {
  id: string
  package_id: string
  package_path: string
  name: string
  kind: 'part' | 'assembly' | 'sketch'
  description: string
  source_type: string
  source_path?: string
  source_url: string
  license?: string
}

export type Catalog = {
  name: string
  package_count: number
  object_count: number
  categories: { name: string; packages: Package[] }[]
  featured: CatalogObject[]
}
