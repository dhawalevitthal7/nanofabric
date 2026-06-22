"""Tests for failure detection background worker."""

import time

from metadata.failure_detector import FailureDetector
from metadata.membership import MembershipRegistry


def test_failure_detector_marks_stale_nodes():
    registry = MembershipRegistry(failure_timeout_sec=0.1)
    registry.register("node1", "node1:8001")

    detector = FailureDetector(registry, interval_sec=0.05)
    detector.start()
    try:
        time.sleep(0.35)
        summary = registry.get_cluster_summary()
        assert summary.get("node1") == "DOWN"
    finally:
        detector.stop()


def test_failure_detector_allows_recovery():
    registry = MembershipRegistry(failure_timeout_sec=0.1)
    registry.register("node1", "node1:8001")

    detector = FailureDetector(registry, interval_sec=0.05)
    detector.start()
    try:
        time.sleep(0.35)
        assert registry.get_cluster_summary()["node1"] == "DOWN"

        registry.heartbeat("node1")
        assert registry.get_cluster_summary()["node1"] == "UP"
    finally:
        detector.stop()
