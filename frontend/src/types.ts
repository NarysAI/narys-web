export type Package = {
  id: string
  path: string
  name: string
  description: string
  source_url: string
  web_url?: string
  category: string
  status: string
  entry_type?: 'package' | 'project'
  access?: 'public' | 'private'
  canonical_repo_url?: string
  contribution_url?: string
  issues_url?: string
  default_branch?: string
  current_drawing?: string
  pub_url?: string
  namespace?: string
  visibility?: 'public' | 'private'
  repository?: 'PUB' | 'indra' | 'git'
  git_commit?: string
  upstream_url?: string
  license_status?: string
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
  semantic_path: string
  license?: string
  namespace?: string
  visibility?: 'public' | 'private'
  repository?: 'PUB' | 'indra'
  git_path?: string
  git_commit?: string
  upstream_url?: string
  checksum?: string
  size?: number
  license_status?: string
  model_role?: 'electronic_component' | 'mechanical_component' | 'printable_part'
  entry_type?: 'package' | 'project'
  canonical_repo_url?: string
  default_branch?: string
  parameters?: Record<string, {
    type: 'float' | 'int' | 'bool' | 'str' | 'string'
    default: number | boolean | string
    min?: number
    max?: number
    step?: number
    hidden?: boolean
    options?: number[]
  }>
  parameter_presets?: Array<{
    id: string
    label: string
    parameters: Record<string, number | boolean | string>
  }>
  default_parameter_preset?: string
  product_family?: {
    id: string
    name: string
  }
  product_variant?: {
    id: string
    name: string
    kind: string
    revision: string
  }
  base_variant?: ProductObjectReference
  components?: ProductComponent[]
  compatibility_aliases?: ProductObjectReference[]
  representations?: ModelRepresentation[]
}

export type ProductObjectReference = {
  kind: 'part' | 'assembly' | 'sketch'
  semantic_path: string
  label: string
}

export type ProductComponent = {
  label: string
  quantity: number | string
  role: string
  modeled: boolean
  kind?: 'part' | 'assembly' | 'sketch'
  semantic_path?: string
}

export type ModelRepresentation = {
  format: 'scad' | 'stl' | 'step'
  path: string
  geometry_scope: 'exterior' | 'interior'
  label: string
  primary: boolean
  components: Array<ProductObjectReference & { identifier: string }>
}

export type Principal = { key_id: string; name: string; role: 'user' | 'admin' }

export type Catalog = {
  name: string
  package_count: number
  object_count: number
  categories: { name: string; packages: Package[] }[]
  featured: CatalogObject[]
}
