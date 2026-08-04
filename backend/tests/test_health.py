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


def test_openapi_exposes_bearer_auth_for_swagger(client):
    """Swagger Authorize needs components.securitySchemes + operation security."""
    schema = client.get("/openapi.json").json()
    schemes = schema.get("components", {}).get("securitySchemes", {})
    assert "BearerAuth" in schemes
    assert schemes["BearerAuth"]["type"] == "http"
    assert schemes["BearerAuth"]["scheme"] == "bearer"
    assert schema.get("security") == [{"BearerAuth": []}]
    # Public health stays optional in the UI.
    assert schema["paths"]["/health"]["get"].get("security") == []
    # Authenticated route advertises Bearer.
    me = schema["paths"]["/auth/me"]["get"]
    assert {"BearerAuth": []} in me.get("security", [])
