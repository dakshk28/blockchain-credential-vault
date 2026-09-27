from flask import Blueprint, flash, jsonify, redirect, render_template, url_for

from vault.auth.decorators import roles_required
from vault.integrity.services import INCIDENT_RESULTS, latest_checks, run_all

bp = Blueprint("integrity", __name__, url_prefix="/integrity")


@bp.post("/run")
@roles_required("admin")
def run_checks():
    return jsonify(results=run_all())


@bp.get("/dashboard")
@roles_required("admin")
def dashboard():
    counts = {}
    for check in latest_checks().values():
        counts[check.result] = counts.get(check.result, 0) + 1
    return jsonify(incident_count=sum(counts.get(kind, 0) for kind in INCIDENT_RESULTS), results=counts)


@bp.get("/monitor")
@roles_required("admin")
def monitor_page():
    latest = latest_checks()
    checks = sorted(latest.values(), key=lambda check: (check.result not in INCIDENT_RESULTS, check.credential.credential_id))
    counts = {}
    for check in checks:
        counts[check.result] = counts.get(check.result, 0) + 1
    last_run = max((check.checked_at for check in checks), default=None)
    return render_template("admin/integrity.html", checks=checks, counts=counts, incidents=sum(counts.get(kind, 0) for kind in INCIDENT_RESULTS), last_run=last_run)


@bp.post("/monitor/run")
@roles_required("admin")
def run_page():
    results = run_all()
    incidents = sum(1 for result in results.values() if result in INCIDENT_RESULTS)
    flash(f"Scanned {len(results)} stored document(s): {incidents} incident(s).", "error" if incidents else "success")
    return redirect(url_for("integrity.monitor_page"))
