# JPK to JSON Converter - Project Context

## Quick Reference

### Local Development
- **Local URL**: http://localhost:8080/
- **Framework**: Flask (Python 3.11)
- **Entry Point**: `src/main.py` or `app.py`

### Production URLs
- **Production Domain**: https://j2j.iointegrated.com
- **Railway Deployment**: https://jbjpk2json-production.up.railway.app

## Project Overview

A high-performance asynchronous web service for converting Jitterbit JPK files to JSON format with concurrent processing capabilities.

### Key Features
- Asynchronous processing with thread pool (4 concurrent workers)
- Batch upload support for multiple JPK files
- Real-time queue monitoring dashboard
- REST API with 8+ endpoints
- Google OAuth authentication
- IP blacklisting and rate limiting

## Important Files

| File | Purpose |
|------|---------|
| `src/main.py` | Flask app initialization & startup validation |
| `src/routes/flask_async_converter.py` | Main converter routes & async processing |
| `src/routes/auth.py` | OAuth authentication routes |
| `config/oauth_config.json` | Google OAuth credentials (gitignored) |
| `config/ip_blacklist.json` | IP blacklist configuration |
| `jpk2json/converter.py` | Core converter logic |

## API Endpoints

### File Operations
- `POST /api/converter/upload` - Upload single JPK file
- `POST /api/converter/batch/upload` - Upload multiple JPK files
- `GET /api/converter/download/{job_id}` - Download converted JSON
- `DELETE /api/converter/cleanup/{job_id}` - Clean up job files

### Status & Monitoring
- `GET /api/converter/status/{job_id}` - Get conversion status
- `GET /api/converter/queue/status` - Get queue statistics
- `GET /api/converter/health` - Health check endpoint

### Admin
- `GET /admin/blacklist` - View IP blacklist
- `GET /admin/files` - Runtime file verification

## Known Issues

1. **OAuth Configuration**: Google OAuth may have redirect_uri_mismatch errors
   - See `OAUTH_FIX_REQUIRED.md` for details
   - Workaround: Can disable OAuth if needed

2. **Railway Deployment**: Previously had path resolution issues for converter libraries
   - Status: Fixed in recent commits

## Running Locally

```bash
# Default command
PORT=8080 python src/main.py

# Or via gunicorn
gunicorn --bind 0.0.0.0:8080 --workers 1 --threads 4 --timeout 600 wsgi:app
```

## Testing

- Test files available in `baseline/` directory
- Conversion parity tests: `python test_conversion_parity.py`
- Deployment validation: `python deployment_check.py`
