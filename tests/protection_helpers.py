"""Shared fixtures for data protection tests."""

import pytest

from node.storage_engine import StorageEngine
from storage.cluster_bridge import EngineBlockAdapter, make_placement_restore
from storage.protection_factory import build_protection_stack
from metadata.metadata_store import MetadataStore


@pytest.fixture
def engine(tmp_path):
    eng = StorageEngine(tmp_path / "node_data", node_id="node1")
    yield eng
    eng.close()


@pytest.fixture
def metadata_store(tmp_path):
    store = MetadataStore(tmp_path / "metadata.db")
    yield store
    store.close()


@pytest.fixture
def protection_stack(tmp_path, engine, metadata_store):
    adapter = EngineBlockAdapter(engine)
    restore_placement = make_placement_restore(metadata_store)

    def clear_blocks():
        engine.purge_all_blocks()

    stack = build_protection_stack(
        data_dir=tmp_path / "protection",
        read_blocks=adapter,
        write_blocks=adapter,
        get_metadata_version=lambda: metadata_store.get_stats()["total_blocks"],
        get_placements=metadata_store.list_all_placements,
        restore_placement=restore_placement,
        clear_blocks=clear_blocks,
    )
    yield stack
    stack.close()
