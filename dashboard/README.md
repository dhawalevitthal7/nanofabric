# NanoFabric Dashboard

Enterprise-grade cluster management console for NanoFabric — inspired by Nutanix Prism Central.

## Tech Stack

- React 19 + TypeScript + Vite
- TailwindCSS + shadcn-style components
- TanStack Router + TanStack Query
- Zustand state management
- Recharts + React Flow + Framer Motion

## Quick Start

```bash
cd dashboard
npm install
npm run dev
```

Open http://localhost:5173

## Backend Connection

The dashboard proxies API requests to the metadata service at `localhost:9000`.

Start the cluster first:

```bash
# Terminal 1 — metadata
python -m metadata.main

# Terminal 2+ — nodes
set NODE_ID=node1 && set NODE_PORT=8001 && set METADATA_URL=http://localhost:9000
python -m node.main
```

Or use Docker:

```bash
docker compose up --build
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `VITE_API_URL` | `/api` | Metadata API base URL |
| `VITE_WS_URL` | `ws://localhost:9000/ws/cluster` | WebSocket endpoint |

## Features

- Executive cluster overview with live health cards
- Interactive React Flow topology
- Real-time metrics (WebSocket + polling fallback)
- Node grid/table views with actions
- Placement, replication, consistency consoles
- Repair job management
- Grafana-style metrics platform
- Live log viewer with search/filter
- Alert center with toast notifications
- Global search (⌘K)
