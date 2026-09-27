import pytest

from vault import create_app
from vault.extensions import db


@pytest.fixture()
def app():
    app = create_app("test")
    with app.app_context():
        db.drop_all()  # start clean even if a previous run on a shared PostgreSQL test DB was interrupted
        db.create_all()
    yield app
    with app.app_context():
        db.session.remove()  # release open transactions first, or PostgreSQL blocks DROP TABLE
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()
