# Changelog

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
