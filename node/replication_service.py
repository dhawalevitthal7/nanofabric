"""Orchestrates primary-to-replica write and delete replication."""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Tuple

from node.metadata_client import MetadataClient
from node.metrics import Metrics
from node.replica_client import ReplicaClient, ReplicaClientError
from node.replica_manager import ReplicaManager
from node.replication_job_store import ReplicationJobStore
from node.replication_models import (
    JobStatus,
    ReplicateDeleteRequest,
    ReplicateRequest,
    ReplicationJob,
    ReplicationState,
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
    ):
        self._node_id = node_id
        self._metadata = metadata_client
        self._replica_client = replica_client
        self._replica_manager = replica_manager
        self._job_store = job_store
        self._metrics = metrics

    @property
    def node_id(self) -> str:
        return self._node_id

    def replicate_write(
        self,
        block_id: str,
        data: str,
        version: int,
        lsn: int,
    ) -> ReplicationState:
        locations = self._metadata.get_block_locations(block_id)
        if not locations:
            log.info(
                "no placement for block, skipping replication",
                extra={"block_id": block_id},
            )
            return ReplicationState.REPLICATED

        if self._node_id not in locations:
            log.warning(
                "this node is not in placement, skipping replication",
                extra={"block_id": block_id, "locations": locations},
            )
            return ReplicationState.REPLICATED

        replicas = [n for n in locations if n != self._node_id]
        if not replicas:
            self._replica_manager.mark_pending(block_id, version, locations)
            self._replica_manager.mark_replicated(block_id)
            return ReplicationState.REPLICATED

        self._replica_manager.mark_pending(block_id, version, locations)
        self._replica_manager.mark_replicating(block_id)

        jobs = self._create_jobs(block_id, version, lsn, data, replicas, is_delete=False)
        results = self._send_write_replications(block_id, data, version, lsn, jobs)
        return self._finalize_state(block_id, results)

    def replicate_delete(
        self,
        block_id: str,
        version: int,
        lsn: int,
    ) -> ReplicationState:
        locations = self._metadata.get_block_locations(block_id)
        if not locations or self._node_id not in locations:
            return ReplicationState.REPLICATED

        replicas = [n for n in locations if n != self._node_id]
        if not replicas:
            self._replica_manager.mark_replicated(block_id)
            return ReplicationState.REPLICATED

        self._replica_manager.mark_pending(block_id, version, locations)
        self._replica_manager.mark_replicating(block_id)

        jobs = self._create_jobs(block_id, version, lsn, None, replicas, is_delete=True)
        results = self._send_delete_replications(block_id, version, lsn, jobs)
        return self._finalize_state(block_id, results)

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
    ) -> ReplicationState:
        if not results:
            self._replica_manager.mark_replicated(block_id)
            return ReplicationState.REPLICATED

        successes = sum(1 for _, ok, _ in results if ok)
        if successes == len(results):
            self._replica_manager.mark_replicated(block_id)
            return ReplicationState.REPLICATED
        if successes == 0:
            self._replica_manager.mark_failed(block_id)
            return ReplicationState.FAILED

        self._metrics.inc_degraded_replications()
        self._replica_manager.mark_degraded(block_id)
        return ReplicationState.DEGRADED

    def _update_block_state_from_jobs(self, block_id: str) -> None:
        jobs = [
            j for j in self._job_store.list_all_jobs() if j.block_id == block_id
        ]
        if not jobs:
            return
        latest_version = max(j.version for j in jobs)
        version_jobs = [j for j in jobs if j.version == latest_version]
        successes = sum(1 for j in version_jobs if j.status == JobStatus.SUCCESS)
        if successes == len(version_jobs):
            self._replica_manager.mark_replicated(block_id)
        elif successes == 0:
            self._replica_manager.mark_failed(block_id)
        else:
            self._replica_manager.mark_degraded(block_id)
