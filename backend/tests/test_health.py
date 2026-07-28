def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_docs_available(client):
    resp = client.get("/docs")
    assert resp.status_code == 200


def test_openapi_schema_available(client):
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    paths = resp.json()["paths"]
    assert "/health" in paths
    assert "/mutual-funds/portfolio/parse" in paths
    assert "/tax-expert/parse-ais" in paths
