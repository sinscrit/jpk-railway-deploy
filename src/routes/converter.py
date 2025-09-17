import os
import sys
import uuid
import subprocess
import threading
import time
from flask import Blueprint, request, jsonify, send_file
from werkzeug.utils import secure_filename

# Add jpk2json to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'jpk2json'))

converter_bp = Blueprint('converter', __name__)

# Store conversion status
conversion_status = {}
UPLOAD_FOLDER = '/tmp/jpk_uploads'
OUTPUT_FOLDER = '/tmp/jpk_outputs'

# Ensure directories exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

def allowed_file(filename):
    """Check if file has allowed extension"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() == 'jpk'

def run_conversion(job_id, input_path, output_path):
    """Run the JPK to JSON conversion in a separate thread"""
    try:
        conversion_status[job_id] = {
            'status': 'processing',
            'message': 'Starting conversion...',
            'progress': 10
        }
        
        # Import the converter
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
        
        # Run the conversion
        exit_code = converter_main(converter_args)
        
        if exit_code == 0 and os.path.exists(output_path):
            file_size = os.path.getsize(output_path)
            conversion_status[job_id] = {
                'status': 'completed',
                'message': f'Conversion completed successfully! Output size: {file_size / (1024*1024):.1f} MB',
                'progress': 100,
                'output_file': output_path,
                'file_size': file_size
            }
        else:
            conversion_status[job_id] = {
                'status': 'error',
                'message': 'Conversion failed - please check your JPK file',
                'progress': 0
            }
            
    except Exception as e:
        conversion_status[job_id] = {
            'status': 'error',
            'message': f'Conversion error: {str(e)}',
            'progress': 0
        }

@converter_bp.route('/upload', methods=['POST'])
def upload_file():
    """Handle file upload and start conversion"""
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
            'message': 'File uploaded successfully, queued for conversion',
            'progress': 0,
            'filename': filename
        }
        
        # Start conversion in background thread
        thread = threading.Thread(target=run_conversion, args=(job_id, input_path, output_path))
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'job_id': job_id,
            'message': 'File uploaded successfully, conversion started',
            'filename': filename
        })
        
    except Exception as e:
        return jsonify({'error': f'Upload failed: {str(e)}'}), 500

@converter_bp.route('/status/<job_id>', methods=['GET'])
def get_status(job_id):
    """Get conversion status"""
    if job_id not in conversion_status:
        return jsonify({'error': 'Job not found'}), 404
    
    return jsonify(conversion_status[job_id])

@converter_bp.route('/download/<job_id>', methods=['GET'])
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

@converter_bp.route('/cleanup/<job_id>', methods=['DELETE'])
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
