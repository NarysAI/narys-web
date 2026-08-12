# Drawing and product release lifecycle

## Select one release track

Use the persistent task and repository rules as the authority. If they request only a CAD, drawing, model, or export release, use the drawing track. Use the product track only when physical qualification is explicitly in scope.

Functional wording alone does not select the product track. For example, requirements that a component fit, install, remove, clip, move through positions, expose terminals, or allow wire routing are digital assembly and clearance checks in a drawing task. Treat them as physical gates only when the contract explicitly asks for a printed or manufactured sample, measurement, hands-on trial, test procedure, or engineer sign-off.

### Digital drawing release

A drawing release proves that the native model and required artifacts are internally consistent and digitally validated. Require the applicable computational and visual gates: source provenance, native feature integrity, recompute and persistence, topology, collision and clearance analysis, assembly-path analysis, exports, renders, manifests, hashes, and historical immutability.

Use the repository's existing drawing tag. When no convention exists, prefer `drawing-v<design-version>`. State that physical manufacture and product qualification are not claimed. Unrequested physical tests are recommendations, not blockers.

### Physically qualified product release

A product release proves that an exact drawing revision was manufactured and checked by an engineer. Require:

1. the exact immutable drawing tag, commit, source hashes, material, manufacturing process, and relevant print or fabrication settings;
2. a real sample made from that revision;
3. dimensional inspection of every mounting hole, opening, and critical interface identified by the qualification plan;
4. installation, fastening or clip engagement, intended movement, removal, and full assembly checks without unintended damage;
5. component, cable, connector, and service checks that are explicitly in product scope;
6. recorded results, deviations, evidence, engineer identity, date, and sign-off.

Add cycle, vibration, electrical, load, thermal, environmental, or regulatory tests only when an authoritative qualification plan requires them. When no repository convention exists, prefer `product-v<design-version>` and make it reference the exact qualified drawing commit.

## Version and branch policy

Keep one design lineage. Use short-lived work branches and separate immutable tags or release records for maturity; do not maintain divergent long-lived drawing and product geometry branches.

- A product tag must identify the exact drawing revision that was tested.
- Never move or overwrite either tag.
- If physical testing requires a geometry or material change, create a new drawing version, rerun digital validation, manufacture a new sample, and qualify the new revision.
- A drawing version may exist without a product tag. A product tag must not exist without its qualified drawing revision and evidence.
