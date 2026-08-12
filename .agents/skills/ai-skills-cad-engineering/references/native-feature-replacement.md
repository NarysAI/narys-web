# Native feature replacement

Apply this workflow whenever replacing or resizing a component, opening, pocket, boss, mount, connector access, relief, channel, or fastener feature.

## Non-negotiable rule

Change the feature at the earliest editable point that defines it. Do not repair a finished downstream solid by adding material over obsolete geometry.

Forbidden substitutes include:

- wall-restoration patches fused into an already cut enclosure;
- overlay plates, plugs, skins, caps, filler solids, or coplanar sheets;
- sacrificial bridges used to hide an oversized legacy opening rather than support the final intended opening;
- baked `Part::Feature` copies that sever the editable dependency chain;
- downstream face replacement that leaves the old boundary, seam, or topology in place.

A removable manufacturing support is allowed only when project policy explicitly requires it, it lies inside the final correct opening, and the native opening remains independently verifiable with the support hidden or removed. Never use support material to correct an incorrect opening.

## Required reconstruction order

1. Find the last native body before the obsolete feature was applied.
2. If no such body is stored, replay the original editable construction chain from its native walls, shells, sketches, and non-obsolete operations.
3. Omit the old component-specific cutter, relief, bridge, and dependent operations.
4. Create the new fully constrained control geometry.
5. Apply the new operation once to the reconstructed native body.
6. Reconnect later legitimate operations without baking or flattening the model.
7. Remove obsolete objects and prove that no surviving final object depends on them.

If steps 1–6 cannot be performed without inventing geometry or losing user-authored state, preserve the worktree and report a blocker. Do not fall back to a patch.

## Required computational proof

Define a bounded validation zone around the replaced feature and independently construct:

`expected = native_pre_feature_body + legitimate_existing_operations - new_intended_cut`

Within that zone, require zero symmetric-difference volume between `expected` and the final candidate. Also require:

- no obsolete cutter or repair object in the final dependency graph;
- no closed edge loop corresponding to the legacy opening;
- no unexplained coplanar face boundary or internal face around the repaired zone;
- the expected wall thickness throughout the material surrounding the new opening;
- exactly the intended opening count, profile, position, and through-depth;
- a measurable downstream response when a new controlling dimension is perturbed on a disposable copy.

Do not validate only by object names, overall volume, or the existence of a new sketch. Those checks can pass while a repair patch remains.

## Required visual proof

Render close-ups from both sides of the affected wall with:

1. the component hidden, showing the bare native opening;
2. the component installed;
3. construction/helper objects hidden;
4. edge display enabled when it helps reveal seams or residual contours.

Treat visible legacy perimeters, nested outlines, patch seams, or unexplained planar subdivisions as a failed gate even when the document reports one solid.
