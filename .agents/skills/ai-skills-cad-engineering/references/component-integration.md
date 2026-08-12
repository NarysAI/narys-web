# Exact component integration

## Source package

Preserve together:

1. exact immutable catalog revision;
2. original editable source;
3. exact imported/rendered artifact;
4. SHA-256 for both files;
5. units and import transformation;
6. provenance stored in the native CAD object and source manifest.

Do not substitute a hand-built envelope when an exact model is required. Use a simplified clearance body only as an explicitly derived non-source witness and retain the exact component model.

## Placement and mounting

- Derive the panel opening, mounting axes, clips, fasteners, keep-outs, and connector access from verified geometry.
- Replace an obsolete mount in the native construction history. Never fuse material into the old opening to make it smaller; rebuild the continuous wall or host feature first, then apply the new opening once.
- Preserve an inspectable transform from source coordinates to assembly coordinates.
- Model required contact separately from forbidden overlap.
- Check both installed and insertion/removal states.
- Check terminal access, actual connection direction, wire exit, bend radius, insulation clearance, and strain relief.
- When replacing a component, remove obsolete cuts, clip reliefs, bridges, labels, validation rules, source entries, active embedded objects, repair features, and downstream dependencies belonging only to the old component.

## Physical limits

Digital geometry cannot prove print tolerance, clip force, fatigue, vibration retention, electrical pinout, connector friction, material behavior, or tool ergonomics. Never declare these properties physically proven from CAD evidence.

- For a digital drawing release, validate geometry, clearances, paths, and intended contacts in the native model. Record relevant untested physical properties as limitations or recommended follow-up; they do not block completion unless the authoritative task contract explicitly requires them.
- For a physically qualified product release, require a real print or manufacturing sample, dimensional inspection of all mounting openings and critical interfaces, assembly and removal checks, intended actuator travel, and engineer sign-off against the exact drawing revision.
- Require coupon tests, repeated clip cycles, vibration, electrical continuity or pinout, wire-gauge trials, loads, environmental tests, or other specialized tests only when the Issue, repository policy, qualification plan, or user explicitly requires them.
