# Lampstand Trust Addendum

Lampstand is a trusted local retrieval substrate, not merely a convenience search tool.

## Invariants
- indexed roots are policy-governed
- logical route constrains semantic route
- extraction runs out-of-process with bounded resources
- query logging is off by default
- support disclosures are explicit and minimal
- privileged collectors must not create cross-user exposure
- mutating or sensitive RPC calls should carry session and intent context
- material extractor outcomes should be receipted

## Planned trust extensions
- session and intent context on RPC
- workload identity for daemon, collector, and extractors
- extractor receipts
- route provenance
- support bundle generation with explicit disclosure scope
