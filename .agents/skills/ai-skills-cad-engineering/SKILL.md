---
name: ai-skills-cad-engineering
description: Perform reliable CAD and FreeCAD engineering changes, component replacements, enclosure adaptations, parametric modeling, artifact export, validation, digitally validated drawing releases, and physically qualified product releases. Use for FCStd, STEP, STL, OpenSCAD, PartCAD, enclosure geometry, mounting features, collision checks, service access, physical prototype qualification, source provenance, CAD snapshots, manifests, or drawing release work where preserving an existing model and proving the claimed maturity level are critical.
---

# CAD engineering workflow

Treat repository instructions and repository-owned validators as authoritative. Use this skill to make the work systematic; never replace project-specific requirements with generic assumptions.

## 1. Establish the contract

1. Read every applicable `AGENTS.md`, the complete project guide, the active drawing snapshot, and the requested Issue before writing.
2. Identify the immutable baseline tag, CAD path, SHA-256, coordinate system, unit system, current component inventory, expected printable bodies, and release target.
3. Stop before editing if the sources of truth conflict or the baseline cannot be verified.
4. Separate the requested result from related-Issue context. Do not absorb a backlog into the task.
5. Select the release track declared by the Issue, repository policy, or user: digital CAD/drawing or physically qualified product. A drawing release does not imply product qualification.
6. Classify every acceptance criterion as computational, visual, physical, or operator-only according to that authoritative contract. For a drawing track, wording such as fit, install, remove, clip, actuate, route, or access means digital geometry/path validation unless the contract explicitly requires a manufactured sample or hands-on test. Never promote a generic engineering risk into a mandatory gate, and never report a physical criterion as passed from geometry alone.

Read [baseline-and-source-truth.md](references/baseline-and-source-truth.md) when selecting or validating a baseline. Read [failure-patterns.md](references/failure-patterns.md) before repairing an existing failed candidate.

## 2. Inspect before modifying

1. Open the existing native CAD document and inspect its tree, object types, expressions, properties, placements, groups, solids, visibility, and recompute state.
2. Record a machine-readable baseline report. When FreeCAD is available, run:

   `python scripts/run_inspect_fcstd.py --freecad FreeCADCmd.exe --file <baseline.FCStd> --output <baseline-report.json>`

3. Do not rebuild an existing native document from mesh, STEP, screenshots, snapshots, or bootstrap generators.
4. Do not overwrite user-saved placements, colors, visibility, expressions, or manual edits unless the task explicitly requires those exact changes.
5. Work in a new versioned path when repository rules make historical releases immutable.

## 3. Implement the smallest complete engineering change

1. Use exact, pinned component sources. Preserve the editable source, exact imported artifact, provenance revision, and SHA-256 together.
2. Place external components in the repository's embedded-source group and derive mounting geometry from the verified model.
3. Replace legacy geometry at its native upstream feature. Never conceal an obsolete hole, pocket, relief, or mounting feature by fusing a patch, plate, plug, skin, filler, or coplanar repair into a downstream finished body.
4. If the native pre-feature body or editable construction chain cannot be recovered, stop with a blocker. Do not substitute additive repair geometry merely to obtain the requested final envelope.
5. Keep controlling geometry editable and fully constrained when the repository requires Sketcher-based control.
6. Connect every control feature to the final printable body through an inspectable dependency or sequential boolean chain. The existence of a sketch or cutter does not prove integration.
7. Remove obsolete component-specific cuts, reliefs, labels, active embedded sources, and downstream remnants when replacing a component.
8. Limit collateral changes. Preserve unrelated component placements, printable bodies, coordinate systems, appearance, and document structure.

For every replacement or resized opening, read and follow [native-feature-replacement.md](references/native-feature-replacement.md). Read [component-integration.md](references/component-integration.md) for component work and [parametric-geometry.md](references/parametric-geometry.md) for native modeling and boolean operations.

## 4. Validate in layers

Run validation after each meaningful geometry group, not only at the end.

1. Recompute and reject document errors.
2. Save, close, reopen, recompute, save, and reopen again.
3. Confirm expected printable-body count, solid count, bounds, volume, and topology.
4. Prove that requested features affect the intended final body.
5. For a replacement, prove that the affected local solid equals the native unmodified feature with only the new intended operation applied. Reject residual legacy contours, additive repair dependencies, extra coplanar boundaries, and hidden filler bodies.
6. Check collisions and required contacts separately. A required mounting contact is not an unwanted collision.
7. Check assembly order, removal path, connector insertion path, fastener axis, tool envelope, terminal access, wiring space, bend radius, and strain relief digitally where applicable. Label this evidence as geometric; do not claim physical fit, force, or durability.
8. Test parametric editability on a disposable copy, then restore the original parameter.
9. Export required STL and STEP artifacts and reopen every export independently.
10. Render close-ups with the component shown and hidden so the native opening and surrounding wall are reviewable.
11. Render the saved FCStd, not an approximate parallel model.
12. Run every repository-owned test exactly as controlled by the runner.

Generate a candidate report with `run_inspect_fcstd.py`, then compare it with the baseline using:

`python scripts/compare_fcstd_reports.py --baseline <baseline-report.json> --candidate <candidate-report.json>`

Read [validation-matrix.md](references/validation-matrix.md) for the evidence required by each gate.

## 5. Assemble a coherent release candidate

1. Keep native CAD, embedded sources, exports, preview, layout, manifest, snapshot, version note, and active index mutually consistent.
2. Recompute SHA-256 only after final artifact generation. Re-run validation after any hash-bearing file changes.
3. Prove historical baseline immutability with a diff or stored hashes.
4. Keep manual-only formats empty when project policy forbids automated generation.
5. Do not create or approve a tag or release when any mandatory gate is incomplete.
6. Permit a drawing release when its required digital gates pass, even if optional future physical qualification has not run. Never label it production-ready or physically qualified.
7. Create a product-qualified release only from an exact drawing commit after the required physical build, measurement, assembly, and engineer sign-off pass.

Read [release-lifecycle.md](references/release-lifecycle.md) to select the release track and tag policy. Read [release-gate.md](references/release-gate.md) before declaring completion.

## 6. Report truthfully

- Return `completed` when all task-required gates for the selected release track pass.
- Return `blocked` with the completed candidate preserved only when an authoritative task or repository source explicitly requires an incomplete physical or operator gate.
- Return `no_change_needed` only after proving the requested state already exists.
- Record unrequested coupon, cycle, vibration, pinout, wiring, or other physical tests as follow-up recommendations, not blockers. Do not invent acceptance criteria.
- List each blocker separately with evidence and one actionable next step.
- Distinguish `not_run`, `failed`, and `passed`. Never convert absence of evidence into success.
- Do not hide release blockers in risks or summary text.
