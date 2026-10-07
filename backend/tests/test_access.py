from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient

from vibrato.config import Settings, configure, get_settings

from .conftest import sign_in_owner, wav_bytes


def tone(seconds: float = 1.0, hz: float = 220.0) -> bytes:
    t = np.linspace(0, seconds, int(44100 * seconds), endpoint=False)
    return wav_bytes(0.2 * np.sin(2 * np.pi * hz * t))


class TesterClient(TestClient):
    user_id: str = ""


class Site:
    def __init__(self, app: Any, owner: TestClient) -> None:
        self.app = app
        self.owner = owner

    def tester(self, name: str = "Tester") -> TesterClient:
        invite = self.owner.post("/api/auth/invites", json={"display_name": name}).json()["invite"]
        client = TesterClient(self.app)
        response = client.get(f"/api/auth/claim/{invite['code']}", follow_redirects=False)
        assert response.status_code == 302 and response.headers["location"] == "/"
        client.user_id = invite["user_id"]
        return client


@pytest.fixture(scope="module")
def site(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Site]:
    from vibrato.api.app import create_app

    app = create_app(Settings(data_dir=tmp_path_factory.mktemp("access") / "data", workers=2))
    with TestClient(app) as owner:
        sign_in_owner(owner)
        yield Site(app, owner)


def limits(**overrides: Any) -> Settings:
    previous = get_settings()
    configure(replace(previous, **overrides))
    return previous


def upload(client: TestClient, project_id: str, data: bytes | None = None, **form: str) -> Any:
    return client.post(
        f"/api/projects/{project_id}/recordings",
        data={"kind": "take", "auto_analyze": "false", **form},
        files={"file": ("t.wav", data if data is not None else tone(), "audio/wav")},
    )


def test_anonymous_requests_are_rejected_but_health_is_public(site: Site) -> None:
    anon = TestClient(site.app)
    assert anon.get("/api/health").status_code == 200
    for path in ("/api/projects", "/api/preferences", "/api/tasks", "/api/auth/me", "/api/system"):
        assert anon.get(path).status_code == 401, path


def test_api_docs_are_hidden(site: Site) -> None:
    assert site.owner.get("/api/docs").status_code == 404
    assert site.owner.get("/api/openapi.json").status_code == 404


def test_invite_links_are_single_use(site: Site) -> None:
    invite = site.owner.post("/api/auth/invites", json={"display_name": "Once"}).json()["invite"]
    first = TestClient(site.app).get(f"/api/auth/claim/{invite['code']}", follow_redirects=False)
    assert first.headers["location"] == "/"
    second = TestClient(site.app).get(f"/api/auth/claim/{invite['code']}", follow_redirects=False)
    assert second.status_code == 302 and second.headers["location"] == "/?invite=invalid"
    bogus = TestClient(site.app).get("/api/auth/claim/inv_nope", follow_redirects=False)
    assert bogus.headers["location"] == "/?invite=invalid"


def test_tester_invites_never_expire_but_stay_single_use(site: Site) -> None:
    from vibrato.db import get_db

    invite = site.owner.post("/api/auth/invites", json={"display_name": "Patient"}).json()["invite"]
    with get_db().tx() as conn:
        conn.execute("UPDATE invites SET created_at = '2000-01-01T00:00:00.000+00:00' WHERE code = ?", (invite["code"],))
    first = TestClient(site.app).get(f"/api/auth/claim/{invite['code']}", follow_redirects=False)
    assert first.headers["location"] == "/"
    second = TestClient(site.app).get(f"/api/auth/claim/{invite['code']}", follow_redirects=False)
    assert second.headers["location"] == "/?invite=invalid"


def test_expired_owner_invites_are_rejected(site: Site) -> None:
    from vibrato.db import get_db

    with get_db().tx() as conn:
        owner = conn.execute("SELECT id FROM users WHERE is_owner = 1").fetchone()["id"]
        conn.execute("DELETE FROM invites WHERE user_id = ?", (owner,))
        conn.execute(
            "INSERT INTO invites (code, user_id, created_at) VALUES ('inv_old', ?, '2000-01-01T00:00:00.000+00:00')",
            (owner,),
        )
    response = TestClient(site.app).get("/api/auth/claim/inv_old", follow_redirects=False)
    assert response.headers["location"] == "/?invite=invalid"


def test_testers_are_isolated_from_each_other_and_the_owner(site: Site) -> None:
    owner_project = site.owner.post("/api/projects", json={"name": "Owner only"}).json()["project"]
    alice, bob = site.tester("Alice"), site.tester("Bob")
    alice_project = alice.post("/api/projects", json={"name": "Alice's"}).json()["project"]
    rec = upload(alice, alice_project["id"]).json()["recording"]

    assert [p["name"] for p in bob.get("/api/projects").json()["projects"]] == []
    for path in (
        f"/api/projects/{owner_project['id']}",
        f"/api/projects/{alice_project['id']}",
        f"/api/recordings/{rec['id']}",
        f"/api/recordings/{rec['id']}/audio",
    ):
        assert bob.get(path).status_code == 404, path
    assert bob.delete(f"/api/projects/{alice_project['id']}").status_code == 404
    assert bob.patch(f"/api/recordings/{rec['id']}", json={"name": "pwned"}).status_code == 404

    names = {p["name"] for p in site.owner.get("/api/projects").json()["projects"]}
    assert {"Owner only", "Alice's"} <= names


def test_admin_routes_are_owner_only(site: Site) -> None:
    tester = site.tester()
    for method, path in (
        ("get", "/api/system"),
        ("get", "/api/system/logs"),
        ("post", "/api/system/cache/clear"),
        ("post", "/api/system/reanalyze"),
        ("get", "/api/auth/users"),
        ("post", "/api/auth/invites"),
    ):
        response = getattr(tester, method)(path, **({"json": {}} if method == "post" else {}))
        assert response.status_code == 403, path


def test_revoke_ends_sessions_and_new_link_restores_access(site: Site) -> None:
    tester = site.tester("Revokee")
    assert tester.get("/api/auth/me").status_code == 200
    assert site.owner.post(f"/api/auth/users/{tester.user_id}/revoke").status_code == 200
    assert tester.get("/api/auth/me").status_code == 401
    users = {u["id"]: u for u in site.owner.get("/api/auth/users").json()["users"]}
    assert users[tester.user_id]["disabled"] == 1 and users[tester.user_id]["active_sessions"] == 0

    invite = site.owner.post(f"/api/auth/users/{tester.user_id}/link").json()["invite"]
    again = TestClient(site.app)
    assert again.get(f"/api/auth/claim/{invite['code']}", follow_redirects=False).headers["location"] == "/"
    assert again.get("/api/auth/me").json()["user"]["id"] == tester.user_id
    assert tester.get("/api/auth/me").status_code == 401


def test_new_link_invalidates_other_sessions_for_that_tester(site: Site) -> None:
    tester = site.tester("Leaky")
    site.owner.post(f"/api/auth/users/{tester.user_id}/link")
    assert tester.get("/api/auth/me").status_code == 401


def test_owner_can_rotate_own_link_without_locking_themselves_out(site: Site) -> None:
    owner_id = site.owner.get("/api/auth/me").json()["user"]["id"]
    other_owner_session = TestClient(site.app)
    sign_in_owner(other_owner_session)
    invite = site.owner.post(f"/api/auth/users/{owner_id}/link").json()["invite"]
    assert invite["code"].startswith("inv_")
    assert site.owner.get("/api/auth/me").status_code == 200
    assert other_owner_session.get("/api/auth/me").status_code == 401
    assert site.owner.post(f"/api/auth/users/{owner_id}/revoke").status_code == 403


def test_project_quota(site: Site) -> None:
    tester = site.tester()
    previous = limits(tester_max_projects=2)
    try:
        for name in ("a", "b"):
            assert tester.post("/api/projects", json={"name": name}).status_code == 200
        blocked = tester.post("/api/projects", json={"name": "c"})
        assert blocked.status_code == 429 and blocked.json()["error"]["code"] == "quota_exceeded"
        pid = tester.get("/api/projects").json()["projects"][0]["id"]
        assert tester.post(f"/api/projects/{pid}/duplicate").status_code == 429
        assert site.owner.post("/api/projects", json={"name": "owner is exempt"}).status_code == 200
    finally:
        configure(previous)


def test_storage_quota(site: Site) -> None:
    tester = site.tester()
    pid = tester.post("/api/projects", json={"name": "quota"}).json()["project"]["id"]
    previous = limits(tester_storage_bytes=150_000)
    try:
        assert upload(tester, pid, tone(1.0, 220)).status_code == 200
        blocked = upload(tester, pid, tone(1.0, 330))
        assert blocked.status_code == 429
        assert len(tester.get(f"/api/projects/{pid}/recordings").json()["recordings"]) == 1
    finally:
        configure(previous)


def test_task_capacity(site: Site) -> None:
    tester = site.tester()
    pid = tester.post("/api/projects", json={"name": "busy"}).json()["project"]["id"]
    rec = upload(tester, pid).json()["recording"]
    previous = limits(tester_max_active_tasks=0)
    try:
        assert tester.post(f"/api/recordings/{rec['id']}/analyze", json={}).status_code == 429
        assert upload(tester, pid, tone(1.0, 440), auto_analyze="true").status_code == 429
        assert tester.post("/api/demo").status_code == 429
    finally:
        configure(previous)


def test_calibration_changes_do_not_leak_across_accounts(site: Site) -> None:
    from vibrato.db import get_db

    owner_id = site.owner.get("/api/auth/me").json()["user"]["id"]
    tester = site.tester()
    with get_db().tx() as conn:
        conn.execute(
            "INSERT INTO calibration_profiles (id, name, status, is_active, owner_id, created_at) "
            "VALUES ('cal_owner', 'Owner cal', 'complete', 1, ?, '2026-01-01T00:00:00.000+00:00'), "
            "('cal_tester', 'Tester cal', 'complete', 0, ?, '2026-01-01T00:00:00.000+00:00')",
            (owner_id, tester.user_id),
        )
    assert tester.post("/api/calibrations/cal_tester/activate").json()["active"]["id"] == "cal_tester"
    assert tester.post("/api/calibrations/deactivate").status_code == 200
    assert site.owner.get("/api/calibrations").json()["active"]["id"] == "cal_owner"
    assert tester.post("/api/calibrations/cal_owner/activate").status_code == 404


def test_cross_account_references_are_rejected(site: Site) -> None:
    owner_pid = site.owner.post("/api/projects", json={"name": "ref owner"}).json()["project"]["id"]
    owner_ref = upload(site.owner, owner_pid, kind="reference").json()["recording"]
    owner_profile = site.owner.post("/api/reference-profiles", json={"name": "owner profile"}).json()["profile"]

    tester = site.tester()
    pid = tester.post("/api/projects", json={"name": "mine"}).json()["project"]["id"]
    take = upload(tester, pid).json()["recording"]

    assert tester.patch(f"/api/projects/{pid}", json={"reference_profile_id": owner_profile["id"]}).status_code == 404
    assert tester.patch(f"/api/recordings/{take['id']}", json={"reference_profile_id": owner_profile["id"]}).status_code == 404
    assert tester.patch(f"/api/recordings/{take['id']}", json={"reference_recording_id": owner_ref["id"]}).status_code == 404
    assert upload(tester, pid, tone(1.0, 550), reference_id=owner_ref["id"]).status_code == 404
    assert tester.post("/api/comparisons", json={"take_id": take["id"], "reference_id": owner_ref["id"]}).status_code == 404
    assert tester.get(f"/api/projects/{pid}/progress", params={"reference_id": owner_ref["id"]}).status_code == 404


def test_chunked_upload_limits(site: Site) -> None:
    from vibrato.api.routes import uploads

    tester = site.tester()
    pid = tester.post("/api/projects", json={"name": "chunks"}).json()["project"]["id"]
    data = tone(2.0)
    upload_id = tester.post("/api/uploads", json={"filename": "t.wav"}).json()["upload_id"]
    half = len(data) // 2
    assert tester.put(f"/api/uploads/{upload_id}/chunk/0", content=data[:half]).status_code == 200
    assert tester.put(f"/api/uploads/{upload_id}/chunk/1", content=data[half:]).status_code == 200
    done = tester.post(f"/api/uploads/{upload_id}/complete", json={"total_chunks": 2}).json()
    assert done["size_bytes"] == len(data)
    created = tester.post(
        f"/api/projects/{pid}/recordings", data={"upload_id": upload_id, "kind": "take", "auto_analyze": "false"}
    )
    assert created.status_code == 200 and created.json()["recording"]["size_bytes"] == len(data)

    stranger = site.tester()
    other = tester.post("/api/uploads", json={"filename": "t.wav"}).json()["upload_id"]
    assert stranger.put(f"/api/uploads/{other}/chunk/0", content=b"x").status_code == 403
    assert tester.put(f"/api/uploads/{other}/chunk/-1", content=b"x").status_code == 404
    assert tester.put(f"/api/uploads/{other}/chunk/{uploads.MAX_CHUNKS}", content=b"x").status_code == 404

    original = uploads.MAX_CHUNK_BYTES
    uploads.MAX_CHUNK_BYTES = 10
    try:
        assert tester.put(f"/api/uploads/{other}/chunk/0", content=b"x" * 11).status_code == 413
    finally:
        uploads.MAX_CHUNK_BYTES = original

    for _ in range(uploads.MAX_PENDING_PER_USER - 1):
        tester.post("/api/uploads", json={"filename": "t.wav"})
    assert tester.post("/api/uploads", json={"filename": "t.wav"}).status_code == 429


def test_derived_cache_variants_are_bounded(site: Site) -> None:
    from vibrato.storage import stretched_path

    tester = site.tester()
    pid = tester.post("/api/projects", json={"name": "cache"}).json()["project"]["id"]
    rec = upload(tester, pid).json()["recording"]
    for speed in (0.7501, 0.7499, 0.76, 0.74):
        response = tester.get(f"/api/recordings/{rec['id']}/stretched", params={"speed": speed})
        assert response.status_code == 200 and response.headers["x-stretch-factor"] == "1.3333"
    cache_dir = Path(stretched_path(rec["content_hash"], 1.0)).parent
    assert len(list(cache_dir.glob("stretch-*.wav"))) == 1
