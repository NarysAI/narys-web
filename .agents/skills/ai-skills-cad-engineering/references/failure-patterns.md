# Known CAD failure patterns

Use this list when diagnosing a failed or reverted candidate.

- **Helper-only implementation:** sketches and cutters exist, but printable geometry is unchanged. Prove downstream integration.
- **Downstream patch repair:** an oversized legacy hole is covered by a fused wall patch, plate, plug, skin, or filler instead of changing the native opening. Rebuild the pre-feature body and apply only the new cutter.
- **One-solid false confidence:** fused repair geometry reports one valid solid but retains nested contours, seams, coplanar subdivisions, or an obsolete dependency. Compare the local solid with an independently constructed native expectation.
- **Silent boolean no-op:** a compound cut recomputes without producing the requested feature. Replace with validated sequential operations.
- **Mesh reconstruction:** a native model is replaced from STL/STEP and loses editability or user state. Return to the verified FCStd baseline.
- **Approximate component substitution:** local dimensions replace a required catalog artifact. Pin and embed the exact source.
- **Appearance destruction:** headless finalization overwrites colors, visibility, or transparency. Compare saved view properties with baseline.
- **Validator circularity:** the same script creates and validates its own assumptions. Add independent geometry and persistence evidence.
- **Stale version gate:** policy runs only an older validator. Keep baseline regression tests and add a target-version validator.
- **Documentation ahead of geometry:** README or snapshot claims a feature that the final body lacks. Derive claims from validated artifacts.
- **Qualification overreach:** generic physical risks such as coupon, vibration, cycle, pinout, or wiring tests are added as blockers although the authoritative task does not require them. Keep them as recommendations for a drawing release.
- **Premature product qualification:** a digitally validated drawing is called production-ready before the required sample, measurements, assembly checks, and engineer sign-off pass. Keep drawing and product qualification claims separate.
- **Aggregated scope:** one task attempts a range of unrelated issues. Split into independently testable results.
- **Historical mutation:** old version directories or tags change during a new release. Diff immutable paths and verify hashes.
- **Export trust:** STL/STEP files exist but were never reopened. Validate every exported body independently.
