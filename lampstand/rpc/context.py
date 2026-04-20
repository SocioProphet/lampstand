from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


RPC_VERSION = 1


@dataclass(frozen=True)
class RequestContext:
    session_id: Optional[str] = None
    intent_id: Optional[str] = None
    client_identity: Optional[str] = None
    policy_scope: Optional[str] = None
