# Release gate

## Candidate completeness

Require all repository-declared artifacts, normally including:

- native versioned CAD document;
- source archive and manifest;
- STL and STEP exports for every printable body;
- preview and layout when geometry or placement changed;
- drawing snapshot and version note;
- migration, export, render, and target-version validation tools;
- current index and component inventory updates.

Do not create forbidden convenience exports. Keep manual-only directories empty except for an allowed placeholder.

## Hash ordering

1. Generate final geometry.
2. Export and render.
3. Validate native and exported artifacts.
4. Compute source and artifact hashes.
5. Update manifest and snapshot.
6. Re-run consistency checks without regenerating artifacts.

## Terminal decisions

- **Completed drawing release:** all task-required computational and visual gates pass. Optional physical qualification may remain `not_run`; state that the release is digitally validated and makes no production-readiness claim.
- **Completed product release:** all drawing gates plus the explicitly defined physical qualification plan pass against the exact drawing revision, with engineer sign-off.
- **Blocked candidate:** a gate explicitly required for the selected track by the Issue, repository policy, qualification plan, or user remains incomplete. Preserve changes and use a draft/blocked workflow.
- **Failed:** a required computational gate fails or evidence contradicts the claimed result.

Do not turn generic best practices into mandatory acceptance criteria. Coupon, cycle, vibration, electrical, wiring, load, or environmental tests are blockers only when an authoritative contract requires them. Never tag or publish a blocked candidate, weaken a required gate merely to obtain a green result, or claim physical qualification from digital evidence. Change a requirement only through an explicit authorized decision recorded in the persistent task.
