# JPK to JSON Converter - Railway Deployment

A high-performance asynchronous web service for converting Jitterbit JPK files to JSON format with concurrent processing capabilities.

## 🚀 Features

- **Asynchronous Processing**: Thread pool with 4 concurrent workers
- **Batch Upload Support**: Process multiple JPK files simultaneously
- **Real-time Queue Monitoring**: Live status dashboard with progress tracking
- **Professional Web Interface**: Modern, responsive design with drag & drop
- **REST API**: Complete RESTful API for programmatic access
- **Auto Cleanup**: Automatic file cleanup after processing

## 📦 Railway Deployment Instructions

### Method 1: Deploy from GitHub (Recommended)

1. **Fork or Clone this Repository**
   ```bash
   git clone <your-repo-url>
   cd jpk-railway-deploy
   ```

2. **Deploy on Railway**
   - Go to [Railway.app](https://railway.app)
   - Click "New Project"
   - Select "Deploy from GitHub repo"
   - Choose your repository
   - Railway will automatically detect the configuration and deploy

3. **Environment Variables** (Optional)
   - `PORT`: Automatically set by Railway
   - `FLASK_ENV`: Set to `production` (default)

### Method 2: Deploy via Railway CLI

1. **Install Railway CLI**
   ```bash
   npm install -g @railway/cli
   ```

2. **Login to Railway**
   ```bash
   railway login
   ```

3. **Initialize and Deploy**
   ```bash
   railway init
   railway up
   ```

### Method 3: Deploy from Local Directory

1. **Upload Files to Railway**
   - Create a new project on Railway
   - Connect to GitHub or upload files directly
   - Railway will automatically build and deploy

## 🔧 Configuration Files

This package includes all necessary Railway configuration files:

- **`Procfile`**: Defines the web process command
- **`railway.json`**: Railway-specific configuration
- **`nixpacks.toml`**: Build configuration for Nixpacks
- **`requirements.txt`**: Python dependencies
- **`runtime.txt`**: Python version specification
- **`wsgi.py`**: WSGI entry point for production
- **`app.py`**: Alternative entry point

## 🌐 API Endpoints

Once deployed, your service will have these endpoints:

### File Operations
- `POST /api/converter/upload` - Upload single JPK file
- `POST /api/converter/batch/upload` - Upload multiple JPK files
- `GET /api/converter/download/{job_id}` - Download converted JSON
- `DELETE /api/converter/cleanup/{job_id}` - Clean up job files

### Status & Monitoring
- `GET /api/converter/status/{job_id}` - Get conversion status
- `GET /api/converter/queue/status` - Get queue statistics
- `GET /api/converter/health` - Health check endpoint

### Batch Operations
- `POST /api/converter/batch/status` - Get status for multiple jobs

## 📊 Usage Examples

### Single File Upload
```bash
curl -X POST -F "file=@example.jpk" https://your-app.railway.app/api/converter/upload
```

### Check Status
```bash
curl https://your-app.railway.app/api/converter/status/{job_id}
```

### Download Result
```bash
curl -O https://your-app.railway.app/api/converter/download/{job_id}
```

## 🔍 Monitoring

### Health Check
```bash
curl https://your-app.railway.app/api/converter/health
```

### Queue Status
```bash
curl https://your-app.railway.app/api/converter/queue/status
```

## 🛠 Technical Specifications

- **Framework**: Flask with ThreadPoolExecutor
- **Concurrent Workers**: 4 simultaneous conversions
- **File Support**: JPK files up to 100MB
- **Output Format**: Comprehensive JSON with metadata
- **Deployment**: Gunicorn WSGI server with 4 workers
- **Auto-scaling**: Railway handles scaling automatically

## 📁 Project Structure

```
jpk-railway-deploy/
├── src/                          # Application source code
│   ├── main.py                   # Flask application
│   ├── routes/                   # API routes
│   │   └── flask_async_converter.py
│   └── static/                   # Web interface
│       └── index.html
├── jpk2json/                     # JPK converter library
├── jpk2json-convert              # Converter executable
├── app.py                        # Railway entry point
├── wsgi.py                       # WSGI entry point
├── requirements.txt              # Python dependencies
├── Procfile                      # Railway process definition
├── railway.json                  # Railway configuration
├── nixpacks.toml                 # Build configuration
├── runtime.txt                   # Python version
└── README.md                     # This file
```

## 🚀 Post-Deployment

After successful deployment:

1. **Access the Web Interface**: Visit your Railway app URL
2. **Test the API**: Use the health endpoint to verify functionality
3. **Upload Test File**: Try converting a JPK file
4. **Monitor Performance**: Check the queue status dashboard

## 🔧 Troubleshooting

### Common Issues

1. **Build Failures**
   - Check that all files are properly uploaded
   - Verify Python version compatibility
   - Review Railway build logs

2. **Runtime Errors**
   - Check Railway application logs
   - Verify environment variables
   - Test health endpoint

3. **File Upload Issues**
   - Ensure JPK files are valid
   - Check file size limits (100MB max)
   - Verify network connectivity

### Support

For issues with:
- **JPK Conversion**: Check converter logs and file format
- **Railway Deployment**: Consult Railway documentation
- **API Usage**: Review endpoint documentation above

## 📈 Performance

- **Concurrent Processing**: Up to 4 simultaneous conversions
- **File Size**: Supports JPK files up to 100MB
- **Output Quality**: Comprehensive JSON with 2.6MB+ typical output
- **Response Time**: Immediate upload response, background processing
- **Scalability**: Railway auto-scales based on demand

## 🔒 Security

- **File Validation**: Only JPK files accepted
- **Auto Cleanup**: Files automatically removed after processing
- **Secure Upload**: Temporary file storage with cleanup
- **API Security**: Input validation and error handling

---

**Ready to deploy!** This package contains everything needed for a successful Railway deployment of your JPK to JSON converter service.
