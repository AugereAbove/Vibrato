from __future__ import annotations

import numpy as np
import pytest
from fastapi.testclient import TestClient

from vibrato.demo.songs import DEMO_LYRICS

from .conftest import wav_bytes
from .helpers import wait_for


@pytest.fixture(scope="module")
def project(client: TestClient, rendered) -> dict:
    created = client.post("/api/projects", json={"name": "Integration", "song_title": "Harbor Light"}).json()[
        "project"
    ]
    ref = client.post(
        f"/api/projects/{created['id']}/recordings",
        data={"kind": "reference", "lyrics": DEMO_LYRICS},
        files={"file": ("reference.wav", wav_bytes(rendered["reference"].audio), "audio/wav")},
    ).json()
    assert wait_for(client, ref["task"])["status"] == "complete"
    take = client.post(
        f"/api/projects/{created['id']}/recordings",
        data={"kind": "take"},
        files={"file": ("take1.wav", wav_bytes(rendered["take1"].audio), "audio/wav")},
    ).json()
    state = wait_for(client, take["task"])
    assert state["status"] == "complete", state
    return {
        "project": created,
        "reference": ref["recording"],
        "take": take["recording"],
        "comparison_id": state["result"]["comparison_id"],
    }


def test_health_and_system(client: TestClient) -> None:
    health = client.get("/api/health").json()
    assert health["status"] == "ok" and health["schema_version"] >= 1
    system = client.get("/api/system").json()
    assert system["privacy"]["telemetry"] is False
    models = {m["id"]: m for m in client.get("/api/system/models").json()["models"]}
    assert models["praat"]["available"] and "install" in models["crepe"]
    methods = client.get("/api/system/methods").json()
    assert len(methods["analyzers"]) >= 10 and methods["glossary"]


def test_import_analyze_compare_retrieve(client: TestClient, project: dict) -> None:
    comparison = client.get(f"/api/comparisons/{project['comparison_id']}").json()
    assert comparison["scores"]["overall"]["score"] is not None
    assert comparison["coaching"]["primary"]
    assert comparison["heatmap"]["views"]["phrase"]["columns"]
    analysis = client.get(f"/api/recordings/{project['reference']['id']}/analysis").json()
    assert analysis["status"] == "complete" and not analysis["analysis"]["outdated"]
    levels = {s["level"] for s in analysis["segments"]}
    assert {"phrase", "word", "syllable", "note", "phoneme"}.issubset(levels)
    features = client.get(f"/api/recordings/{project['take']['id']}/features")
    header_length = int.from_bytes(features.content[:4], "little")
    assert header_length > 10 and len(features.content) > header_length
    assert client.get(f"/api/recordings/{project['take']['id']}/spectrogram").status_code == 200
    audio = client.get(f"/api/recordings/{project['take']['id']}/audio", headers={"Range": "bytes=0-1023"})
    assert audio.status_code == 206 and len(audio.content) == 1024


def test_duplicate_and_invalid_uploads(client: TestClient, project: dict, rendered) -> None:
    pid = project["project"]["id"]
    duplicate = client.post(
        f"/api/projects/{pid}/recordings",
        data={"kind": "reference"},
        files={"file": ("again.wav", wav_bytes(rendered["reference"].audio), "audio/wav")},
    )
    assert duplicate.status_code == 409 and duplicate.json()["error"]["existing_id"]
    garbage = client.post(
        f"/api/projects/{pid}/recordings",
        data={"kind": "take"},
        files={"file": ("bad.wav", b"RIFFnonsense" * 50, "audio/wav")},
    )
    assert garbage.status_code == 422
    error = garbage.json()["error"]
    assert error["what"] and error["why"] and error["action"]
    unsupported = client.post(
        f"/api/projects/{pid}/recordings",
        data={"kind": "take"},
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert unsupported.status_code == 422


def test_region_explanation_rescore_and_alignment(client: TestClient, project: dict) -> None:
    cid = project["comparison_id"]
    explanation = client.post(f"/api/comparisons/{cid}/why", json={"start_s": 1.9, "end_s": 3.7}).json()
    assert explanation["primary"]
    rescored = client.post(f"/api/comparisons/{cid}/rescore", json={"enabled": {"phonation": False}}).json()
    assert rescored["categories"]["phonation"]["enabled"] is False
    alignment = client.get(f"/api/comparisons/{cid}/alignment").json()
    assert alignment["summary"]["overall_confidence"] > 0.5
    anchor = client.post(
        "/api/anchors",
        json={
            "reference_id": project["reference"]["id"],
            "take_id": project["take"]["id"],
            "ref_time_s": 5.0,
            "user_time_s": 5.1,
        },
    ).json()["anchor"]
    moved = client.patch(f"/api/anchors/{anchor['id']}", json={"user_time_s": 5.15, "locked": False}).json()[
        "anchor"
    ]
    assert moved["user_time_s"] == pytest.approx(5.15) and moved["locked"] == 0
    assert client.delete(f"/api/anchors/{anchor['id']}").json()["deleted"]


def test_counterfactual_is_labelled_synthetic(client: TestClient, project: dict) -> None:
    task = client.post(
        f"/api/takes/{project['take']['id']}/counterfactuals", json={"transform": "note_centers"}
    ).json()["task"]
    state = wait_for(client, task)
    assert state["status"] == "complete"
    render_id = state["result"]["id"]
    audio = client.get(f"/api/renders/{render_id}/audio?download=true")
    assert audio.headers["x-synthetic"] == "true"
    assert "SYNTHETIC" in audio.headers["content-disposition"]


def test_progress_exports_and_reports(client: TestClient, project: dict) -> None:
    pid = project["project"]["id"]
    progress = client.get(f"/api/projects/{pid}/progress").json()
    assert len(progress["takes"]) == 1 and progress["trends"]["overall"]["latest"] is not None
    csv_text = client.get(f"/api/comparisons/{project['comparison_id']}/export.csv").text
    assert "vibrato.rate" in csv_text and "confidence" in csv_text.splitlines()[1]
    exported = client.get(f"/api/comparisons/{project['comparison_id']}/export.json").json()
    assert exported["reproducibility"]["analyzer_versions"]["pitch"]
    assert "<html" in client.get(f"/api/projects/{pid}/report.html").text
    assert (
        client.get(f"/api/comparisons/{project['comparison_id']}/ab.wav?start=1.9&end=3.7").status_code == 200
    )
    assert client.get(f"/api/recordings/{project['take']['id']}/segment.wav?start=1&end=2").status_code == 200


def test_backup_and_restore_round_trip(client: TestClient, project: dict) -> None:
    backup = client.post(f"/api/projects/{project['project']['id']}/backup")
    assert backup.status_code == 200
    restored = client.post(
        "/api/projects/restore", files={"file": ("b.zip", backup.content, "application/zip")}
    ).json()["project"]
    assert restored["name"].endswith("(restored)")
    recordings = client.get(f"/api/projects/{restored['id']}/recordings").json()["recordings"]
    assert len(recordings) == 2


def test_empty_project_progress_and_preferences(client: TestClient) -> None:
    empty = client.post("/api/projects", json={"name": "Empty"}).json()["project"]
    progress = client.get(f"/api/projects/{empty['id']}/progress").json()
    assert progress["takes"] == [] and progress["weaknesses"] == []
    prefs = client.put(
        "/api/preferences", json={"values": {"display.theme": "light", "privacy.telemetry": True}}
    ).json()["values"]
    assert prefs["display.theme"] == "light" and prefs["privacy.telemetry"] is False
    reset = client.post("/api/preferences/reset").json()["values"]
    assert reset["display.theme"] == "system"


def test_project_crud(client: TestClient) -> None:
    created = client.post("/api/projects", json={"name": "Temp"}).json()["project"]
    renamed = client.patch(
        f"/api/projects/{created['id']}", json={"name": "Renamed", "favorite": True}
    ).json()["project"]
    assert renamed["name"] == "Renamed" and renamed["favorite"] == 1
    copy = client.post(f"/api/projects/{created['id']}/duplicate").json()["project"]
    assert copy["name"] == "Renamed (copy)"
    archived = client.patch(f"/api/projects/{copy['id']}", json={"archived": True}).json()["project"]
    assert archived["archived"] == 1
    names = [p["name"] for p in client.get("/api/projects?search=Renamed").json()["projects"]]
    assert "Renamed" in names and "Renamed (copy)" not in names
    assert client.delete(f"/api/projects/{created['id']}").json()["deleted"]
    assert client.get(f"/api/projects/{created['id']}").status_code == 404


def test_persistence_across_restart(tmp_path, rendered) -> None:
    from vibrato.api.app import create_app
    from vibrato.config import Settings

    settings = Settings(data_dir=tmp_path / "persist", workers=1)
    with TestClient(create_app(settings)) as first:
        created = first.post("/api/projects", json={"name": "Survivor"}).json()["project"]
        upload = first.post(
            f"/api/projects/{created['id']}/recordings",
            data={"kind": "reference", "auto_analyze": "false"},
            files={"file": ("r.wav", wav_bytes(rendered["reference"].audio[: 44100 * 3]), "audio/wav")},
        )
        assert upload.status_code == 200
    with TestClient(create_app(Settings(data_dir=tmp_path / "persist", workers=1))) as second:
        project = second.get(f"/api/projects/{created['id']}").json()
        assert project["project"]["name"] == "Survivor" and len(project["recordings"]) == 1


def test_short_silence_upload_is_rejected(client: TestClient) -> None:
    pid = client.post("/api/projects", json={"name": "Short"}).json()["project"]["id"]
    response = client.post(
        f"/api/projects/{pid}/recordings",
        data={"kind": "take"},
        files={"file": ("s.wav", wav_bytes(np.zeros(2000)), "audio/wav")},
    )
    assert response.status_code == 422 and response.json()["error"]["code"] == "too_short"
