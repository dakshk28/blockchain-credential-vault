def test_application_starts(app):
    assert app.config["TESTING"] is True


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_unknown_api_route_returns_json_error(client):
    response = client.get("/api/not-here")
    assert response.status_code == 404
    assert response.get_json()["error"] == "not_found"


def test_security_headers_are_present(client):
    response = client.get("/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
