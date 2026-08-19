"""
Minimal smoke test for the backend service.
Only exercises the DB-free health endpoint so it can run in CI without a
live Postgres connection — see the Jenkins repo's README for this trade-off.
"""
import app as app_module


def test_health_endpoint_returns_ok():
    client = app_module.app.test_client()
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}