"""
Valaioli — Stage 5 updater endpoint tests.

Tests cover:
  - /api/updater/status (with candidate and without)
  - /api/updater/verify (requires Windows and verify-tools.ps1)
"""
import sys
import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.updater

def test_updater_status_no_candidate(no_tools_client: TestClient):
    """Manifest with no candidates returns update_available=False."""
    resp = no_tools_client.get("/api/updater/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["update_available"] is False
    assert len(data["tools"]) == 2
    for tool in data["tools"]:
        assert tool["candidate"] is None

def test_updater_status_with_candidate(candidate_client: TestClient):
    """Manifest with a candidate returns update_available=True."""
    resp = candidate_client.get("/api/updater/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["update_available"] is True
    tools_by_name = {t["name"]: t for t in data["tools"]}
    ffmpeg = tools_by_name["ffmpeg"]
    assert ffmpeg["candidate"] is not None
    assert ffmpeg["candidate"]["version"] == "9.0.2"

@pytest.mark.skipif(sys.platform != "win32", reason="Verify script requires Windows")
def test_updater_verify_endpoint(client: TestClient):
    """
    Test that the verify endpoint correctly invokes verify-tools.ps1.
    This may fail if the actual script is not in place or not executable.
    Since we mock/patch the manifest for unit tests, here we use the real client
    to run the real script. We just expect it to run and return a 200 with JSON.
    """
    resp = client.post("/api/updater/verify")
    # Depending on what's installed, it might be 200 True or False.
    # But it shouldn't be 500.
    if resp.status_code == 200:
        data = resp.json()
        assert "passed" in data
        assert "output" in data
    elif resp.status_code == 503:
        pass # missing script
    else:
        pytest.fail(f"Unexpected status code: {resp.status_code}")
