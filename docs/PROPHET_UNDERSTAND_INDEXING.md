# Prophet Understand Indexing

## Purpose

Lampstand is the local index and retrieval surface for Prophet Understand / Repo Intelligence v0 artifacts.

The canonical artifact is emitted as:

```text
.prophet/prophet-understanding.json
```

The platform schema and fixture live in `SocioProphet/prophet-platform` under:

- `schemas/repo-intelligence/prophet-understanding.schema.json`
- `examples/repo-intelligence/prophet-understanding.fixture.json`

## Indexing stance

Lampstand does not own graph generation. Smart Tree or another governed scanner emits the artifact. Lampstand ingests the artifact and exposes searchable records while preserving evidence, policy state, validation state, and graph relationships.

## Index record families

v0 should produce these record families:

- `repo_graph_node`: one record per node
- `repo_graph_edge`: one record per edge
- `repo_graph_summary`: one record per node summary
- `repo_graph_tour`: one record per guided tour step
- `repo_graph_diff_impact`: one record per diff impact set
- `repo_graph_policy`: one record per policy check
- `repo_graph_validation`: one record per validation result
- `repo_graph_receipt`: one record per provenance receipt

## Required retained fields

Every indexed record should retain:

- `repo_full_name`
- `repo_commit`
- `schema_version`
- `record_family`
- `record_id`
- `title`
- `text`
- `node_id` or `edge_id` when applicable
- `path` when applicable
- `source_anchor` when applicable
- `confidence` when applicable
- `provenance_receipt_ids`
- `policy_state` when applicable
- `validation_status` when applicable
- `raw` compact source object for exact evidence recovery

## Query targets

v0 retrieval must support at least:

- what owns this file?
- what depends on this contract?
- which tests cover this node?
- what changed in this PR impact set?
- what policy gates touch this service?

## Safety rules

Invalid or stale artifacts should not disappear. They should be indexed as status records so search can answer: "why is this repo graph untrusted?"

No record may drop provenance IDs. If the upstream artifact lacks provenance, Lampstand must mark the indexed record as incomplete rather than inventing evidence.

## First smoke command

```bash
python3 tools/index_prophet_understanding.py \
  --artifact path/to/prophet-understanding.json \
  --out build/prophet-understand-index.json
```

The output is a deterministic JSON list of index records that Sherlock can consume in the next tranche.
