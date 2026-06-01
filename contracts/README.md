# Lampstand Contracts

Lampstand is the local-first search/indexing service for SourceOS, SociOS, and SocioProphet surfaces.

This contract set defines the minimum governed boundary for search, index publication, mesh publication, and audit receipts.

## Schemas

| Schema | Purpose |
|---|---|
| `schemas/lampstand.query.v0.schema.json` | Query request envelope for local and RPC-backed search. |
| `schemas/lampstand.index-publication.v0.schema.json` | Index publication record emitted after scan/reconcile/update. |
| `schemas/lampstand.mesh-publication-policy.v0.schema.json` | Policy envelope controlling whether and how index metadata can leave the local device. |
| `schemas/lampstand.audit-receipt.v0.schema.json` | Audit receipt for query, publication, denial, health, and mesh-publication events. |

## Examples

| Example | Schema |
|---|---|
| `examples/lampstand.query.v0.example.json` | `schemas/lampstand.query.v0.schema.json` |
| `examples/lampstand.index-publication.v0.example.json` | `schemas/lampstand.index-publication.v0.schema.json` |
| `examples/lampstand.mesh-publication-policy.v0.example.json` | `schemas/lampstand.mesh-publication-policy.v0.schema.json` |
| `examples/lampstand.audit-receipt.v0.example.json` | `schemas/lampstand.audit-receipt.v0.schema.json` |

## Boundary rules

1. Local indexing remains local-first by default.
2. Mesh publication is opt-in and must be policy-gated.
3. Query and publication events must be auditable.
4. Health/stats are part of the operational contract, not incidental debug output.
5. TriTRPC is the production RPC direction; unixjson remains a development/test fallback.

## Validation

Run:

```bash
make validate
```

The validation path includes `tools/check_lampstand_contract_schemas.py`, which validates schema shape and the committed examples against the schema subset used by these contracts.
