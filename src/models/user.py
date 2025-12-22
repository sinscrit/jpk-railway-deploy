from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)

    def __repr__(self):
        return f'<User {self.username}>'

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email
        }

class ApprovedUser(db.Model):
    """Users who are approved to use the converter"""
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    name = db.Column(db.String(255), nullable=True)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    approved_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    approved_by = db.Column(db.String(120), nullable=True)  # Admin who approved
    notes = db.Column(db.Text, nullable=True)  # Admin notes
    max_conversions_per_day = db.Column(db.Integer, default=50, nullable=False)

    def __repr__(self):
        return f'<ApprovedUser {self.email}>'

    def to_dict(self):
        return {
            'id': self.id,
            'email': self.email,
            'name': self.name,
            'is_admin': self.is_admin,
            'is_active': self.is_active,
            'approved_at': self.approved_at.isoformat() if self.approved_at else None,
            'approved_by': self.approved_by,
            'notes': self.notes,
            'max_conversions_per_day': self.max_conversions_per_day
        }

class AccessRequest(db.Model):
    """Pending access requests from users"""
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    name = db.Column(db.String(255), nullable=True)
    requested_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    reason = db.Column(db.Text, nullable=True)  # Why they need access
    status = db.Column(db.String(20), default='pending', nullable=False)  # pending, approved, denied
    reviewed_at = db.Column(db.DateTime, nullable=True)
    reviewed_by = db.Column(db.String(120), nullable=True)

    def __repr__(self):
        return f'<AccessRequest {self.email} {self.status}>'

    def to_dict(self):
        return {
            'id': self.id,
            'email': self.email,
            'name': self.name,
            'requested_at': self.requested_at.isoformat() if self.requested_at else None,
            'reason': self.reason,
            'status': self.status,
            'reviewed_at': self.reviewed_at.isoformat() if self.reviewed_at else None,
            'reviewed_by': self.reviewed_by
        }

class ConversionLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.String(36), unique=True, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    client_ip = db.Column(db.String(45), nullable=False)  # IPv6 compatible
    user_email = db.Column(db.String(120), nullable=True)  # User email from session
    user_name = db.Column(db.String(255), nullable=True)  # User display name
    input_filename = db.Column(db.String(255), nullable=False)
    input_file_size = db.Column(db.Integer, nullable=False)  # bytes
    output_file_size = db.Column(db.Integer, nullable=True)  # bytes, null if failed
    status = db.Column(db.String(20), nullable=False)  # processing, completed, error
    processing_time = db.Column(db.Float, nullable=True)  # seconds
    error_message = db.Column(db.Text, nullable=True)

    def __repr__(self):
        return f'<ConversionLog {self.job_id}>'

    def to_dict(self):
        return {
            'id': self.id,
            'job_id': self.job_id,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'client_ip': self.client_ip,
            'user_email': self.user_email,
            'user_name': self.user_name,
            'input_filename': self.input_filename,
            'input_file_size': self.input_file_size,
            'output_file_size': self.output_file_size,
            'status': self.status,
            'processing_time': self.processing_time,
            'error_message': self.error_message
        }

class RateLimitLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    client_ip = db.Column(db.String(45), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    endpoint = db.Column(db.String(100), nullable=False)

    def __repr__(self):
        return f'<RateLimitLog {self.client_ip} {self.endpoint}>'

class PageLoadLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    client_ip = db.Column(db.String(45), nullable=False)
    user_email = db.Column(db.String(120), nullable=True)  # User email if logged in
    user_name = db.Column(db.String(255), nullable=True)  # User display name if logged in
    page_url = db.Column(db.String(500), nullable=False)  # Page URL
    user_agent = db.Column(db.Text, nullable=True)  # Browser user agent
    referrer = db.Column(db.String(500), nullable=True)  # Referrer URL

    def __repr__(self):
        return f'<PageLoadLog {self.client_ip} {self.page_url}>'

    def to_dict(self):
        return {
            'id': self.id,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'client_ip': self.client_ip,
            'user_email': self.user_email,
            'user_name': self.user_name,
            'page_url': self.page_url,
            'user_agent': self.user_agent,
            'referrer': self.referrer
        }

class LoginLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    client_ip = db.Column(db.String(45), nullable=False)
    user_email = db.Column(db.String(120), nullable=False)  # User email
    user_name = db.Column(db.String(255), nullable=False)  # User display name
    login_method = db.Column(db.String(50), nullable=False)  # e.g., 'google_oauth'
    success = db.Column(db.Boolean, nullable=False, default=True)  # Login success/failure
    error_message = db.Column(db.Text, nullable=True)  # Error message if failed
    user_agent = db.Column(db.Text, nullable=True)  # Browser user agent

    def __repr__(self):
        return f'<LoginLog {self.user_email} {self.timestamp}>'

    def to_dict(self):
        return {
            'id': self.id,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'client_ip': self.client_ip,
            'user_email': self.user_email,
            'user_name': self.user_name,
            'login_method': self.login_method,
            'success': self.success,
            'error_message': self.error_message,
            'user_agent': self.user_agent
        }
