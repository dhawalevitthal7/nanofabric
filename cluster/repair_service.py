"""Central repair orchestrator — scan, schedule, execute, verify, retry."""

import logging
import time
from typing import Callable, Dict, List, Optional

from cluster.anti_entropy_service import AntiEntropyService
from cluster.placement_reconciliation import PlacementReconciliation
from cluster.re_replication_service import ReReplicationService
from cluster.repair_job_store import RepairJobStore
from cluster.repair_models import (
    ClusterHealthReport,
    RepairJob,
    RepairStatus,
    RepairType,
)
from cluster.replica_health_scanner import ReplicaHealthScanner
from metadata.placement_policy import PlacementPolicy

log = logging.getLogger(__name__)

MAX_REPAIR_ATTEMPTS = 5


class RepairService:

    def __init__(
        self,
        coordinator_node_id: str,
        job_store: RepairJobStore,
        health_scanner: ReplicaHealthScanner,
        re_replication: ReReplicationService,
        anti_entropy: AntiEntropyService,
        placement_reconciliation: PlacementReconciliation,
        placement_policy: PlacementPolicy,
        get_healthy_nodes_fn: Callable[[], List[str]],
        get_block_version_fn: Callable[[str], Optional[int]],
        remove_extra_replica_fn: Optional[Callable[[str, str, int], List[str]]] = None,
        metrics=None,
    ):
        self._coordinator_node_id = coordinator_node_id
        self._job_store = job_store
        self._health_scanner = health_scanner
        self._re_replication = re_replication
        self._anti_entropy = anti_entropy
        self._placement_reconciliation = placement_reconciliation
        self._placement_policy = placement_policy
        self._get_healthy_nodes = get_healthy_nodes_fn
        self._get_block_version = get_block_version_fn
        self._remove_extra_replica = remove_extra_replica_fn
        self._metrics = metrics
        self._last_health: Optional[ClusterHealthReport] = None

    @property
    def last_health_report(self) -> Optional[ClusterHealthReport]:
        return self._last_health

    def scan_cluster(self) -> ClusterHealthReport:
        report = self._health_scanner.scan_cluster()
        self._last_health = report
        if self._metrics:
            self._metrics.set_under_replicated_blocks(len(report.under_replicated))
            self._metrics.set_over_replicated_blocks(len(report.over_replicated))
            self._metrics.set_orphan_blocks(len(report.orphans))
        return report

    def schedule_repair(
        self,
        block_id: str,
        source_node: str,
        target_node: str,
        version: int,
        repair_type: RepairType = RepairType.RE_REPLICATION,
    ) -> RepairJob:
        job = self._job_store.create_job(
            block_id=block_id,
            source_node=source_node,
            target_node=target_node,
            version=version,
            repair_type=repair_type,
        )
        if self._metrics:
            self._metrics.inc_repair_jobs_total()
        return job

    def repair_block(self, block_id: str) -> dict:
        report = self.scan_cluster()
        under = next((b for b in report.under_replicated if b.block_id == block_id), None)
        diverged = next((b for b in report.diverged if b.block_id == block_id), None)

        if diverged:
            return self._anti_entropy.repair_divergence(block_id)

        if under:
            missing = under.missing_nodes[0] if under.missing_nodes else None
            healthy = self._get_healthy_nodes()
            present = under.present_nodes
            source = present[0] if present else None
            target = self._select_replacement(block_id, under.desired_nodes, healthy)
            if not source or not target:
                return {"ok": False, "error": "cannot determine source or target"}
            job = self.schedule_repair(
                block_id, source, target, under.version, RepairType.RE_REPLICATION
            )
            return self._execute_job(job, missing_node=missing)

        return {"ok": True, "message": "block is healthy", "block_id": block_id}

    def repair_node(self, failed_node: str) -> dict:
        report = self.scan_cluster()
        repaired = 0
        failed_jobs: List[str] = []

        for under in report.under_replicated:
            if failed_node not in under.missing_nodes:
                continue
            healthy = self._get_healthy_nodes()
            source = under.present_nodes[0] if under.present_nodes else None
            target = self._select_replacement(block_id=under.block_id, current_nodes=under.desired_nodes, healthy_nodes=healthy)
            if not source or not target:
                failed_jobs.append(under.block_id)
                continue
            job = self.schedule_repair(
                under.block_id, source, target, under.version, RepairType.NODE_RECOVERY
            )
            result = self._execute_job(job, missing_node=failed_node)
            if result.get("ok"):
                repaired += 1
            else:
                failed_jobs.append(under.block_id)

        return {
            "failed_node": failed_node,
            "repaired": repaired,
            "failed_blocks": failed_jobs,
        }

    def verify_repair(self, job_id: str) -> dict:
        job = self._job_store.get_job(job_id)
        if job is None:
            return {"ok": False, "error": "job not found"}

        verified = self._re_replication.verify_copy(
            job.block_id, job.source_node, job.target_node
        )
        if verified:
            self._job_store.update_job_status(job.job_id, RepairStatus.COMPLETED)
            if self._metrics:
                self._metrics.inc_repair_jobs_completed()
            return {"ok": True, "job_id": job_id, "verified": True}
        return {"ok": False, "job_id": job_id, "verified": False}

    def recover_jobs(self) -> int:
        recovered = 0
        for job in self._job_store.list_interrupted_jobs():
            self._job_store.update_job_status(job.job_id, RepairStatus.PENDING)
            recovered += 1

        for job in self._job_store.list_jobs_by_status(RepairStatus.FAILED):
            if job.attempt_count < MAX_REPAIR_ATTEMPTS:
                self._job_store.update_job_status(job.job_id, RepairStatus.PENDING)
                recovered += 1
        return recovered

    def run_repair_cycle(self) -> dict:
        self.recover_jobs()
        report = self.scan_cluster()
        scheduled = 0
        executed = 0
        failed = 0

        for under in report.under_replicated:
            healthy = self._get_healthy_nodes()
            source = under.present_nodes[0] if under.present_nodes else None
            target = self._select_replacement(under.block_id, under.desired_nodes, healthy)
            if not source or not target:
                continue
            job = self.schedule_repair(
                under.block_id, source, target, under.version
            )
            scheduled += 1
            result = self._execute_job(job)
            if result.get("ok"):
                executed += 1
            else:
                failed += 1

        for diverged in report.diverged:
            result = self._anti_entropy.repair_divergence(diverged.block_id)
            if result.get("repaired", 0) > 0:
                executed += result["repaired"]

        for over in report.over_replicated:
            if self._remove_extra_replica:
                for extra in over.extra_nodes:
                    self._remove_extra_replica(over.block_id, extra, over.version)

        pending = self._job_store.list_jobs_by_status(RepairStatus.PENDING)
        for job in pending:
            result = self._execute_job(job)
            if result.get("ok"):
                executed += 1
            else:
                failed += 1

        return {
            "scheduled": scheduled,
            "executed": executed,
            "failed": failed,
            "under_replicated": len(report.under_replicated),
            "over_replicated": len(report.over_replicated),
            "diverged": len(report.diverged),
            "orphans": len(report.orphans),
        }

    def reconcile_placements(self) -> dict:
        return self._placement_reconciliation.reconcile()

    def get_cluster_health(self) -> dict:
        report = self.scan_cluster()
        healthy_nodes = self._get_healthy_nodes()
        return {
            "nodes_healthy": len(healthy_nodes),
            "under_replicated_count": len(report.under_replicated),
            "over_replicated_count": len(report.over_replicated),
            "diverged_count": len(report.diverged),
            "orphan_count": len(report.orphans),
            "under_replicated": [b.model_dump() for b in report.under_replicated],
            "over_replicated": [b.model_dump() for b in report.over_replicated],
            "diverged": [b.model_dump() for b in report.diverged],
            "orphans": [b.model_dump() for b in report.orphans],
        }

    def get_cluster_integrity(self) -> dict:
        anti_entropy = self._anti_entropy.verify_cluster()
        reconciliation = self._placement_reconciliation.detect_mismatches()
        return {
            "anti_entropy": anti_entropy,
            "placement_mismatches": {
                "metadata_only": len(reconciliation["metadata_only"]),
                "block_only": len(reconciliation["block_only"]),
            },
            "healthy": anti_entropy["healthy"]
            and not reconciliation["metadata_only"]
            and not reconciliation["block_only"],
        }

    def _execute_job(self, job: RepairJob, missing_node: Optional[str] = None) -> dict:
        if job.attempt_count >= MAX_REPAIR_ATTEMPTS:
            self._job_store.update_job_status(
                job.job_id, RepairStatus.FAILED, last_error="max attempts exceeded"
            )
            if self._metrics:
                self._metrics.inc_repair_jobs_failed()
            return {"ok": False, "job_id": job.job_id, "error": "max attempts exceeded"}

        self._job_store.update_job_status(
            job.job_id, RepairStatus.COPYING, increment_attempt=True
        )
        result = self._re_replication.repair_block(
            block_id=job.block_id,
            version=job.version,
            source_node=job.source_node,
            target_node=job.target_node,
            repair_type=job.repair_type,
        )

        if not result.get("ok"):
            self._job_store.update_job_status(
                job.job_id,
                RepairStatus.FAILED,
                last_error=result.get("error", "repair failed"),
            )
            if self._metrics:
                self._metrics.inc_repair_jobs_failed()
            return result

        self._job_store.update_job_status(job.job_id, RepairStatus.VERIFYING)
        verified = self.verify_repair(job.job_id)
        if verified.get("verified"):
            if missing_node:
                try:
                    self._re_replication._replace_replica(
                        job.block_id, missing_node, job.target_node, job.version
                    )
                except Exception as exc:
                    log.warning("metadata update after repair failed", extra={"error": str(exc)})
            elif job.repair_type == RepairType.RE_REPLICATION:
                locations = self._re_replication._get_block_locations(job.block_id) or []
                old = self._re_replication._find_missing_node(job.block_id, locations)
                if old and old != job.target_node:
                    try:
                        self._re_replication._replace_replica(
                            job.block_id, old, job.target_node, job.version
                        )
                    except Exception as exc:
                        log.warning("metadata update after repair failed", extra={"error": str(exc)})
            return {"ok": True, "job_id": job.job_id, **result}

        self._job_store.update_job_status(
            job.job_id, RepairStatus.FAILED, last_error="verification failed"
        )
        if self._metrics:
            self._metrics.inc_repair_jobs_failed()
        return {"ok": False, "job_id": job.job_id, "error": "verification failed"}

    def _select_replacement(
        self,
        block_id: str,
        current_nodes: List[str],
        healthy_nodes: List[str],
    ) -> Optional[str]:
        available = [n for n in healthy_nodes if n not in current_nodes]
        if not available:
            return None
        try:
            selected = self._placement_policy.select_nodes(available, 1)
            return selected[0]
        except ValueError:
            return available[0] if available else None
