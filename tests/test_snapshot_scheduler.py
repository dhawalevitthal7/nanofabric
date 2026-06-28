"""Tests for SnapshotScheduler."""

import time

from storage.models import PolicySchedule


def test_create_policy(protection_stack):
    policy = protection_stack.scheduler.create_policy(
        name="daily-backup",
        schedule=PolicySchedule.DAILY,
        retention_count=3,
    )
    assert policy.name == "daily-backup"
    assert policy.schedule == PolicySchedule.DAILY

    policies = protection_stack.scheduler.list_policies()
    assert any(p.policy_id == policy.policy_id for p in policies)


def test_run_due_policies(protection_stack, engine):
    engine.write("sched1", "data", version=1)
    policy = protection_stack.scheduler.create_policy(
        name="hourly",
        schedule=PolicySchedule.HOURLY,
        retention_count=5,
    )
    policy.next_run_at = int(time.time() * 1000) - 1000
    protection_stack.store.save_policy(policy)

    results = protection_stack.scheduler.run_due_policies()
    assert len(results) >= 1
    assert "snapshot_id" in results[0]
