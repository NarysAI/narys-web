# Baseline and source-of-truth gate

## Required evidence

Before editing, resolve and record:

- repository default branch and clean worktree state;
- active drawing version and immutable tag;
- tag commit and native CAD path;
- native CAD SHA-256;
- synchronization status and source provenance;
- units, coordinate system, body architecture, and component inventory;
- applicable repository and scoped instructions;
- required tools, validators, and expected release artifacts.

## Stop conditions

Stop without editing when:

- an instruction file, active guide, or active snapshot is missing;
- the active guide and snapshot disagree;
- the tag is missing, mutable, or resolves to unexpected content;
- the native CAD hash differs from the declared baseline;
- only mesh or neutral-format artifacts exist but the task assumes a preserved parametric model;
- the requested component source is unavailable or not pinned;
- the task requires invented dimensions, tolerances, pinout, loads, or material properties.

## Historical integrity

Never modify a released version in place. Create a new versioned directory, snapshot, and version note. Verify the old version by path-scoped diff and artifact hashes before completion.

Treat a reverted or rejected candidate as evidence, not as a new baseline, unless the repository explicitly promotes it.
