import os
import sys
import uuid
import asyncio
import threading
import time
import ipaddress
import json
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Blueprint, request, jsonify, send_file
from werkzeug.utils import secure_filename
from functools import wraps
from flask import session

# Add jpk2json to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'jpk2json'))

# Import database models
from src.models.user import db, ConversionLog, RateLimitLog, PageLoadLog, LoginLog

flask_async_converter_bp = Blueprint('flask_async_converter', __name__)

# Store conversion status
conversion_status = {}
UPLOAD_FOLDER = '/tmp/jpk_uploads'
OUTPUT_FOLDER = '/tmp/jpk_outputs'

# Thread pool for CPU-intensive conversion tasks
executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="JPKConverter")

# Ensure directories exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# Rate limiting configuration
RATE_LIMIT_REQUESTS = 10  # requests per minute
RATE_LIMIT_WINDOW = 60    # seconds

# IP Blacklist configuration
BLACKLIST_FILE = os.path.join(os.path.dirname(__file__), '..', '..', 'config', 'ip_blacklist.json')
ip_blacklist = []

def load_ip_blacklist():
    """Load IP blacklist from configuration file"""
    global ip_blacklist
    try:
        if os.path.exists(BLACKLIST_FILE):
            with open(BLACKLIST_FILE, 'r') as f:
                data = json.load(f)
                ip_blacklist = data.get('blacklisted_ips', [])
                print(f"Loaded {len(ip_blacklist)} blacklisted IP(s)/range(s)")
        else:
            # Create default blacklist file
            os.makedirs(os.path.dirname(BLACKLIST_FILE), exist_ok=True)
            default_blacklist = {
                "blacklisted_ips": [],
                "description": "IP addresses and CIDR ranges to block from accessing the converter",
                "examples": [
                    "192.168.1.100",
                    "10.0.0.0/24", 
                    "172.16.0.0/16"
                ]
            }
            with open(BLACKLIST_FILE, 'w') as f:
                json.dump(default_blacklist, f, indent=2)
            ip_blacklist = []
    except Exception as e:
        print(f"Error loading IP blacklist: {e}")
        ip_blacklist = []

def save_ip_blacklist():
    """Save IP blacklist to configuration file"""
    try:
        os.makedirs(os.path.dirname(BLACKLIST_FILE), exist_ok=True)
        data = {
            "blacklisted_ips": ip_blacklist,
            "description": "IP addresses and CIDR ranges to block from accessing the converter",
            "last_updated": datetime.now().isoformat(),
            "examples": [
                "192.168.1.100",
                "10.0.0.0/24", 
                "172.16.0.0/16"
            ]
        }
        with open(BLACKLIST_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving IP blacklist: {e}")
        return False

def is_ip_blacklisted(ip_address):
    """Check if an IP address is blacklisted"""
    try:
        client_ip = ipaddress.ip_address(ip_address)
        
        for blacklisted_entry in ip_blacklist:
            try:
                # Check if it's a single IP or CIDR range
                if '/' in blacklisted_entry:
                    # CIDR range
                    network = ipaddress.ip_network(blacklisted_entry, strict=False)
                    if client_ip in network:
                        return True
                else:
                    # Single IP
                    blacklisted_ip = ipaddress.ip_address(blacklisted_entry)
                    if client_ip == blacklisted_ip:
                        return True
            except ValueError:
                # Invalid IP format in blacklist, skip
                continue
        
        return False
    except ValueError:
        # Invalid client IP format
        return False

# Load blacklist on startup
load_ip_blacklist()

def require_auth(f):
    """Authentication decorator - requires user to be logged in"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return jsonify({
                'error': 'Authentication required',
                'message': 'Please log in to use this service',
                'redirect': '/login'
            }), 401
        return f(*args, **kwargs)
    return decorated_function

def get_client_ip():
    """Get client IP address, handling proxies"""
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    elif request.headers.get('X-Real-IP'):
        return request.headers.get('X-Real-IP')
    else:
        return request.remote_addr

def rate_limit(max_requests=RATE_LIMIT_REQUESTS, window_seconds=RATE_LIMIT_WINDOW):
    """Rate limiting decorator with IP blacklist checking"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            client_ip = get_client_ip()
            
            # Check if IP is blacklisted first
            if is_ip_blacklisted(client_ip):
                return jsonify({
                    'error': 'Access denied',
                    'message': 'Your IP address has been blocked',
                    'ip': client_ip
                }), 403
            
            endpoint = request.endpoint
            now = datetime.utcnow()
            window_start = now - timedelta(seconds=window_seconds)
            
            # Count recent requests from this IP for this endpoint
            recent_requests = RateLimitLog.query.filter(
                RateLimitLog.client_ip == client_ip,
                RateLimitLog.endpoint == endpoint,
                RateLimitLog.timestamp >= window_start
            ).count()
            
            if recent_requests >= max_requests:
                return jsonify({
                    'error': 'Rate limit exceeded',
                    'message': f'Maximum {max_requests} requests per {window_seconds} seconds allowed',
                    'retry_after': window_seconds,
                    'ip': client_ip
                }), 429
            
            # Log this request
            rate_log = RateLimitLog(
                client_ip=client_ip,
                endpoint=endpoint,
                timestamp=now
            )
            db.session.add(rate_log)
            db.session.commit()
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def allowed_file(filename):
    """Check if file has allowed extension"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() == 'jpk'

def run_conversion_sync(job_id, input_path, output_path, input_filename, input_file_size, client_ip, user_email, user_name, app):
    """Synchronous conversion function to run in thread pool"""
    start_time = time.time()
    
    # Use Flask app context for database operations
    with app.app_context():
        try:
            conversion_status[job_id] = {
                'status': 'processing',
                'message': 'Starting conversion...',
                'progress': 10
            }
            
            # Import the converter with proper path handling
            import sys
            import os
            converter_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'jpk2json')
            if converter_path not in sys.path:
                sys.path.insert(0, converter_path)
            
            from converter import main as converter_main
            
            conversion_status[job_id] = {
                'status': 'processing',
                'message': 'Loading JPK file...',
                'progress': 30
            }
            
            # Create arguments for the converter
            converter_args = type('Args', (), {
                'jpk_path': input_path,
                'output_path': output_path,
                'verbose': False
            })()
            
            conversion_status[job_id] = {
                'status': 'processing',
                'message': 'Converting JPK to JSON...',
                'progress': 60
            }
            
            # Run the conversion with detailed logging
            print(f"🔄 Starting conversion: {input_path} -> {output_path}")
            print(f"📊 Input file size: {input_file_size} bytes")
            
            try:
                exit_code = converter_main(converter_args)
                print(f"✅ Converter exit code: {exit_code}")
            except Exception as conv_error:
                print(f"❌ Converter exception: {conv_error}")
                raise conv_error
            
            processing_time = time.time() - start_time
            print(f"⏱️ Processing time: {processing_time:.2f} seconds")
            
            if exit_code == 0 and os.path.exists(output_path):
                file_size = os.path.getsize(output_path)
                print(f"📁 Output file size: {file_size} bytes ({file_size/1024/1024:.2f} MB)")
                conversion_status[job_id] = {
                    'status': 'completed',
                    'message': f'Conversion completed successfully! Output size: {file_size / (1024*1024):.1f} MB',
                    'progress': 100,
                    'output_file': output_path,
                    'file_size': file_size
                }
                
                # Update database log with success
                log_entry = ConversionLog.query.filter_by(job_id=job_id).first()
                if log_entry:
                    log_entry.status = 'completed'
                    log_entry.output_file_size = file_size
                    log_entry.processing_time = processing_time
                    db.session.commit()
            else:
                error_msg = f'Conversion failed - exit code: {exit_code}'
                if not os.path.exists(output_path):
                    error_msg += ', output file not created'
                print(f"DEBUG: {error_msg}")
                conversion_status[job_id] = {
                    'status': 'error',
                    'message': error_msg,
                    'progress': 0
                }
                
                # Update database log with error
                log_entry = ConversionLog.query.filter_by(job_id=job_id).first()
                if log_entry:
                    log_entry.status = 'error'
                    log_entry.processing_time = processing_time
                    log_entry.error_message = error_msg
                    db.session.commit()
                
        except Exception as e:
            processing_time = time.time() - start_time
            error_message = f'Conversion error: {str(e)}'
            conversion_status[job_id] = {
                'status': 'error',
                'message': error_message,
                'progress': 0
            }
            
            # Update database log with exception
            log_entry = ConversionLog.query.filter_by(job_id=job_id).first()
            if log_entry:
                log_entry.status = 'error'
                log_entry.processing_time = processing_time
                log_entry.error_message = error_message
                db.session.commit()

@flask_async_converter_bp.route('/upload', methods=['POST'])
@require_auth
@rate_limit(max_requests=5, window_seconds=60)  # 5 uploads per minute
def upload_file():
    """Handle file upload and start asynchronous conversion"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if not allowed_file(file.filename):
            return jsonify({'error': 'Only JPK files are allowed'}), 400
        
        # Generate unique job ID
        job_id = str(uuid.uuid4())
        client_ip = get_client_ip()
        
        # Save uploaded file
        filename = secure_filename(file.filename)
        input_path = os.path.join(UPLOAD_FOLDER, f"{job_id}_{filename}")
        file.save(input_path)
        input_file_size = os.path.getsize(input_path)
        
        # Determine output path
        output_filename = f"{os.path.splitext(filename)[0]}.json"
        output_path = os.path.join(OUTPUT_FOLDER, f"{job_id}_{output_filename}")
        
        # Log conversion to database
        user_info = session.get('user', {})
        conversion_log = ConversionLog(
            job_id=job_id,
            client_ip=client_ip,
            user_email=user_info.get('email'),
            user_name=user_info.get('name'),
            input_filename=filename,
            input_file_size=input_file_size,
            status='processing'
        )
        db.session.add(conversion_log)
        db.session.commit()
        
        # Initialize status
        conversion_status[job_id] = {
            'status': 'queued',
            'message': 'File uploaded successfully, queued for conversion',
            'progress': 0,
            'filename': filename
        }
        
        # Submit conversion task to thread pool with Flask app context
        from flask import current_app
        app = current_app._get_current_object()
        user_info = session.get('user', {})
        future = executor.submit(run_conversion_sync, job_id, input_path, output_path, filename, input_file_size, client_ip, user_info.get('email'), user_info.get('name'), app)
        
        return jsonify({
            'job_id': job_id,
            'message': 'File uploaded successfully, conversion started asynchronously',
            'filename': filename
        })
        
    except Exception as e:
        return jsonify({'error': f'Upload failed: {str(e)}'}), 500

@flask_async_converter_bp.route('/status/<job_id>', methods=['GET'])
@require_auth
def get_status(job_id):
    """Get conversion status"""
    if job_id not in conversion_status:
        return jsonify({'error': 'Job not found'}), 404
    
    return jsonify(conversion_status[job_id])

@flask_async_converter_bp.route('/download/<job_id>', methods=['GET'])
@require_auth
def download_file(job_id):
    """Download converted file"""
    if job_id not in conversion_status:
        return jsonify({'error': 'Job not found'}), 404
    
    status = conversion_status[job_id]
    if status['status'] != 'completed':
        return jsonify({'error': 'Conversion not completed'}), 400
    
    if 'output_file' not in status or not os.path.exists(status['output_file']):
        return jsonify({'error': 'Output file not found'}), 404
    
    # Get original filename for download
    original_filename = status.get('filename', 'converted.json')
    download_filename = f"{os.path.splitext(original_filename)[0]}.json"
    
    return send_file(
        status['output_file'],
        as_attachment=True,
        download_name=download_filename,
        mimetype='application/json'
    )

@flask_async_converter_bp.route('/cleanup/<job_id>', methods=['DELETE'])
def cleanup_job(job_id):
    """Clean up job files and status"""
    if job_id in conversion_status:
        status = conversion_status[job_id]
        
        # Clean up files
        input_file = os.path.join(UPLOAD_FOLDER, f"{job_id}_*")
        output_file = status.get('output_file')
        
        try:
            # Remove input file
            import glob
            for f in glob.glob(input_file):
                if os.path.exists(f):
                    os.remove(f)
            
            # Remove output file
            if output_file and os.path.exists(output_file):
                os.remove(output_file)
        except:
            pass
        
        # Remove from status
        del conversion_status[job_id]
    
    return jsonify({'message': 'Job cleaned up successfully'})

@flask_async_converter_bp.route('/queue/status', methods=['GET'])
def get_queue_status():
    """Get overall queue status and statistics"""
    total_jobs = len(conversion_status)
    queued = sum(1 for status in conversion_status.values() if status['status'] == 'queued')
    processing = sum(1 for status in conversion_status.values() if status['status'] == 'processing')
    completed = sum(1 for status in conversion_status.values() if status['status'] == 'completed')
    errors = sum(1 for status in conversion_status.values() if status['status'] == 'error')
    
    # Get active thread count
    active_threads = threading.active_count()
    
    return jsonify({
        'total_jobs': total_jobs,
        'queued': queued,
        'processing': processing,
        'completed': completed,
        'errors': errors,
        'active_threads': active_threads,
        'max_workers': executor._max_workers
    })

@flask_async_converter_bp.route('/batch/upload', methods=['POST'])
@require_auth
def batch_upload():
    """Handle multiple file uploads for batch processing"""
    try:
        files = request.files.getlist('files')
        if not files or all(f.filename == '' for f in files):
            return jsonify({'error': 'No files provided'}), 400
        
        job_ids = []
        results = []
        futures = []
        
        for file in files:
            if not allowed_file(file.filename):
                results.append({
                    'filename': file.filename,
                    'status': 'error',
                    'message': 'Only JPK files are allowed'
                })
                continue
            
            # Generate unique job ID
            job_id = str(uuid.uuid4())
            job_ids.append(job_id)
            
            # Save uploaded file
            filename = secure_filename(file.filename)
            input_path = os.path.join(UPLOAD_FOLDER, f"{job_id}_{filename}")
            file.save(input_path)
            
            # Determine output path
            output_filename = f"{os.path.splitext(filename)[0]}.json"
            output_path = os.path.join(OUTPUT_FOLDER, f"{job_id}_{output_filename}")
            
            # Initialize status
            conversion_status[job_id] = {
                'status': 'queued',
                'message': 'File uploaded successfully, queued for batch conversion',
                'progress': 0,
                'filename': filename
            }
            
            # Submit conversion task to thread pool
            from flask import current_app
            app = current_app._get_current_object()
            future = executor.submit(run_conversion_sync, job_id, input_path, output_path, filename, input_file_size, client_ip, app)
            futures.append(future)
            
            results.append({
                'filename': filename,
                'job_id': job_id,
                'status': 'queued',
                'message': 'File uploaded successfully, conversion started asynchronously'
            })
        
        return jsonify({
            'message': f'Batch upload completed: {len(job_ids)} files queued for conversion',
            'job_ids': job_ids,
            'results': results
        })
        
    except Exception as e:
        return jsonify({'error': f'Batch upload failed: {str(e)}'}), 500

@flask_async_converter_bp.route('/batch/status', methods=['POST'])
@require_auth
def batch_status():
    """Get status for multiple jobs"""
    try:
        data = request.get_json()
        job_ids = data.get('job_ids', [])
        
        if not job_ids:
            return jsonify({'error': 'No job IDs provided'}), 400
        
        statuses = {}
        for job_id in job_ids:
            if job_id in conversion_status:
                statuses[job_id] = conversion_status[job_id]
            else:
                statuses[job_id] = {'status': 'not_found', 'message': 'Job not found'}
        
        return jsonify({'statuses': statuses})
        
    except Exception as e:
        return jsonify({'error': f'Batch status check failed: {str(e)}'}), 500

@flask_async_converter_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'service': 'JPK to JSON Converter',
        'version': 'async-v1.0',
        'thread_pool_size': executor._max_workers,
        'active_jobs': len(conversion_status)
    })

@flask_async_converter_bp.route('/admin/conversions', methods=['GET'])
@rate_limit(max_requests=30, window_seconds=60)  # 30 requests per minute for admin
def get_conversion_history():
    """Get conversion history (admin endpoint)"""
    try:
        # Get query parameters
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 50, type=int), 100)  # Max 100 per page
        status_filter = request.args.get('status', None)
        ip_filter = request.args.get('ip', None)
        
        # Build query
        query = ConversionLog.query
        
        if status_filter:
            query = query.filter(ConversionLog.status == status_filter)
        if ip_filter:
            query = query.filter(ConversionLog.client_ip == ip_filter)
        
        # Order by most recent first
        query = query.order_by(ConversionLog.timestamp.desc())
        
        # Paginate
        conversions = query.paginate(
            page=page, 
            per_page=per_page, 
            error_out=False
        )
        
        # Calculate statistics
        total_conversions = ConversionLog.query.count()
        completed_conversions = ConversionLog.query.filter_by(status='completed').count()
        failed_conversions = ConversionLog.query.filter_by(status='error').count()
        
        # Calculate total data processed
        total_input_size = db.session.query(db.func.sum(ConversionLog.input_file_size)).scalar() or 0
        total_output_size = db.session.query(db.func.sum(ConversionLog.output_file_size)).scalar() or 0
        
        return jsonify({
            'conversions': [conv.to_dict() for conv in conversions.items],
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': conversions.total,
                'pages': conversions.pages,
                'has_next': conversions.has_next,
                'has_prev': conversions.has_prev
            },
            'statistics': {
                'total_conversions': total_conversions,
                'completed_conversions': completed_conversions,
                'failed_conversions': failed_conversions,
                'success_rate': round((completed_conversions / total_conversions * 100), 2) if total_conversions > 0 else 0,
                'total_input_size_mb': round(total_input_size / (1024*1024), 2),
                'total_output_size_mb': round(total_output_size / (1024*1024), 2)
            }
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to retrieve conversion history: {str(e)}'}), 500

@flask_async_converter_bp.route('/admin/stats', methods=['GET'])
@rate_limit(max_requests=60, window_seconds=60)  # 60 requests per minute for stats
def get_conversion_stats():
    """Get conversion statistics"""
    try:
        # Get date range from query params
        days = request.args.get('days', 7, type=int)
        since = datetime.utcnow() - timedelta(days=days)
        
        # Recent conversions
        recent_conversions = ConversionLog.query.filter(
            ConversionLog.timestamp >= since
        ).count()
        
        # Recent successful conversions
        recent_successful = ConversionLog.query.filter(
            ConversionLog.timestamp >= since,
            ConversionLog.status == 'completed'
        ).count()
        
        # Top IPs by conversion count
        top_ips = db.session.query(
            ConversionLog.client_ip,
            db.func.count(ConversionLog.id).label('count')
        ).group_by(ConversionLog.client_ip).order_by(
            db.func.count(ConversionLog.id).desc()
        ).limit(10).all()
        
        # Average processing time
        avg_processing_time = db.session.query(
            db.func.avg(ConversionLog.processing_time)
        ).filter(
            ConversionLog.processing_time.isnot(None)
        ).scalar()
        
        return jsonify({
            'period_days': days,
            'recent_conversions': recent_conversions,
            'recent_successful': recent_successful,
            'recent_success_rate': round((recent_successful / recent_conversions * 100), 2) if recent_conversions > 0 else 0,
            'top_ips': [{'ip': ip, 'count': count} for ip, count in top_ips],
            'average_processing_time_seconds': round(avg_processing_time, 2) if avg_processing_time else None
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to retrieve statistics: {str(e)}'}), 500

@flask_async_converter_bp.route('/admin/blacklist', methods=['GET'])
@rate_limit(max_requests=30, window_seconds=60)  # Higher limit for admin
def get_blacklist():
    """Get current IP blacklist"""
    try:
        return jsonify({
            'blacklisted_ips': ip_blacklist,
            'total_count': len(ip_blacklist),
            'config_file': BLACKLIST_FILE
        })
    except Exception as e:
        return jsonify({'error': f'Failed to retrieve blacklist: {str(e)}'}), 500

@flask_async_converter_bp.route('/admin/blacklist/add', methods=['POST'])
@rate_limit(max_requests=20, window_seconds=60)  # Admin endpoint
def add_to_blacklist():
    """Add IP address or CIDR range to blacklist"""
    try:
        data = request.get_json()
        if not data or 'ip' not in data:
            return jsonify({'error': 'IP address or CIDR range required'}), 400
        
        ip_to_add = data['ip'].strip()
        
        # Validate IP address or CIDR range
        try:
            if '/' in ip_to_add:
                # CIDR range
                ipaddress.ip_network(ip_to_add, strict=False)
            else:
                # Single IP
                ipaddress.ip_address(ip_to_add)
        except ValueError:
            return jsonify({'error': 'Invalid IP address or CIDR range format'}), 400
        
        # Check if already blacklisted
        if ip_to_add in ip_blacklist:
            return jsonify({'error': 'IP/range already blacklisted'}), 409
        
        # Add to blacklist
        ip_blacklist.append(ip_to_add)
        
        # Save to file
        if save_ip_blacklist():
            return jsonify({
                'message': f'Successfully added {ip_to_add} to blacklist',
                'blacklisted_ips': ip_blacklist,
                'total_count': len(ip_blacklist)
            })
        else:
            # Remove from memory if save failed
            ip_blacklist.remove(ip_to_add)
            return jsonify({'error': 'Failed to save blacklist to file'}), 500
            
    except Exception as e:
        return jsonify({'error': f'Failed to add to blacklist: {str(e)}'}), 500

@flask_async_converter_bp.route('/admin/blacklist/remove', methods=['POST'])
@rate_limit(max_requests=20, window_seconds=60)  # Admin endpoint
def remove_from_blacklist():
    """Remove IP address or CIDR range from blacklist"""
    try:
        data = request.get_json()
        if not data or 'ip' not in data:
            return jsonify({'error': 'IP address or CIDR range required'}), 400
        
        ip_to_remove = data['ip'].strip()
        
        # Check if in blacklist
        if ip_to_remove not in ip_blacklist:
            return jsonify({'error': 'IP/range not found in blacklist'}), 404
        
        # Remove from blacklist
        ip_blacklist.remove(ip_to_remove)
        
        # Save to file
        if save_ip_blacklist():
            return jsonify({
                'message': f'Successfully removed {ip_to_remove} from blacklist',
                'blacklisted_ips': ip_blacklist,
                'total_count': len(ip_blacklist)
            })
        else:
            # Add back to memory if save failed
            ip_blacklist.append(ip_to_remove)
            return jsonify({'error': 'Failed to save blacklist to file'}), 500
            
    except Exception as e:
        return jsonify({'error': f'Failed to remove from blacklist: {str(e)}'}), 500

@flask_async_converter_bp.route('/admin/blacklist/check', methods=['POST'])
@rate_limit(max_requests=50, window_seconds=60)  # Higher limit for checking
def check_ip_blacklist():
    """Check if an IP address is blacklisted"""
    try:
        data = request.get_json()
        if not data or 'ip' not in data:
            return jsonify({'error': 'IP address required'}), 400
        
        ip_to_check = data['ip'].strip()
        
        # Validate IP address
        try:
            ipaddress.ip_address(ip_to_check)
        except ValueError:
            return jsonify({'error': 'Invalid IP address format'}), 400
        
        is_blocked = is_ip_blacklisted(ip_to_check)
        
        # Find which rule matched (if any)
        matched_rule = None
        if is_blocked:
            client_ip = ipaddress.ip_address(ip_to_check)
            for blacklisted_entry in ip_blacklist:
                try:
                    if '/' in blacklisted_entry:
                        network = ipaddress.ip_network(blacklisted_entry, strict=False)
                        if client_ip in network:
                            matched_rule = blacklisted_entry
                            break
                    else:
                        blacklisted_ip = ipaddress.ip_address(blacklisted_entry)
                        if client_ip == blacklisted_ip:
                            matched_rule = blacklisted_entry
                            break
                except ValueError:
                    continue
        
        return jsonify({
            'ip': ip_to_check,
            'is_blacklisted': is_blocked,
            'matched_rule': matched_rule,
            'total_blacklist_entries': len(ip_blacklist)
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to check IP: {str(e)}'}), 500

@flask_async_converter_bp.route('/admin/blacklist/reload', methods=['POST'])
@rate_limit(max_requests=10, window_seconds=60)  # Admin endpoint
def reload_blacklist():
    """Reload IP blacklist from configuration file"""
    try:
        old_count = len(ip_blacklist)
        load_ip_blacklist()
        new_count = len(ip_blacklist)
        
        return jsonify({
            'message': 'Blacklist reloaded successfully',
            'old_count': old_count,
            'new_count': new_count,
            'blacklisted_ips': ip_blacklist
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to reload blacklist: {str(e)}'}), 500
