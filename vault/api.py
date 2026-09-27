from flask import Blueprint, jsonify

bp = Blueprint("api", __name__, url_prefix="/api")

@bp.get("/openapi.json")
def openapi():
    return jsonify({"openapi": "3.0.3", "info": {"title": "Academic Credential Vault API", "version": "1.0.0"}, "paths": {"/auth/api/login": {"post": {"summary": "Authenticate a user"}}, "/credentials": {"post": {"summary": "Issue a credential"}}, "/credentials/bulk": {"post": {"summary": "Issue credentials from CSV"}}, "/verify/{credential_id}": {"get": {"summary": "Publicly verify a credential"}}, "/student/shared/{token}": {"get": {"summary": "View a shared credential"}}, "/audit/validate": {"get": {"summary": "Validate the audit chain"}}}})
