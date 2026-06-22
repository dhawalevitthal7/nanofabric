"""Entry point for a storage node."""

import logging
import os

import uvicorn

from node.api_server import create_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)


def main() -> None:
    node_id = os.environ.get("NODE_ID", "node1")
    port = int(os.environ.get("NODE_PORT", "8001"))
    data_dir = os.environ.get("DATA_DIR", f"./data/{node_id}")
    metadata_url = os.environ.get("METADATA_URL", "http://localhost:9000")
    address = os.environ.get("NODE_ADDRESS", f"localhost:{port}")

    app = create_app(
        node_id=node_id,
        data_dir=data_dir,
        metadata_url=metadata_url,
        address=address,
    )
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
