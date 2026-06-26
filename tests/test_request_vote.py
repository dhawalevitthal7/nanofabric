"""Tests for Raft RequestVote RPC."""

import pytest

from metadata.raft.models import RequestVoteRequest, RaftRole
from raft_helpers import InMemoryRaftCluster


@pytest.fixture
def raft_cluster(tmp_path):
    cluster = InMemoryRaftCluster(tmp_path)
    yield cluster
    cluster.stop_all()


def test_grant_vote_to_up_to_date_candidate(raft_cluster):
    follower = raft_cluster.nodes["metadata2"]
    req = RequestVoteRequest(
        term=5,
        candidate_id="metadata1",
        last_log_index=0,
        last_log_term=0,
    )
    resp = follower.handle_request_vote(req)
    assert resp.vote_granted is True
    assert resp.term == 5
    assert follower.voted_for == "metadata1"


def test_deny_vote_for_stale_term(raft_cluster):
    leader_id = raft_cluster.wait_for_leader()
    leader = raft_cluster.nodes[leader_id]
    term = leader.current_term

    follower = raft_cluster.nodes["metadata3"]
    req = RequestVoteRequest(
        term=term - 1,
        candidate_id="metadata1",
        last_log_index=0,
        last_log_term=0,
    )
    resp = follower.handle_request_vote(req)
    assert resp.vote_granted is False


def test_only_one_vote_per_term(raft_cluster):
    follower = raft_cluster.nodes["metadata2"]
    req1 = RequestVoteRequest(term=10, candidate_id="metadata1", last_log_index=0, last_log_term=0)
    req2 = RequestVoteRequest(term=10, candidate_id="metadata3", last_log_index=0, last_log_term=0)

    assert follower.handle_request_vote(req1).vote_granted is True
    assert follower.handle_request_vote(req2).vote_granted is False


def test_request_vote_http_endpoint(tmp_path):
    from fastapi.testclient import TestClient

    from metadata.app import create_app
    from metadata.raft.config import RaftConfig

    config = RaftConfig(
        enabled=True,
        node_id="metadata1",
        peer_urls={"metadata1": "http://localhost:9001"},
        election_min_ms=200,
        election_max_ms=300,
    )
    app = create_app(db_path=tmp_path / "meta.db", raft_config=config)
    app.state.start_repair_worker = False
    with TestClient(app) as client:
        resp = client.post(
            "/raft/request-vote",
            json={
                "term": 2,
                "candidate_id": "metadata2",
                "last_log_index": 0,
                "last_log_term": 0,
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "vote_granted" in body
        assert "term" in body
