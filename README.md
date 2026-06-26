# NanoFabric

A distributed storage system inspired by Nutanix DSF, built incrementally in phases.

## Current status

| Phase | Feature | Status |
|-------|---------|--------|
| 1 | Storage engine (oplog, cache, extent store, recovery) | Done |
| 2 | Cluster membership, failure detection, Docker cluster | Done |
| 3+ | Placement, replication, quorum, self-healing | Done |
| 7 | Enterprise dashboard & observability | Done |
| 8 | Highly available metadata (Raft consensus) | Done |

## Architecture (Phase 8)

```
        Metadata Cluster (Raft)
    ┌──────────┬──────────┬──────────┐
    ▼          ▼          ▼
 metadata1  metadata2  metadata3
  (Leader)  (Follower) (Follower)
            │
    ┌───────┼───────┐
    ▼       ▼       ▼
  Node 1  Node 2  Node 3
 (:8001) (:8002) (:8003)
```

- **Metadata cluster** — 3-node Raft quorum; no single point of failure in the control plane
- **Storage nodes** — Phase 1 engine exposed over HTTP; send heartbeats every 1s
- **Failure detector** — marks nodes DOWN after 3s without heartbeat

## Quick start

### Prerequisites

- Python 3.12+
- Docker & Docker Compose (for cluster mode)

### Local development

```bash
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Linux/macOS

pip install -r requirements.txt
pytest
```

### Run a single node + metadata (no Raft)

```bash
# Terminal 1 — metadata
python -m metadata.main

# Terminal 2 — node
set NODE_ID=node1
set NODE_PORT=8001
set METADATA_URL=http://localhost:9000
python -m node.main
```

### Run HA metadata cluster (3 nodes)

```bash
# Terminal 1
set RAFT_ENABLED=true
set RAFT_NODE_ID=metadata1
set METADATA_PORT=9001
set RAFT_ADVERTISE_URL=http://localhost:9001
set RAFT_PEERS=metadata1=http://localhost:9001,metadata2=http://localhost:9002,metadata3=http://localhost:9003
python -m metadata.main

# Terminals 2 & 3 — metadata2 on :9002, metadata3 on :9003 (same RAFT_PEERS, different RAFT_NODE_ID)
```

Check Raft leader:

```bash
curl http://localhost:9001/raft/leader
curl http://localhost:9001/raft/status
```

### Run the full cluster (Docker)

```bash
docker compose up --build
```

Check cluster health:

```bash
curl http://localhost:9001/cluster-summary
curl http://localhost:9001/raft/leader
```

Expected: `{"node1":"UP","node2":"UP","node3":"UP"}`

### API overview

**Metadata** (`:9001`–`:9003` with Raft, or `:9000` single-node)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/register` | Register a node (redirects to leader if follower) |
| POST | `/heartbeat` | Node liveness ping |
| GET | `/nodes` | Full node details |
| GET | `/cluster-summary` | `{node_id: UP\|DOWN}` |
| GET | `/health` | Service health |
| GET | `/raft/status` | Raft role, term, commit index |
| GET | `/raft/leader` | Current leader ID and URL |
| GET | `/raft/metrics` | Raft observability metrics |
| POST | `/raft/request-vote` | Raft RequestVote RPC |
| POST | `/raft/append-entries` | Raft AppendEntries RPC |

**Node** (`:8001`–`:8003`)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/write` | Write a block |
| GET | `/read/{block_id}` | Read a block |
| GET | `/stats` | Engine statistics |
| GET | `/health` | Node health |

## Project layout

```
nanofabric/
├── metadata/          # Cluster membership & metadata service
│   └── raft/          # Raft consensus (leader election, log replication)
├── node/              # Storage engine & node API
├── dashboard/         # Phase 7 — React enterprise console
├── tests/             # Unit and integration tests
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

### Dashboard (Phase 7)

```bash
cd dashboard
npm install
npm run dev
```

Open http://localhost:5173 — proxies API/WebSocket to metadata on `:9000`.

## License

MIT (or add your preferred license)
