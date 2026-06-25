"""Orchestrates primary-to-replica write and delete replication with quorum."""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Tuple

from node.consistency import ConsistencyLevel
from node.hinted_handoff import HintedHandoff
from node.metadata_client import MetadataClient
from node.metrics import Metrics
from node.quorum import is_quorum_satisfied, required_acks
from node.quorum_manager import QuorumManager, QuorumOutcome
from node.replica_client import ReplicaClient, ReplicaClientError
from node.replica_manager import ReplicaManager
from node.replication_job_store import ReplicationJobStore
from node.replication_models import (
    JobStatus,
    ReplicateDeleteRequest,
    ReplicateRequest,
    ReplicationJob,
    ReplicationState,
    WriteQuorumResult,
)

log = logging.getLogger(__name__)


class ReplicationService:

    def __init__(
        self,
        node_id: str,
        metadata_client: MetadataClient,
        replica_client: ReplicaClient,
        replica_manager: ReplicaManager,
        job_store: ReplicationJobStore,
        metrics: Metrics,
        hinted_handoff: Optional[HintedHandoff] = None,
        consistency: ConsistencyLevel = ConsistencyLevel.QUORUM,
    ):
        self._node_id = node_id
        self._metadata = metadata_client
        self._replica_client = replica_client
        self._replica_manager = replica_manager
        self._job_store = job_store
        self._metrics = metrics
        self._hinted_handoff = hinted_handoff
        self._consistency = consistency
        self._last_quorum_snapshot: Optional[dict] = None

    @property
    def node_id(self) -> str:
        return self._node_id

    @property
    def consistency(self) -> ConsistencyLevel:
        return self._consistency

    def set_consistency(self, level: ConsistencyLevel) -> None:
        self._consistency = level

    def get_last_quorum_snapshot(self) -> Optional[dict]:
        return self._last_quorum_snapshot

    def replicate_write(
        self,
        block_id: str,
        data: str,
        version: int,
        lsn: int,
    ) -> WriteQuorumResult:
        locations = self._metadata.get_block_locations(block_id)
        if not locations:
            log.info(
                "no placement for block, skipping replication",
                extra={"block_id": block_id},
            )
            return self._local_only_result(block_id, locations or [self._node_id])

        if self._node_id not in locations:
            log.warning(
                "this node is not in placement, skipping replication",
                extra={"block_id": block_id, "locations": locations},
            )
            return self._local_only_result(block_id, locations)

        replicas = [n for n in locations if n != self._node_id]
        rf = len(locations)
        quorum_mgr = QuorumManager(rf, self._consistency)
        quorum_mgr.record_ack(self._node_id)

        if not replicas:
            self._replica_manager.mark_pending(block_id, version, locations)
            self._replica_manager.mark_replicated(block_id)
            return self._build_result(quorum_mgr, ReplicationState.REPLICATED, locations)

        self._replica_manager.mark_pending(block_id, version, locations)
        self._replica_manager.mark_replicating(block_id)

        jobs = self._create_jobs(block_id, version, lsn, data, replicas, is_delete=False)
        results = self._send_write_replications(block_id, data, version, lsn, jobs)

        for target, ok, _ in results:
            if ok:
                quorum_mgr.record_ack(target)
            else:
                quorum_mgr.record_failure(target)
                if self._hinted_handoff is not None:
                    self._hinted_handoff.store_hint(
                        target_node=target,
                        block_id=block_id,
                        version=version,
                        data=data,
                        lsn=lsn,
                    )

        state = self._finalize_state(block_id, results, quorum_mgr)
        result = self._build_result(quorum_mgr, state, locations)
        self._metrics.record_quorum_latency(quorum_mgr.latency_ms())
        self._last_quorum_snapshot = result.model_dump()
        return result

    def replicate_delete(
        self,
        block_id: str,
        version: int,
        lsn: int,
    ) -> WriteQuorumResult:
        locations = self._metadata.get_block_locations(block_id)
        if not locations or self._node_id not in locations:
            return self._local_only_result(block_id, locations or [self._node_id])

        replicas = [n for n in locations if n != self._node_id]
        rf = len(locations)
        quorum_mgr = QuorumManager(rf, self._consistency)
        quorum_mgr.record_ack(self._node_id)

        if not replicas:
            self._replica_manager.mark_replicated(block_id)
            return self._build_result(quorum_mgr, ReplicationState.REPLICATED, locations)

        self._replica_manager.mark_pending(block_id, version, locations)
        self._replica_manager.mark_replicating(block_id)

        jobs = self._create_jobs(block_id, version, lsn, None, replicas, is_delete=True)
        results = self._send_delete_replications(block_id, version, lsn, jobs)

        for target, ok, _ in results:
            if ok:
                quorum_mgr.record_ack(target)
            else:
                quorum_mgr.record_failure(target)
                if self._hinted_handoff is not None:
                    self._hinted_handoff.store_hint(
                        target_node=target,
                        block_id=block_id,
                        version=version,
                        data="",
                        lsn=lsn,
                        is_delete=True,
                    )

        state = self._finalize_state(block_id, results, quorum_mgr)
        result = self._build_result(quorum_mgr, state, locations)
        self._metrics.record_quorum_latency(quorum_mgr.latency_ms())
        self._last_quorum_snapshot = result.model_dump()
        return result

    def wait_for_acks(
        self,
        jobs: List[ReplicationJob],
        block_id: str,
        data: Optional[str],
        version: int,
        lsn: int,
        is_delete: bool = False,
    ) -> List[Tuple[str, bool, Optional[str]]]:
        if is_delete:
            return self._send_delete_replications(block_id, version, lsn, jobs)
        return self._send_write_replications(block_id, data, version, lsn, jobs)

    def retry_failed_replications(self) -> int:
        jobs = self._job_store.list_pending_and_failed()
        retried = 0
        for job in jobs:
            if job.primary_node != self._node_id:
                continue
            retried += 1
            self._metrics.inc_replication_retries()
            if job.is_delete:
                self._execute_delete_job(job)
            else:
                self._execute_write_job(job)
            self._update_block_state_from_jobs(job.block_id)
        return retried

    def recover_pending_jobs(self) -> int:
        return self.retry_failed_replications()

    def get_consistency_info(self, block_id: str) -> dict:
        locations = self._metadata.get_block_locations(block_id)
        rf = len(locations) if locations else 1
        from node.quorum import calculate_read_quorum, calculate_write_quorum

        return {
            "consistency_level": self._consistency.value,
            "replication_factor": rf,
            "write_quorum": calculate_write_quorum(rf),
            "read_quorum": calculate_read_quorum(rf),
            "locations": locations or [],
        }

    def _local_only_result(
        self, block_id: str, locations: List[str]
    ) -> WriteQuorumResult:
        rf = max(len(locations), 1)
        quorum_mgr = QuorumManager(rf, ConsistencyLevel.ONE)
        quorum_mgr.record_ack(self._node_id)
        return self._build_result(quorum_mgr, ReplicationState.REPLICATED, locations)

    def _build_result(
        self,
        quorum_mgr: QuorumManager,
        state: ReplicationState,
        locations: List[str],
    ) -> WriteQuorumResult:
        outcome = quorum_mgr.evaluate()
        satisfied = outcome == QuorumOutcome.SUCCESS
        if not satisfied and state != ReplicationState.REPLICATED:
            self._metrics.inc_write_quorum_failures()
        return WriteQuorumResult(
            state=state,
            quorum_satisfied=satisfied,
            ack_count=quorum_mgr.ack_count,
            required_acks=quorum_mgr.required_acks,
            replication_factor=len(locations) if locations else 1,
            acked_nodes=quorum_mgr.acked_nodes,
            failed_nodes=quorum_mgr.failed_nodes,
            outcome=outcome.value,
            latency_ms=round(quorum_mgr.latency_ms(), 3),
        )

    def _create_jobs(
        self,
        block_id: str,
        version: int,
        lsn: int,
        data: Optional[str],
        replicas: List[str],
        is_delete: bool,
    ) -> List[ReplicationJob]:
        jobs = []
        for target in replicas:
            job = self._job_store.create_job(
                block_id=block_id,
                version=version,
                primary_node=self._node_id,
                target_node=target,
                lsn=lsn,
                data=data,
                is_delete=is_delete,
            )
            jobs.append(job)
        return jobs

    def _send_write_replications(
        self,
        block_id: str,
        data: str,
        version: int,
        lsn: int,
        jobs: List[ReplicationJob],
    ) -> List[Tuple[str, bool, Optional[str]]]:
        return self._parallel_execute(jobs, lambda job: self._execute_write_job(job))

    def _send_delete_replications(
        self,
        block_id: str,
        version: int,
        lsn: int,
        jobs: List[ReplicationJob],
    ) -> List[Tuple[str, bool, Optional[str]]]:
        return self._parallel_execute(jobs, lambda job: self._execute_delete_job(job))

    def _parallel_execute(self, jobs, executor_fn):
        results: List[Tuple[str, bool, Optional[str]]] = []
        if not jobs:
            return results
        with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
            futures = {pool.submit(executor_fn, job): job for job in jobs}
            for future in as_completed(futures):
                job = futures[future]
                try:
                    success, error = future.result()
                    results.append((job.target_node, success, error))
                except Exception as exc:
                    results.append((job.target_node, False, str(exc)))
        return results

    def _execute_write_job(self, job: ReplicationJob) -> Tuple[bool, Optional[str]]:
        start = time.perf_counter()
        self._job_store.update_job_status(
            job.job_id, JobStatus.IN_PROGRESS, increment_attempt=True
        )
        try:
            addresses = self._metadata.get_node_addresses()
            target_url = self._metadata.resolve_node_url(job.target_node, addresses)
            request = ReplicateRequest(
                block_id=job.block_id,
                data=job.data or "",
                version=job.version,
                lsn=job.lsn,
                origin_node_id=self._node_id,
            )
            self._replica_client.replicate_write(target_url, job.target_node, request)
            elapsed_ms = (time.perf_counter() - start) * 1000
            self._metrics.record_replication_latency(elapsed_ms)
            self._metrics.inc_successful_replications()
            self._job_store.update_job_status(job.job_id, JobStatus.SUCCESS)
            return True, None
        except ReplicaClientError as exc:
            self._metrics.inc_failed_replications()
            self._job_store.update_job_status(
                job.job_id, JobStatus.FAILED, last_error=str(exc)
            )
            return False, str(exc)
        except Exception as exc:
            self._metrics.inc_failed_replications()
            self._job_store.update_job_status(
                job.job_id, JobStatus.FAILED, last_error=str(exc)
            )
            return False, str(exc)

    def _execute_delete_job(self, job: ReplicationJob) -> Tuple[bool, Optional[str]]:
        start = time.perf_counter()
        self._job_store.update_job_status(
            job.job_id, JobStatus.IN_PROGRESS, increment_attempt=True
        )
        try:
            addresses = self._metadata.get_node_addresses()
            target_url = self._metadata.resolve_node_url(job.target_node, addresses)
            request = ReplicateDeleteRequest(
                block_id=job.block_id,
                version=job.version,
                lsn=job.lsn,
                origin_node_id=self._node_id,
            )
            self._replica_client.replicate_delete(target_url, job.target_node, request)
            elapsed_ms = (time.perf_counter() - start) * 1000
            self._metrics.record_replication_latency(elapsed_ms)
            self._metrics.inc_successful_replications()
            self._job_store.update_job_status(job.job_id, JobStatus.SUCCESS)
            return True, None
        except ReplicaClientError as exc:
            self._metrics.inc_failed_replications()
            self._job_store.update_job_status(
                job.job_id, JobStatus.FAILED, last_error=str(exc)
            )
            return False, str(exc)
        except Exception as exc:
            self._metrics.inc_failed_replications()
            self._job_store.update_job_status(
                job.job_id, JobStatus.FAILED, last_error=str(exc)
            )
            return False, str(exc)

    def _finalize_state(
        self,
        block_id: str,
        results: List[Tuple[str, bool, Optional[str]]],
        quorum_mgr: QuorumManager,
    ) -> ReplicationState:
        if not results:
            self._replica_manager.mark_replicated(block_id)
            return ReplicationState.REPLICATED

        outcome = quorum_mgr.evaluate()
        if outcome == QuorumOutcome.SUCCESS:
            if quorum_mgr.failure_count > 0:
                self._metrics.inc_degraded_replications()
                self._replica_manager.mark_degraded(block_id)
            else:
                self._replica_manager.mark_replicated(block_id)
            return ReplicationState.REPLICATED

        if quorum_mgr.ack_count == 0:
            self._replica_manager.mark_failed(block_id)
            return ReplicationState.FAILED

        self._replica_manager.mark_failed(block_id)
        return ReplicationState.FAILED

    def _update_block_state_from_jobs(self, block_id: str) -> None:
        jobs = [
            j for j in self._job_store.list_all_jobs() if j.block_id == block_id
        ]
        if not jobs:
            return
        latest_version = max(j.version for j in jobs)
        version_jobs = [j for j in jobs if j.version == latest_version]
        successes = sum(1 for j in version_jobs if j.status == JobStatus.SUCCESS)
        primary_node = version_jobs[0].primary_node
        locations = [primary_node] + [j.target_node for j in version_jobs]
        rf = len(set(locations))
        required = required_acks(rf, self._consistency)
        if is_quorum_satisfied(successes + 1, required):
            if successes < len(version_jobs):
                self._replica_manager.mark_degraded(block_id)
            else:
                self._replica_manager.mark_replicated(block_id)
        elif successes == 0:
            self._replica_manager.mark_failed(block_id)
        else:
            self._replica_manager.mark_failed(block_id)
