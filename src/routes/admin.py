"""
Admin routes for user management and reporting
"""
import os
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, session, render_template_string
from sqlalchemy import func, desc
from src.models.user import db, ApprovedUser, AccessRequest, ConversionLog, LoginLog

admin_bp = Blueprint('admin', __name__)

# Get admin emails from environment variable (comma-separated)
ADMIN_EMAILS = os.getenv('ADMIN_EMAILS', 'sinscrit@gmail.com').split(',')

def is_admin():
    """Check if current user is an admin"""
    user = session.get('user')
    if not user:
        return False

    email = user.get('email', '').lower()

    # Check environment variable admins
    if email in [e.strip().lower() for e in ADMIN_EMAILS]:
        return True

    # Check database admins
    approved = ApprovedUser.query.filter_by(email=email, is_admin=True, is_active=True).first()
    return approved is not None

def is_approved_user(email):
    """Check if a user is approved to use the system"""
    if not email:
        return False

    email = email.lower()

    # Admins are always approved
    if email in [e.strip().lower() for e in ADMIN_EMAILS]:
        return True

    # Check approved users table
    approved = ApprovedUser.query.filter_by(email=email, is_active=True).first()
    return approved is not None

def require_admin(f):
    """Decorator to require admin access"""
    from functools import wraps

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return jsonify({'error': 'Authentication required'}), 401
        if not is_admin():
            return jsonify({'error': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated_function

# ============= User Management =============

@admin_bp.route('/api/admin/users', methods=['GET'])
@require_admin
def list_users():
    """List all approved users"""
    users = ApprovedUser.query.order_by(desc(ApprovedUser.approved_at)).all()
    return jsonify({
        'users': [u.to_dict() for u in users],
        'total': len(users)
    })

@admin_bp.route('/api/admin/users', methods=['POST'])
@require_admin
def add_user():
    """Add a new approved user"""
    data = request.get_json()
    email = data.get('email', '').strip().lower()

    if not email:
        return jsonify({'error': 'Email is required'}), 400

    # Check if already exists
    existing = ApprovedUser.query.filter_by(email=email).first()
    if existing:
        return jsonify({'error': 'User already exists'}), 400

    user = ApprovedUser(
        email=email,
        name=data.get('name', ''),
        is_admin=data.get('is_admin', False),
        is_active=True,
        approved_by=session['user']['email'],
        notes=data.get('notes', ''),
        max_conversions_per_day=data.get('max_conversions_per_day', 50)
    )

    db.session.add(user)
    db.session.commit()

    return jsonify({'message': 'User added successfully', 'user': user.to_dict()}), 201

@admin_bp.route('/api/admin/users/<int:user_id>', methods=['PUT'])
@require_admin
def update_user(user_id):
    """Update an approved user"""
    user = ApprovedUser.query.get_or_404(user_id)
    data = request.get_json()

    if 'name' in data:
        user.name = data['name']
    if 'is_admin' in data:
        user.is_admin = data['is_admin']
    if 'is_active' in data:
        user.is_active = data['is_active']
    if 'notes' in data:
        user.notes = data['notes']
    if 'max_conversions_per_day' in data:
        user.max_conversions_per_day = data['max_conversions_per_day']

    db.session.commit()
    return jsonify({'message': 'User updated', 'user': user.to_dict()})

@admin_bp.route('/api/admin/users/<int:user_id>', methods=['DELETE'])
@require_admin
def delete_user(user_id):
    """Delete an approved user"""
    user = ApprovedUser.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()
    return jsonify({'message': 'User deleted'})

# ============= Access Requests =============

@admin_bp.route('/api/admin/requests', methods=['GET'])
@require_admin
def list_requests():
    """List pending access requests"""
    status = request.args.get('status', 'pending')
    if status == 'all':
        requests_list = AccessRequest.query.order_by(desc(AccessRequest.requested_at)).all()
    else:
        requests_list = AccessRequest.query.filter_by(status=status).order_by(desc(AccessRequest.requested_at)).all()

    return jsonify({
        'requests': [r.to_dict() for r in requests_list],
        'total': len(requests_list)
    })

@admin_bp.route('/api/admin/requests/<int:request_id>/approve', methods=['POST'])
@require_admin
def approve_request(request_id):
    """Approve an access request"""
    access_request = AccessRequest.query.get_or_404(request_id)

    if access_request.status != 'pending':
        return jsonify({'error': 'Request already processed'}), 400

    # Create approved user
    user = ApprovedUser(
        email=access_request.email,
        name=access_request.name,
        is_admin=False,
        is_active=True,
        approved_by=session['user']['email'],
        notes=f"Approved from request: {access_request.reason}"
    )

    access_request.status = 'approved'
    access_request.reviewed_at = datetime.utcnow()
    access_request.reviewed_by = session['user']['email']

    db.session.add(user)
    db.session.commit()

    return jsonify({'message': 'Request approved', 'user': user.to_dict()})

@admin_bp.route('/api/admin/requests/<int:request_id>/deny', methods=['POST'])
@require_admin
def deny_request(request_id):
    """Deny an access request"""
    access_request = AccessRequest.query.get_or_404(request_id)

    if access_request.status != 'pending':
        return jsonify({'error': 'Request already processed'}), 400

    access_request.status = 'denied'
    access_request.reviewed_at = datetime.utcnow()
    access_request.reviewed_by = session['user']['email']

    db.session.commit()

    return jsonify({'message': 'Request denied'})

# ============= Reports =============

@admin_bp.route('/api/admin/reports/summary', methods=['GET'])
@require_admin
def get_summary():
    """Get summary statistics"""
    today = datetime.utcnow().date()
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)

    # User counts
    total_users = ApprovedUser.query.filter_by(is_active=True).count()
    pending_requests = AccessRequest.query.filter_by(status='pending').count()

    # Conversion counts
    total_conversions = ConversionLog.query.count()
    successful_conversions = ConversionLog.query.filter_by(status='completed').count()
    failed_conversions = ConversionLog.query.filter_by(status='error').count()

    conversions_today = ConversionLog.query.filter(
        func.date(ConversionLog.timestamp) == today
    ).count()

    conversions_week = ConversionLog.query.filter(
        func.date(ConversionLog.timestamp) >= week_ago
    ).count()

    conversions_month = ConversionLog.query.filter(
        func.date(ConversionLog.timestamp) >= month_ago
    ).count()

    # Login counts
    logins_today = LoginLog.query.filter(
        func.date(LoginLog.timestamp) == today,
        LoginLog.success == True
    ).count()

    logins_week = LoginLog.query.filter(
        func.date(LoginLog.timestamp) >= week_ago,
        LoginLog.success == True
    ).count()

    # Storage stats
    total_input_size = db.session.query(func.sum(ConversionLog.input_file_size)).scalar() or 0
    total_output_size = db.session.query(func.sum(ConversionLog.output_file_size)).scalar() or 0

    return jsonify({
        'users': {
            'total_approved': total_users,
            'pending_requests': pending_requests
        },
        'conversions': {
            'total': total_conversions,
            'successful': successful_conversions,
            'failed': failed_conversions,
            'today': conversions_today,
            'this_week': conversions_week,
            'this_month': conversions_month,
            'success_rate': round(successful_conversions / total_conversions * 100, 1) if total_conversions > 0 else 0
        },
        'logins': {
            'today': logins_today,
            'this_week': logins_week
        },
        'storage': {
            'total_input_mb': round(total_input_size / (1024 * 1024), 2),
            'total_output_mb': round(total_output_size / (1024 * 1024), 2)
        }
    })

@admin_bp.route('/api/admin/reports/conversions', methods=['GET'])
@require_admin
def get_conversions():
    """Get conversion history"""
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)
    user_email = request.args.get('user_email')
    status = request.args.get('status')

    query = ConversionLog.query

    if user_email:
        query = query.filter_by(user_email=user_email)
    if status:
        query = query.filter_by(status=status)

    total = query.count()
    conversions = query.order_by(desc(ConversionLog.timestamp)).offset(offset).limit(limit).all()

    return jsonify({
        'conversions': [c.to_dict() for c in conversions],
        'total': total,
        'limit': limit,
        'offset': offset
    })

@admin_bp.route('/api/admin/reports/logins', methods=['GET'])
@require_admin
def get_logins():
    """Get login history"""
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)

    total = LoginLog.query.count()
    logins = LoginLog.query.order_by(desc(LoginLog.timestamp)).offset(offset).limit(limit).all()

    return jsonify({
        'logins': [l.to_dict() for l in logins],
        'total': total,
        'limit': limit,
        'offset': offset
    })

@admin_bp.route('/api/admin/reports/users-activity', methods=['GET'])
@require_admin
def get_users_activity():
    """Get activity by user"""
    # Conversions by user
    user_stats = db.session.query(
        ConversionLog.user_email,
        func.count(ConversionLog.id).label('conversion_count'),
        func.sum(ConversionLog.input_file_size).label('total_input_size'),
        func.max(ConversionLog.timestamp).label('last_conversion')
    ).group_by(ConversionLog.user_email).order_by(desc('conversion_count')).all()

    return jsonify({
        'users': [{
            'email': stat.user_email,
            'conversion_count': stat.conversion_count,
            'total_input_mb': round((stat.total_input_size or 0) / (1024 * 1024), 2),
            'last_conversion': stat.last_conversion.isoformat() if stat.last_conversion else None
        } for stat in user_stats]
    })

# ============= Request Access (Public) =============

@admin_bp.route('/api/request-access', methods=['POST'])
def request_access():
    """Submit an access request (public endpoint)"""
    user = session.get('user')
    if not user:
        return jsonify({'error': 'Please login with Google first'}), 401

    email = user.get('email', '').lower()
    name = user.get('name', '')

    # Check if already approved
    if is_approved_user(email):
        return jsonify({'error': 'You already have access'}), 400

    # Check if request already exists
    existing = AccessRequest.query.filter_by(email=email).first()
    if existing:
        return jsonify({
            'error': 'Access request already submitted',
            'status': existing.status,
            'requested_at': existing.requested_at.isoformat()
        }), 400

    data = request.get_json() or {}

    access_request = AccessRequest(
        email=email,
        name=name,
        reason=data.get('reason', '')
    )

    db.session.add(access_request)
    db.session.commit()

    return jsonify({
        'message': 'Access request submitted. An admin will review your request.',
        'request': access_request.to_dict()
    }), 201

@admin_bp.route('/api/access-status', methods=['GET'])
def access_status():
    """Check access status for current user"""
    user = session.get('user')
    if not user:
        return jsonify({'authenticated': False, 'approved': False})

    email = user.get('email', '').lower()

    # Check if approved
    if is_approved_user(email):
        approved_user = ApprovedUser.query.filter_by(email=email).first()
        return jsonify({
            'authenticated': True,
            'approved': True,
            'is_admin': is_admin(),
            'user': approved_user.to_dict() if approved_user else {'email': email, 'is_admin': is_admin()}
        })

    # Check if request pending
    access_request = AccessRequest.query.filter_by(email=email).first()
    if access_request:
        return jsonify({
            'authenticated': True,
            'approved': False,
            'request_status': access_request.status,
            'requested_at': access_request.requested_at.isoformat()
        })

    return jsonify({
        'authenticated': True,
        'approved': False,
        'request_status': None
    })

# ============= Admin Dashboard HTML =============

ADMIN_DASHBOARD_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Admin Dashboard - JPK Converter</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #f5f5f5;
            min-height: 100vh;
        }
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .header h1 { font-size: 1.5rem; }
        .header a { color: white; text-decoration: none; margin-left: 20px; }
        .container { max-width: 1400px; margin: 0 auto; padding: 20px; }
        .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 30px; }
        .card {
            background: white;
            border-radius: 10px;
            padding: 20px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        .card h3 { color: #666; font-size: 0.9rem; margin-bottom: 10px; text-transform: uppercase; }
        .card .value { font-size: 2rem; font-weight: 700; color: #333; }
        .card .sub { font-size: 0.8rem; color: #999; }
        .section {
            background: white;
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        .section h2 { margin-bottom: 20px; color: #333; font-size: 1.2rem; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #eee; }
        th { background: #f8f9fa; font-weight: 600; color: #666; }
        .btn {
            padding: 8px 16px;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            font-size: 0.9rem;
            margin-right: 5px;
        }
        .btn-approve { background: #28a745; color: white; }
        .btn-deny { background: #dc3545; color: white; }
        .btn-primary { background: #667eea; color: white; }
        .status { padding: 4px 8px; border-radius: 12px; font-size: 0.8rem; }
        .status-pending { background: #fff3cd; color: #856404; }
        .status-approved { background: #d4edda; color: #155724; }
        .status-denied { background: #f8d7da; color: #721c24; }
        .status-completed { background: #d4edda; color: #155724; }
        .status-error { background: #f8d7da; color: #721c24; }
        .tabs { display: flex; gap: 10px; margin-bottom: 20px; }
        .tab {
            padding: 10px 20px;
            background: #e9ecef;
            border-radius: 5px;
            cursor: pointer;
            transition: all 0.2s;
        }
        .tab.active { background: #667eea; color: white; }
        .modal {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.5);
            justify-content: center;
            align-items: center;
        }
        .modal.show { display: flex; }
        .modal-content {
            background: white;
            padding: 30px;
            border-radius: 10px;
            width: 90%;
            max-width: 500px;
        }
        .form-group { margin-bottom: 15px; }
        .form-group label { display: block; margin-bottom: 5px; font-weight: 500; }
        .form-group input, .form-group textarea {
            width: 100%;
            padding: 10px;
            border: 1px solid #ddd;
            border-radius: 5px;
        }
        .form-group input[type="checkbox"] { width: auto; }
    </style>
</head>
<body>
    <div class="header">
        <h1>Admin Dashboard</h1>
        <div>
            <span id="adminEmail"></span>
            <a href="/">Back to Converter</a>
            <a href="/logout">Logout</a>
        </div>
    </div>

    <div class="container">
        <div class="cards" id="summaryCards"></div>

        <div class="tabs">
            <div class="tab active" onclick="showTab('users')">Users</div>
            <div class="tab" onclick="showTab('requests')">Access Requests</div>
            <div class="tab" onclick="showTab('conversions')">Conversions</div>
            <div class="tab" onclick="showTab('logins')">Login History</div>
            <div class="tab" onclick="showTab('activity')">User Activity</div>
        </div>

        <div id="usersTab" class="section">
            <h2>Approved Users <button class="btn btn-primary" onclick="showAddUserModal()">+ Add User</button></h2>
            <table>
                <thead>
                    <tr>
                        <th>Email</th>
                        <th>Name</th>
                        <th>Admin</th>
                        <th>Active</th>
                        <th>Approved At</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody id="usersTable"></tbody>
            </table>
        </div>

        <div id="requestsTab" class="section" style="display:none;">
            <h2>Access Requests</h2>
            <table>
                <thead>
                    <tr>
                        <th>Email</th>
                        <th>Name</th>
                        <th>Reason</th>
                        <th>Requested At</th>
                        <th>Status</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody id="requestsTable"></tbody>
            </table>
        </div>

        <div id="conversionsTab" class="section" style="display:none;">
            <h2>Conversion History</h2>
            <table>
                <thead>
                    <tr>
                        <th>Time</th>
                        <th>User</th>
                        <th>File</th>
                        <th>Size</th>
                        <th>Status</th>
                        <th>Duration</th>
                    </tr>
                </thead>
                <tbody id="conversionsTable"></tbody>
            </table>
        </div>

        <div id="loginsTab" class="section" style="display:none;">
            <h2>Login History</h2>
            <table>
                <thead>
                    <tr>
                        <th>Time</th>
                        <th>Email</th>
                        <th>Name</th>
                        <th>IP</th>
                        <th>Success</th>
                    </tr>
                </thead>
                <tbody id="loginsTable"></tbody>
            </table>
        </div>

        <div id="activityTab" class="section" style="display:none;">
            <h2>User Activity</h2>
            <table>
                <thead>
                    <tr>
                        <th>User</th>
                        <th>Conversions</th>
                        <th>Total Size</th>
                        <th>Last Active</th>
                    </tr>
                </thead>
                <tbody id="activityTable"></tbody>
            </table>
        </div>
    </div>

    <div class="modal" id="addUserModal">
        <div class="modal-content">
            <h2>Add User</h2>
            <form id="addUserForm">
                <div class="form-group">
                    <label>Email *</label>
                    <input type="email" name="email" required>
                </div>
                <div class="form-group">
                    <label>Name</label>
                    <input type="text" name="name">
                </div>
                <div class="form-group">
                    <label><input type="checkbox" name="is_admin"> Is Admin</label>
                </div>
                <div class="form-group">
                    <label>Notes</label>
                    <textarea name="notes" rows="3"></textarea>
                </div>
                <div class="form-group">
                    <label>Max conversions/day</label>
                    <input type="number" name="max_conversions_per_day" value="50">
                </div>
                <button type="submit" class="btn btn-primary">Add User</button>
                <button type="button" class="btn" onclick="hideAddUserModal()">Cancel</button>
            </form>
        </div>
    </div>

    <script>
        async function loadSummary() {
            const res = await fetch('/api/admin/reports/summary');
            const data = await res.json();
            document.getElementById('summaryCards').innerHTML = `
                <div class="card">
                    <h3>Total Users</h3>
                    <div class="value">${data.users.total_approved}</div>
                    <div class="sub">${data.users.pending_requests} pending requests</div>
                </div>
                <div class="card">
                    <h3>Conversions Today</h3>
                    <div class="value">${data.conversions.today}</div>
                    <div class="sub">${data.conversions.this_week} this week</div>
                </div>
                <div class="card">
                    <h3>Total Conversions</h3>
                    <div class="value">${data.conversions.total}</div>
                    <div class="sub">${data.conversions.success_rate}% success rate</div>
                </div>
                <div class="card">
                    <h3>Storage Used</h3>
                    <div class="value">${data.storage.total_output_mb} MB</div>
                    <div class="sub">Output files generated</div>
                </div>
            `;
        }

        async function loadUsers() {
            const res = await fetch('/api/admin/users');
            const data = await res.json();
            document.getElementById('usersTable').innerHTML = data.users.map(u => `
                <tr>
                    <td>${u.email}</td>
                    <td>${u.name || '-'}</td>
                    <td>${u.is_admin ? 'Yes' : 'No'}</td>
                    <td>${u.is_active ? 'Yes' : 'No'}</td>
                    <td>${new Date(u.approved_at).toLocaleDateString()}</td>
                    <td>
                        <button class="btn btn-primary" onclick="toggleUserActive(${u.id}, ${!u.is_active})">${u.is_active ? 'Deactivate' : 'Activate'}</button>
                    </td>
                </tr>
            `).join('');
        }

        async function loadRequests() {
            const res = await fetch('/api/admin/requests?status=all');
            const data = await res.json();
            document.getElementById('requestsTable').innerHTML = data.requests.map(r => `
                <tr>
                    <td>${r.email}</td>
                    <td>${r.name || '-'}</td>
                    <td>${r.reason || '-'}</td>
                    <td>${new Date(r.requested_at).toLocaleDateString()}</td>
                    <td><span class="status status-${r.status}">${r.status}</span></td>
                    <td>
                        ${r.status === 'pending' ? `
                            <button class="btn btn-approve" onclick="approveRequest(${r.id})">Approve</button>
                            <button class="btn btn-deny" onclick="denyRequest(${r.id})">Deny</button>
                        ` : '-'}
                    </td>
                </tr>
            `).join('');
        }

        async function loadConversions() {
            const res = await fetch('/api/admin/reports/conversions?limit=100');
            const data = await res.json();
            document.getElementById('conversionsTable').innerHTML = data.conversions.map(c => `
                <tr>
                    <td>${new Date(c.timestamp).toLocaleString()}</td>
                    <td>${c.user_email || 'anonymous'}</td>
                    <td>${c.input_filename}</td>
                    <td>${(c.input_file_size / 1024).toFixed(1)} KB</td>
                    <td><span class="status status-${c.status}">${c.status}</span></td>
                    <td>${c.processing_time ? c.processing_time.toFixed(2) + 's' : '-'}</td>
                </tr>
            `).join('');
        }

        async function loadLogins() {
            const res = await fetch('/api/admin/reports/logins?limit=100');
            const data = await res.json();
            document.getElementById('loginsTable').innerHTML = data.logins.map(l => `
                <tr>
                    <td>${new Date(l.timestamp).toLocaleString()}</td>
                    <td>${l.user_email}</td>
                    <td>${l.user_name}</td>
                    <td>${l.client_ip}</td>
                    <td>${l.success ? 'Yes' : 'No'}</td>
                </tr>
            `).join('');
        }

        async function loadActivity() {
            const res = await fetch('/api/admin/reports/users-activity');
            const data = await res.json();
            document.getElementById('activityTable').innerHTML = data.users.map(u => `
                <tr>
                    <td>${u.email || 'anonymous'}</td>
                    <td>${u.conversion_count}</td>
                    <td>${u.total_input_mb} MB</td>
                    <td>${u.last_conversion ? new Date(u.last_conversion).toLocaleDateString() : '-'}</td>
                </tr>
            `).join('');
        }

        function showTab(tab) {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.section').forEach(s => s.style.display = 'none');
            event.target.classList.add('active');
            document.getElementById(tab + 'Tab').style.display = 'block';
        }

        async function approveRequest(id) {
            if (!confirm('Approve this request?')) return;
            await fetch(`/api/admin/requests/${id}/approve`, { method: 'POST' });
            loadRequests();
            loadUsers();
            loadSummary();
        }

        async function denyRequest(id) {
            if (!confirm('Deny this request?')) return;
            await fetch(`/api/admin/requests/${id}/deny`, { method: 'POST' });
            loadRequests();
        }

        async function toggleUserActive(id, active) {
            await fetch(`/api/admin/users/${id}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ is_active: active })
            });
            loadUsers();
        }

        function showAddUserModal() {
            document.getElementById('addUserModal').classList.add('show');
        }

        function hideAddUserModal() {
            document.getElementById('addUserModal').classList.remove('show');
        }

        document.getElementById('addUserForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const form = e.target;
            const data = {
                email: form.email.value,
                name: form.name.value,
                is_admin: form.is_admin.checked,
                notes: form.notes.value,
                max_conversions_per_day: parseInt(form.max_conversions_per_day.value)
            };

            const res = await fetch('/api/admin/users', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });

            if (res.ok) {
                hideAddUserModal();
                form.reset();
                loadUsers();
                loadSummary();
            } else {
                const err = await res.json();
                alert(err.error);
            }
        });

        // Check auth status
        fetch('/auth/status').then(r => r.json()).then(data => {
            if (data.authenticated && data.user) {
                document.getElementById('adminEmail').textContent = data.user.email;
            }
        });

        // Load all data
        loadSummary();
        loadUsers();
        loadRequests();
        loadConversions();
        loadLogins();
        loadActivity();
    </script>
</body>
</html>
'''

@admin_bp.route('/admin')
@require_admin
def admin_dashboard():
    """Serve admin dashboard"""
    return render_template_string(ADMIN_DASHBOARD_HTML)
