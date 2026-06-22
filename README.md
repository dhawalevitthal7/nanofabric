# NanoFabric

A distributed storage system inspired by Nutanix DSF, built incrementally in phases.

## Current status

| Phase | Feature | Status |
|-------|---------|--------|
| 1 | Storage engine (oplog, cache, extent store, recovery) | Done |
| 2 | Cluster membership, failure detection, Docker cluster | Done |
| 3+ | Placement, replication, quorum, self-healing | Planned |

## Architecture (Phase 2)

```
                Metadata Service (:9000)
                       │
    ┌──────────────────┼──────────────────┐
    ▼                  ▼                  ▼
  Node 1             Node 2             Node 3
 (:8001)            (:8002)            (:8003)
```

- **Metadata service** — cluster brain; tracks which nodes are UP/DOWN
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

### Run a single node + metadata

```bash
# Terminal 1 — metadata
python -m metadata.main

# Terminal 2 — node
set NODE_ID=node1
set NODE_PORT=8001
set METADATA_URL=http://localhost:9000
python -m node.main
```

### Run the full cluster (Docker)

```bash
docker compose up --build
```

Check cluster health:

```bash
curl http://localhost:9000/cluster-summary
```

Expected: `{"node1":"UP","node2":"UP","node3":"UP"}`

### API overview

**Metadata** (`:9000`)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/register` | Register a node |
| POST | `/heartbeat` | Node liveness ping |
| GET | `/nodes` | Full node details |
| GET | `/cluster-summary` | `{node_id: UP\|DOWN}` |
| GET | `/health` | Service health |

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
├── node/              # Storage engine & node API
├── tests/             # Unit and integration tests
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

## License

MIT (or add your preferred license)
