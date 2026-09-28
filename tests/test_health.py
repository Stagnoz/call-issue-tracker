def test_health_returns_ok(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_every_endpoint_has_a_summary(client):
    spec = client.get("/openapi.json").json()

    operations = [op for methods in spec["paths"].values() for op in methods.values()]
    assert operations
    assert all(op.get("summary") for op in operations)


def test_api_docs_use_local_files_only(client):
    response = client.get("/docs")

    assert response.status_code == 200
    assert "/static/swagger-ui/swagger-ui-bundle.js" in response.text
    assert "/static/swagger-ui/swagger-ui.css" in response.text
    assert "https://" not in response.text
    assert client.get("/static/swagger-ui/swagger-ui-bundle.js").status_code == 200
    assert client.get("/static/swagger-ui/swagger-ui.css").status_code == 200
    assert client.get("/redoc").status_code == 404
