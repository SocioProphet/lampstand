# Lampstand Runtime Trust Delta v1

This document defines the first runtime hardening delta beyond repository governance.

## Scope
Lampstand is a trusted local retrieval substrate. Runtime trust must cover the daemon, RPC boundary, extractors, route selection, and support or export paths.

## Session and intent on RPC
Every mutating or sensitive RPC call should carry session and intent context.

Initial targets:
- reindex operations
- future policy mutation calls
- future removable-media indexing controls
- future debug or export bundle generation

## Workload identity
The following workloads need explicit identity and trust posture:
- lampstandd
- collector components
- extractor subprocesses
- future semantic sidecars

Each workload should declare:
- role
- allowed side effects
- network posture
- filesystem scope
- receipt obligations

## Extractor receipts
Material extraction outcomes should produce structured receipts containing:
- source identity reference
- source hash when available
- extractor name and version
- outcome status
- elapsed time
- policy flags
- failure summary when relevant

## Route-policy invariants
Logical route constrains semantic route.

This means:
- policy decides which roots and fields are admissible
- semantic ranking may only operate within admissible candidates
- future semantic retrieval must not bypass index root policy or extractor policy

## Query and support privacy
Defaults should be:
- query logging off
- explicit debug bundle generation only
- support disclosures minimal and user-reviewable
- no silent cross-context analytics joins

## Near-term implementation sequence
1. version RPC messages
2. add optional session and intent fields to message schema
3. add extractor receipt objects
4. add route provenance fields to search or debug outputs
5. add explicit support or export bundle command with disclosure scope
