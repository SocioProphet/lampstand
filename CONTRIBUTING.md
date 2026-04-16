# Contributing

## Principles
- correctness before cleverness
- deterministic local behavior first
- privacy by default
- watchers are never sufficient without reconciliation
- GNOME integration remains a thin client boundary
- transport boundaries stay explicit and versioned

## Change expectations
Behavior changes should update the relevant docs in `docs/`, especially `SPEC.md` and `TRUST_ADDENDUM.md` when trust or runtime boundaries move.

## Before opening a PR
- run the test suite
- explain trust-boundary impact
- explain packaging or distro impact
- keep changes scoped and reviewable
