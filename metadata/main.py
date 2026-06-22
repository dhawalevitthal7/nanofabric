"""Entry point for the metadata service."""

import logging
import os

import uvicorn

from metadata.constants import DEFAULT_METADATA_PORT

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)


def main() -> None:
    port = int(os.environ.get("METADATA_PORT", DEFAULT_METADATA_PORT))
    uvicorn.run(
        "metadata.app:app",
        host="0.0.0.0",
        port=port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
