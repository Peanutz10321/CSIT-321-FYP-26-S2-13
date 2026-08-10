"""Recovery of an election the server committed after the client timed out.

``POST /elections/`` generates a 2048-bit Paillier keypair and inserts 50
eligibility rows in one transaction. On a slow deployment that outran the old
30-second client timeout: the client gave up, the server committed anyway, and
the election existed with nothing in the manifest pointing at it. A plain rerun
then created a second election with the same title.

The tests below reproduce that exactly — the fake API handles the POST (so the
election really is stored) and *then* raises ``httpx.ReadTimeout`` — and assert
that the next run adopts the committed election instead of duplicating it.

Fully mocked: every request goes through ``httpx.MockTransport``, and the autouse
guard in conftest makes a client without one an immediate error.
"""

from __future__ import annotations

import json
from uuid import uuid4

import httpx
import pytest

from performance_tests import common, setup_performance_data as setup
from performance_tests.common import ApiError, ManifestError

from .conftest import BATCH, base_env


def run_setup(api, config, data_dir, silent, *, transport=None):
    return setup.run_setup(
        config,
        assume_yes=True,
        transport=transport if transport is not None else api.transport(),
        data_dir=data_dir,
        write=silent,
    )


def load_manifest(data_dir):
    return json.loads(
        common.manifest_path(BATCH, data_dir).read_text(encoding="utf-8")
    )


def election_posts(api):
    return [
        request
        for request in api.requests_to(common.ELECTIONS_PATH)
        if request.method == "POST"
    ]


def timeout_after_commit(api, title):
    """A transport that lets the server commit, then times the client out.

    This is the real failure: the write succeeded and the response never arrived.
    """
    normal = api.handle

    def handler(request: httpx.Request) -> httpx.Response:
        response = normal(request)
        if (
            request.method == "POST"
            and request.url.path == common.ELECTIONS_PATH
            and json.loads(request.content).get("title") == title
        ):
            raise httpx.ReadTimeout("simulated client timeout", request=request)
        return response

    return httpx.MockTransport(handler)


@pytest.fixture
def orphaned_run_two(api, config, data_dir, silent):
    """The FYPLOCAL01 situation: manifest has run 1, the server also has run 2."""
    with pytest.raises(httpx.ReadTimeout):
        run_setup(
            api,
            config,
            data_dir,
            silent,
            transport=timeout_after_commit(api, common.election_title(BATCH, 2)),
        )

    manifest = load_manifest(data_dir)
    assert [e["run"] for e in manifest["elections"]] == [1]
    assert len(api.elections) == 2  # run 1 and the orphaned run 2
    return manifest


def stash_extra_election(api, title, *, status="active", candidates=None):
    """Insert an additional stored election directly, mirroring the fake's shape."""
    election_id = str(uuid4())
    api.elections[election_id] = {
        "response": {
            "id": election_id,
            "organizer_id": str(uuid4()),
            "organizer_username": f"perf_organizer_{BATCH}",
            "title": title,
            "description": None,
            "status": status,
            "ballot_type": "single",
            "max_selections": 1,
            "start_date": "2026-08-10T13:00:00",
            "end_date": "2026-08-30T13:00:00",
            "candidates": candidates
            if candidates is not None
            else [
                {"id": str(uuid4()), "name": name, "display_order": index}
                for index, name in enumerate(common.CANDIDATE_NAMES, start=1)
            ],
        },
        "eligible": [],
        "voted": set(),
    }
    return election_id


# ── The recovery itself ───────────────────────────────────────────────────────


def test_a_committed_election_is_recovered_without_a_post(
    orphaned_run_two, api, config, data_dir, silent
):
    orphaned_id = next(
        election_id
        for election_id, stored in api.elections.items()
        if stored["response"]["title"] == common.election_title(BATCH, 2)
    )
    api.requests.clear()

    run_setup(api, config, data_dir, silent)

    posts = election_posts(api)
    # Only run 3 is created; run 2 is adopted.
    assert len(posts) == 1
    assert posts[0].json_body["title"] == common.election_title(BATCH, 3)

    manifest = load_manifest(data_dir)
    assert [e["run"] for e in manifest["elections"]] == [1, 2, 3]
    assert manifest["elections"][1]["election_id"] == orphaned_id
    assert manifest["elections"][1]["title"] == common.election_title(BATCH, 2)
    assert any("Recovered election 2/3" in line for line in silent.lines)


def test_recovery_searches_by_the_exact_generated_title(
    orphaned_run_two, api, config, data_dir, silent
):
    api.requests.clear()

    run_setup(api, config, data_dir, silent)

    searches = [
        request
        for request in api.requests
        if request.path == common.ACTIVE_ELECTIONS_PATH
    ]
    assert len(searches) == 2  # one per missing run (2 and 3)


def test_no_match_creates_the_election_normally(api, config, data_dir, silent):
    """A fresh batch finds nothing and behaves exactly as before."""
    run_setup(api, config, data_dir, silent)

    posts = election_posts(api)
    assert [p.json_body["title"] for p in posts] == [
        common.election_title(BATCH, run) for run in (1, 2, 3)
    ]
    assert [e["run"] for e in load_manifest(data_dir)["elections"]] == [1, 2, 3]
    assert not any("Recovered election" in line for line in silent.lines)


def test_a_recovered_election_is_fully_validated_against_the_single_election_routes(
    orphaned_run_two, api, config, data_dir, silent
):
    """Recovery re-reads the authoritative routes, not just the search result."""
    orphaned_id = next(
        election_id
        for election_id, stored in api.elections.items()
        if stored["response"]["title"] == common.election_title(BATCH, 2)
    )
    api.requests.clear()

    run_setup(api, config, data_dir, silent)

    assert f"GET /elections/{orphaned_id}" in api.paths
    assert f"GET /elections/{orphaned_id}/voters" in api.paths


def test_setup_continues_to_the_next_run_after_a_recovery(
    orphaned_run_two, api, config, data_dir, silent
):
    run_setup(api, config, data_dir, silent)

    manifest = load_manifest(data_dir)
    assert len(manifest["elections"]) == 3
    assert manifest["elections"][2]["title"] == common.election_title(BATCH, 3)
    assert manifest["elections"][2]["status"] == "active"


def test_a_recovered_manifest_is_written_atomically_and_carries_no_secrets(
    orphaned_run_two, api, config, data_dir, silent, monkeypatch
):
    writes: list[int] = []
    real_save = common.save_manifest

    def spy(manifest, path):
        real_save(manifest, path)
        writes.append(len(manifest["elections"]))

    monkeypatch.setattr(common, "save_manifest", spy)

    run_setup(api, config, data_dir, silent)

    # One checkpoint per election added: the recovered run 2, then the created 3.
    assert writes == [2, 3]
    assert list(data_dir.glob("*.tmp")) == []
    assert common.find_secret_leaks(load_manifest(data_dir)) == []


def test_a_rerun_after_recovery_creates_nothing(
    orphaned_run_two, api, config, data_dir, silent
):
    run_setup(api, config, data_dir, silent)
    api.requests.clear()

    run_setup(api, config, data_dir, silent)

    assert election_posts(api) == []
    assert [e["run"] for e in load_manifest(data_dir)["elections"]] == [1, 2, 3]


# ── Exact matching, not substring ─────────────────────────────────────────────


@pytest.mark.parametrize(
    "decoy_title",
    [
        "PERF-{batch}-RUN-020",  # superstring: search matches, == does not
        "PERF-{batch}-RUN-02-COPY",
        "XPERF-{batch}-RUN-02",
        "perf-{batch}-run-02",  # ilike matches, == does not
        "PERF-{batch}-RUN-02 ",  # trailing space
    ],
)
def test_substring_and_wrong_title_matches_are_ignored(
    api, config, data_dir, silent, decoy_title
):
    """The server's ILIKE is only a narrowing filter; == is what decides."""
    stash_extra_election(api, decoy_title.format(batch=BATCH))
    api.requests.clear()

    run_setup(api, config, data_dir, silent)

    # All three are created normally — the decoy recovered nothing.
    assert len(election_posts(api)) == 3
    assert not any("Recovered election" in line for line in silent.lines)

    manifest = load_manifest(data_dir)
    assert [e["title"] for e in manifest["elections"]] == [
        common.election_title(BATCH, run) for run in (1, 2, 3)
    ]


def test_a_decoy_is_ignored_even_when_the_search_returns_it(
    api, config, data_dir, silent
):
    """Belt and braces: force the endpoint to return only near-miss titles."""
    api.active_elections_override = lambda search: [
        {
            "id": str(uuid4()),
            "title": f"{search}0",
            "status": "active",
            "ballot_type": "single",
            "max_selections": 1,
            "start_date": "2026-08-10T13:00:00",
            "end_date": "2026-08-30T13:00:00",
            "candidates": [],
        }
    ]

    run_setup(api, config, data_dir, silent)

    assert len(election_posts(api)) == 3


# ── Refusals ──────────────────────────────────────────────────────────────────


def test_multiple_exact_matches_are_refused_without_writing(
    orphaned_run_two, api, config, data_dir, silent
):
    duplicate_title = common.election_title(BATCH, 2)
    stash_extra_election(api, duplicate_title)
    before = common.manifest_path(BATCH, data_dir).read_bytes()
    api.requests.clear()

    with pytest.raises(ApiError, match="found 2 active elections already titled"):
        run_setup(api, config, data_dir, silent)

    assert election_posts(api) == []
    assert common.manifest_path(BATCH, data_dir).read_bytes() == before
    assert [e["run"] for e in load_manifest(data_dir)["elections"]] == [1]


def test_three_exact_matches_are_also_refused(
    orphaned_run_two, api, config, data_dir, silent
):
    for _ in range(2):
        stash_extra_election(api, common.election_title(BATCH, 2))

    with pytest.raises(ApiError, match="found 3 active elections"):
        run_setup(api, config, data_dir, silent)


def test_a_match_with_wrong_candidates_is_refused(
    orphaned_run_two, api, config, data_dir, silent
):
    orphaned = next(
        stored
        for stored in api.elections.values()
        if stored["response"]["title"] == common.election_title(BATCH, 2)
    )
    orphaned["response"]["candidates"] = [
        {"id": str(uuid4()), "name": "Someone Else", "display_order": 1},
        {"id": str(uuid4()), "name": "Performance Candidate B", "display_order": 2},
    ]
    before = common.manifest_path(BATCH, data_dir).read_bytes()

    with pytest.raises(ApiError, match="came back with candidates"):
        run_setup(api, config, data_dir, silent)

    assert common.manifest_path(BATCH, data_dir).read_bytes() == before


def test_a_match_with_one_candidate_is_refused(
    orphaned_run_two, api, config, data_dir, silent
):
    orphaned = next(
        stored
        for stored in api.elections.values()
        if stored["response"]["title"] == common.election_title(BATCH, 2)
    )
    orphaned["response"]["candidates"] = orphaned["response"]["candidates"][:1]

    with pytest.raises(ApiError, match="came back with candidates"):
        run_setup(api, config, data_dir, silent)


@pytest.mark.parametrize(
    ("field", "value"),
    [("ballot_type", "multi"), ("max_selections", 2)],
)
def test_a_match_with_wrong_ballot_configuration_is_refused(
    orphaned_run_two, api, config, data_dir, silent, field, value
):
    orphaned = next(
        stored
        for stored in api.elections.values()
        if stored["response"]["title"] == common.election_title(BATCH, 2)
    )
    orphaned["response"][field] = value
    before = common.manifest_path(BATCH, data_dir).read_bytes()

    with pytest.raises(ManifestError, match="does not match"):
        run_setup(api, config, data_dir, silent)

    assert common.manifest_path(BATCH, data_dir).read_bytes() == before


def test_a_match_with_wrong_eligibility_is_refused(
    orphaned_run_two, api, config, data_dir, silent
):
    orphaned = next(
        stored
        for stored in api.elections.values()
        if stored["response"]["title"] == common.election_title(BATCH, 2)
    )
    orphaned["eligible"] = orphaned["eligible"][:49]
    before = common.manifest_path(BATCH, data_dir).read_bytes()

    with pytest.raises(ManifestError, match="eligible voters differ"):
        run_setup(api, config, data_dir, silent)

    assert common.manifest_path(BATCH, data_dir).read_bytes() == before


def test_a_match_owned_by_another_organizer_is_refused(
    orphaned_run_two, api, config, data_dir, silent
):
    orphaned = next(
        stored
        for stored in api.elections.values()
        if stored["response"]["title"] == common.election_title(BATCH, 2)
    )
    orphaned["response"]["organizer_username"] = "somebody_else"

    with pytest.raises(ManifestError, match="organizer is"):
        run_setup(api, config, data_dir, silent)


def test_a_failed_search_stops_the_run(api, config, data_dir, silent):
    api.active_elections_override = lambda search: None
    normal = api.handle

    def broken_search(request: httpx.Request) -> httpx.Response:
        if request.url.path == common.ACTIVE_ELECTIONS_PATH:
            return httpx.Response(500, json={"detail": "boom"})
        return normal(request)

    with pytest.raises(ApiError, match="could not check for an already-committed"):
        run_setup(
            api, config, data_dir, silent, transport=httpx.MockTransport(broken_search)
        )

    assert election_posts(api) == []


# ── Timeout ───────────────────────────────────────────────────────────────────


def test_setup_uses_the_longer_timeout(monkeypatch, api, config, data_dir, silent):
    seen: list[float | None] = []
    real_build = common.build_client

    def spy(base_url, **kwargs):
        seen.append(kwargs.get("timeout"))
        return real_build(base_url, **kwargs)

    monkeypatch.setattr(common, "build_client", spy)

    run_setup(api, config, data_dir, silent)

    assert seen == [120.0]
    assert common.SETUP_TIMEOUT_SECONDS == 120.0


def test_the_default_client_timeout_is_unchanged(api):
    """Only setup gets the longer timeout; verification keeps the default."""
    import inspect

    assert inspect.signature(common.build_client).parameters["timeout"].default == 30.0


# ── No network ────────────────────────────────────────────────────────────────


def test_recovery_cannot_build_a_client_without_a_mock_transport(config):
    with pytest.raises(AssertionError, match="never touch the network"):
        common.build_client(config.base_url, timeout=common.SETUP_TIMEOUT_SECONDS)


def test_every_recovery_request_went_through_the_mock_transport(
    orphaned_run_two, api, config, data_dir, silent
):
    api.requests.clear()

    run_setup(api, config, data_dir, silent)

    # The fake recorded everything, so nothing escaped to a real host.
    assert api.requests
    assert all(
        request.path.startswith(("/elections", "/auth", "/health", "/votes", "/users"))
        for request in api.requests
    )
