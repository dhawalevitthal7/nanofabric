import json
import os
from pathlib import Path

SCHEMA_VERSION = 1


class Manifest:
    def __init__(self, path):
        self.path = Path(path)

    def load(self):
        if not self.path.exists():
            return {}
        with open(self.path, encoding="utf-8") as f:
            return json.load(f)

    def save(self, node_id, last_lsn, last_checkpoint_lsn, block_count):
        payload = {
            "node_id": node_id,
            "last_lsn": last_lsn,
            "last_checkpoint_lsn": last_checkpoint_lsn,
            "block_count": block_count,
            "schema_version": SCHEMA_VERSION,
        }
        tmp = self.path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        tmp.replace(self.path)
        return payload
