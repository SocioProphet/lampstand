"""RPC layer.

We standardize on SocioProphet's **TriTRPC** framework for production, but we
keep a tiny Unix-socket JSON transport for local development/tests where
TriTRPC is not available.

The transport boundary is intentionally thin: business logic lives in
lampstand.rpc.service and should be transport-agnostic.
"""
