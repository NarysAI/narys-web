# Parametric native geometry

## Preservation rules

- Inspect the existing document before using scripts that write it.
- Prefer migration from the verified native baseline over reconstruction.
- Preserve object identity, expressions, placements, colors, visibility, and manual edits outside the requested scope.
- Test destructive or parametric experiments on a disposable copy.

## Control geometry

- Use fully constrained sketches for new controlling profiles when Sketcher is available and required.
- Give features stable semantic names.
- Keep dimensions and placement inputs discoverable as properties or constraints.
- Connect each sketch to the final printable through explicit derived geometry.

## Boolean reliability

- Prefer an inspectable sequential boolean chain when a large compound cutter obscures failures.
- Recompute and validate after every feature group.
- Confirm each cut or fuse changes the intended body's geometry by volume, topology, bounds, section, or direct intersection evidence.
- Reject a candidate where control geometry exists but the final printable is unchanged.
- Reject null shapes, invalid solids, unexpected compounds, multiple solids, or silent no-op operations.

## Persistence test

Require: open → recompute → save → close → reopen → recompute. Then perturb one controlling parameter on a copy, confirm the intended downstream change, restore it, and reopen again.
