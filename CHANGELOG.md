# Changelog

## [0.4.1] - 2026-08-10

### Added

- Mechanical component roles so internal assemblies can link housings, covers,
  fasteners, and vibration isolators as exact catalog records.

### Fixed

- Present corrected H30 Enclosed revision 1.1 composition and preserve exact
  revision selection when preview assets are cached.
- Use the CAD Z axis as up in the 3D viewer so enclosure ports, covers, and
  mounting hardware appear in their intended orientation.

## [0.4.0] - 2026-08-10

### Added

- Product-family metadata with exact variants, independent revisions, base
  variants, BOM components, and compatibility aliases.
- Variant and BOM panels on object pages with direct links to exact referenced
  components.
- Multi-format representations: SCAD/STL exterior geometry and STEP interior
  structure on one exact variant page.
- STEP component identifiers, exact catalog links, format downloads, and
  server-side representation validation.

### Changed

- Object cards and headings use the human-readable exact variant name when
  product metadata is available.
- Legacy semantic paths resolve to their canonical exact variant and the
  browser replaces the old URL with the canonical route.

## [0.3.3] - 2026-08-10

### Fixed

- Hide package-only navigation containers and empty package records from the
  public catalog, search results and direct package pages while retaining their
  populated descendants.
- Remove the legacy preview special case that existed only for the retired
  `std/metric/m` slot sketches.

## [0.3.2] - 2026-08-10

### Fixed

- Expose finite, validated OpenSCAD parameter choices and size presets without
  leaking the full PartCAD object specification.
- Render selected dimensions through safe OpenSCAD `-D` arguments and cache
  each canonical configuration separately.
- Add an apply/reset configurator to object pages so parametric parts are no
  longer limited to their single source-code default.

### Security

- Reject duplicate, unknown, out-of-range and undeclared preview values.
- Limit public configurations to explicit finite option sets and serialize
  OpenSCAD preview generation to avoid duplicate concurrent renders.

## [0.3.1] - 2026-08-10

### Fixed

- Generate thin GLB previews directly for source-free PartCAD `basic`
  circle, square and rectangle sketches instead of requesting nonexistent
  `.basic` files.
- Render the shared metric CadQuery slot source as its dimensional capsule
  profile using each sketch's declared diameter and overall length.
- Keep object metadata and links visible when an unrelated 3D conversion
  fails by containing viewer errors inside a dedicated fallback panel.

## [0.3.0] - 2026-08-10

### Added

- Unified catalog support for released packages and active public/private Git
  projects without changing existing package or object routes.
- Project metadata, FPV/category filtering, contribution and issue links, and
  canonical Git file links.
- Standalone private Git imports through the `indra` index and read-only GitHub
  authentication through a token-file/askpass flow.

### Security

- Guest requests cannot enumerate private packages or trigger a private clone.
- Git credentials are excluded from repository URLs, SQLite, API payloads, and
  the generated askpass script.


## [0.2.1] - 2026-08-09

### Added

- Color-preserving OpenSCAD previews through opt-in `NARYS_MATERIAL`
  declarations. Each semantic layer is rendered independently and assembled
  into a multi-material GLB rather than flattened through a single-color STL.

## [0.2.0] - 2026-08-09

### Added

- `model_role` architecture from PartCAD configuration through SQLite, API, and
  the object-detail UI.
- Strict role/format validation: electronic components use SCAD; printable parts
  use FreeCAD FCStd.
- Headless OpenSCAD and FreeCAD preview pipelines producing browser GLB output.
- Hierarchical package navigation matching the NarysAI PUB tree.
- CI for backend, frontend, production build, and Docker runtime construction.

### Changed

- Local development reads mounted PUB and narys-index trees directly while
  production retains immutable repository snapshots.
