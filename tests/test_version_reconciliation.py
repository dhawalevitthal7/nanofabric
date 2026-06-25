"""Tests for version reconciliation."""

from node.version_reconciliation import (
    ReplicaCopy,
    compare_copies,
    find_stale_replicas,
    select_latest,
)


def _copy(node, version, lsn=0, ts=0, data="x"):
    return ReplicaCopy(
        node_id=node,
        block_id="b1",
        data=data,
        version=version,
        lsn=lsn,
        timestamp_ms=ts,
    )


def test_latest_version_wins():
    copies = [_copy("n1", 10), _copy("n2", 8), _copy("n3", 10)]
    latest = select_latest(copies)
    assert latest.version == 10


def test_lsn_tiebreaker():
    copies = [_copy("n1", 10, lsn=5), _copy("n2", 10, lsn=8)]
    assert compare_copies(copies[1], copies[0]) > 0
    assert select_latest(copies).node_id == "n2"


def test_find_stale_replicas():
    copies = [_copy("n1", 10), _copy("n2", 8), _copy("n3", 10)]
    latest = select_latest(copies)
    stale = find_stale_replicas(copies, latest)
    assert len(stale) == 1
    assert stale[0].node_id == "n2"
