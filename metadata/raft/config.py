"""Raft cluster configuration from environment."""

import os
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class RaftConfig:
    enabled: bool
    node_id: str
    peer_urls: Dict[str, str]
    election_min_ms: int = 150
    election_max_ms: int = 300
    snapshot_threshold: int = 50
    advertise_url: Optional[str] = None


def _parse_peers(raw: str) -> Dict[str, str]:
    peers: Dict[str, str] = {}
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if "=" in part:
            node_id, url = part.split("=", 1)
            peers[node_id.strip()] = url.strip()
        elif ":" in part:
            node_id, _, rest = part.partition(":")
            if rest.startswith("//"):
                peers[node_id.strip()] = f"{node_id.strip()}:{rest}"
            else:
                host_port = part
                node_id = host_port.split(":")[0] if "://" not in host_port else host_port.split("://")[1].split(":")[0]
                peers[node_id] = f"http://{host_port}" if "://" not in host_port else host_port
    return peers


def load_raft_config() -> Optional[RaftConfig]:
    enabled = os.environ.get("RAFT_ENABLED", "").lower() in ("1", "true", "yes")
    node_id = os.environ.get("RAFT_NODE_ID", os.environ.get("METADATA_NODE_ID", ""))
    peers_raw = os.environ.get("RAFT_PEERS", "")

    if not enabled and not peers_raw:
        return None

    if not node_id:
        node_id = "metadata1"

    peer_urls = _parse_peers(peers_raw) if peers_raw else {}
    advertise = os.environ.get("RAFT_ADVERTISE_URL", os.environ.get("METADATA_URL"))

    if advertise:
        peer_urls[node_id] = advertise

    return RaftConfig(
        enabled=enabled or bool(peers_raw),
        node_id=node_id,
        peer_urls=peer_urls,
        election_min_ms=int(os.environ.get("RAFT_ELECTION_MIN_MS", "150")),
        election_max_ms=int(os.environ.get("RAFT_ELECTION_MAX_MS", "300")),
        snapshot_threshold=int(os.environ.get("RAFT_SNAPSHOT_THRESHOLD", "50")),
        advertise_url=advertise,
    )
