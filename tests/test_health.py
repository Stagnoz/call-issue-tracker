def test_health_returns_ok(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_every_endpoint_has_a_summary(client):
    spec = client.get("/openapi.json").json()

    operations = [op for methods in spec["paths"].values() for op in methods.values()]
    assert operations
    assert all(op.get("summary") for op in operations)
