from flask import current_app, has_request_context, url_for


def external_url(endpoint, **values):
    """Absolute URL for links in emails and certificates, also outside a request (CLI, cron).

    Inside a request the current host is used; otherwise PUBLIC_BASE_URL (e.g. https://vault.example.edu).
    """
    if has_request_context() or current_app.config.get("SERVER_NAME"):
        return url_for(endpoint, _external=True, **values)
    with current_app.test_request_context(base_url=current_app.config["PUBLIC_BASE_URL"]):
        return url_for(endpoint, _external=True, **values)
