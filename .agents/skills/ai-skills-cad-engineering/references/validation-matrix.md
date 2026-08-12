# Validation matrix

| Gate | Minimum evidence |
| --- | --- |
| Baseline | tag commit, CAD path, hash, active snapshot consistency |
| Document health | no recompute errors; save/reopen succeeds |
| Parametric integrity | constrained controls; dependency reaches final body; edit test on copy |
| Printable bodies | expected count; each valid and one solid |
| Feature integration | measurable change and direct feature/body evidence |
| Native replacement | local symmetric difference is zero; no repair dependency, legacy loop, seam, filler, or residual contour |
| Components | exact source hash, provenance, placement, embedded-source membership |
| Collisions | explicit allowed contacts and zero forbidden intersections |
| Assembly | insertion/removal sequence and required clearances |
| Service | connector, terminal, fastener, and tool trajectories |
| Exports | every STL/STEP independently reopened and compared |
| Presentation | preview/layout generated from saved native CAD |
| Release consistency | manifest, snapshot, version note, README, and hashes agree |
| Historical integrity | baseline paths and tag unchanged |
| Release track | authoritative contract identifies digital drawing or physically qualified product |
| Physical qualification | for product track or an explicitly required physical gate: exact-revision sample, measurements, assembly evidence, and engineer sign-off; otherwise record `not_run` without blocking the drawing release |

Run repository validators independently after the implementation agent finishes. A validator must fail when a requested feature is absent from the final body, not merely when its named helper object is missing.

For visual review, provide overall assembly views and close-ups of every changed interface. For replacements, show the component both installed and hidden, with helper geometry hidden and edges visible. Visual review supplements geometry checks; it does not replace them.
