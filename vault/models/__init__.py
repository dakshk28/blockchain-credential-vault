from datetime import date

from vault.extensions import db
from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash


class Institution(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    code = db.Column(db.String(32), nullable=False, unique=True, index=True)
    is_verified = db.Column(db.Boolean, nullable=False, default=False)
    # Branding shown on generated certificates and public verification pages.
    accent_color = db.Column(db.String(7), nullable=True)
    website = db.Column(db.String(255), nullable=True)
    logo_key = db.Column(db.String(64), nullable=True)


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(320), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, index=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    email_verified = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    failed_login_count = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    locked_until = db.Column(db.DateTime(timezone=True), nullable=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class IssuerProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, unique=True)
    institution_id = db.Column(db.Integer, db.ForeignKey("institution.id"), nullable=False)
    institution = db.relationship("Institution")
    approval_status = db.Column(db.String(20), nullable=False, default="pending", index=True)
    approved_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)


class AuditEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_type = db.Column(db.String(64), nullable=False, index=True)
    actor_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    metadata_json = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.now())
    previous_event_hash = db.Column(db.String(64), nullable=True)
    event_hash = db.Column(db.String(64), nullable=False, unique=True)
    actor = db.relationship("User")


class Credential(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    credential_id = db.Column(db.String(64), nullable=False, unique=True, index=True)
    institution_id = db.Column(db.Integer, db.ForeignKey("institution.id"), nullable=False)
    issued_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    programme = db.Column(db.String(255), nullable=False)
    issue_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="active", index=True)
    document_sha256 = db.Column(db.String(64), nullable=False)
    storage_key = db.Column(db.String(255), nullable=False, unique=True)
    original_filename = db.Column(db.String(255), nullable=False)
    document_available = db.Column(db.Boolean, nullable=False, default=True)
    description = db.Column(db.Text, nullable=True)
    expiry_date = db.Column(db.Date, nullable=True)
    student_profile_id = db.Column(db.Integer, db.ForeignKey("student_profile.id"), nullable=True, index=True)
    replacement_of_id = db.Column(db.Integer, db.ForeignKey("credential.id"), nullable=True, index=True)
    institution = db.relationship("Institution")
    student_profile = db.relationship("StudentProfile")
    issued_by = db.relationship("User", foreign_keys=[issued_by_user_id])
    revocation = db.relationship("Revocation", uselist=False, viewonly=True)
    signature_record = db.relationship("CredentialSignature", uselist=False, viewonly=True)
    anchor_proof = db.relationship("CredentialAnchorProof", uselist=False, viewonly=True)
    # Self-referential lifecycle links: the credential this one replaced, and the one that replaced it.
    replacement_of = db.relationship("Credential", remote_side=[id], foreign_keys=[replacement_of_id], viewonly=True)
    replaced_by = db.relationship("Credential", foreign_keys=[replacement_of_id], uselist=False, viewonly=True)

    @property
    def is_expired(self):
        return self.expiry_date is not None and self.expiry_date < date.today()

    @property
    def effective_status(self):
        """Stored status, except that an active credential past its expiry date reports as expired."""
        return "expired" if self.status == "active" and self.is_expired else self.status


class IntegrityCheck(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    credential_id = db.Column(db.Integer, db.ForeignKey("credential.id"), nullable=False, index=True)
    checked_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.now())
    current_sha256 = db.Column(db.String(64), nullable=True)
    result = db.Column(db.String(20), nullable=False)
    details = db.Column(db.String(500), nullable=True)
    credential = db.relationship("Credential")


class Revocation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    credential_id = db.Column(db.Integer, db.ForeignKey("credential.id"), nullable=False, unique=True)
    reason = db.Column(db.String(500), nullable=False)
    revoked_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    revoked_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.now())


class StudentProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    institution_id = db.Column(db.Integer, db.ForeignKey("institution.id"), nullable=False, index=True)
    student_identifier = db.Column(db.String(100), nullable=False, index=True)
    __table_args__ = (db.UniqueConstraint("institution_id", "student_identifier", name="uq_student_identifier_per_institution"),)
    user = db.relationship("User")


class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    event_type = db.Column(db.String(64), nullable=False)
    message = db.Column(db.String(500), nullable=False)
    is_read = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.now())


class InstitutionVerificationRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    institution_id = db.Column(db.Integer, db.ForeignKey("institution.id"), nullable=False, unique=True)
    representative_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    official_email_domain = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pending", index=True)
    reviewer_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    review_note = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.now())
    institution = db.relationship("Institution")
    representative = db.relationship("User", foreign_keys=[representative_user_id])

class CredentialSignature(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    credential_id = db.Column(db.Integer, db.ForeignKey("credential.id"), nullable=False, unique=True)
    algorithm = db.Column(db.String(32), nullable=False, default="HMAC-SHA256")
    signature = db.Column(db.String(128), nullable=False)
    key_id = db.Column(db.String(32), nullable=True)  # Ed25519 key fingerprint; NULL for legacy HMAC signatures

class AuditAnchor(db.Model):
    """A Merkle root (credential batch) or audit-chain head published through an anchor provider."""
    id = db.Column(db.Integer, primary_key=True)
    audit_root = db.Column(db.String(64), nullable=False)  # the anchored 32-byte root, hex
    provider = db.Column(db.String(64), nullable=False, default="local")
    anchored_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.now())
    kind = db.Column(db.String(20), nullable=False, default="audit", server_default="audit")
    item_count = db.Column(db.Integer, nullable=True)
    network = db.Column(db.String(64), nullable=True)
    tx_hash = db.Column(db.String(80), nullable=True)
    block_number = db.Column(db.Integer, nullable=True)
    explorer_url = db.Column(db.String(255), nullable=True)


class CredentialAnchorProof(db.Model):
    """Merkle inclusion proof linking one credential's signed record to an anchored root."""
    id = db.Column(db.Integer, primary_key=True)
    credential_id = db.Column(db.Integer, db.ForeignKey("credential.id"), nullable=False, unique=True)
    anchor_id = db.Column(db.Integer, db.ForeignKey("audit_anchor.id"), nullable=False, index=True)
    leaf_hash = db.Column(db.String(64), nullable=False)
    proof = db.Column(db.JSON, nullable=False, default=list)
    anchor = db.relationship("AuditAnchor")

class CredentialTemplate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    institution_id = db.Column(db.Integer, db.ForeignKey("institution.id"), nullable=False, index=True)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    programme = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    archived = db.Column(db.Boolean, nullable=False, default=False)

class ShareLink(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(96), nullable=False, unique=True, index=True)
    credential_id = db.Column(db.Integer, db.ForeignKey("credential.id"), nullable=False)
    student_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    revoked = db.Column(db.Boolean, nullable=False, default=False)


class ClaimRequest(db.Model):
    """A student asks an institution to link their account to a student identifier."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    institution_id = db.Column(db.Integer, db.ForeignKey("institution.id"), nullable=False, index=True)
    student_identifier = db.Column(db.String(100), nullable=False)
    message = db.Column(db.String(500), nullable=True)
    status = db.Column(db.String(20), nullable=False, default="pending", index=True)
    review_note = db.Column(db.String(500), nullable=True)
    reviewed_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.now())
    reviewed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    user = db.relationship("User", foreign_keys=[user_id])
    institution = db.relationship("Institution")
