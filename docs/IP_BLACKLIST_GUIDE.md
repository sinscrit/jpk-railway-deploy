# IP Blacklisting Guide

## Overview

The JPK to JSON Converter now includes comprehensive IP blacklisting functionality that allows you to block specific IP addresses or entire IP ranges from accessing the converter. This feature is integrated with the existing rate limiting system and provides both individual IP blocking and CIDR range blocking capabilities.

## Features

- ✅ **Individual IP Blocking**: Block specific IP addresses (e.g., `192.168.1.100`)
- ✅ **CIDR Range Blocking**: Block entire IP ranges (e.g., `10.0.0.0/24`, `172.16.0.0/16`)
- ✅ **Persistent Configuration**: Blacklist is saved to a JSON configuration file
- ✅ **Real-time Updates**: Changes take effect immediately without server restart
- ✅ **Admin API**: Complete REST API for managing the blacklist
- ✅ **Validation**: Automatic validation of IP addresses and CIDR ranges
- ✅ **Integration**: Seamlessly integrated with rate limiting system

## Configuration File

The blacklist is stored in: `config/ip_blacklist.json`

```json
{
  "blacklisted_ips": [
    "192.168.1.100",
    "10.0.0.0/24",
    "172.16.0.0/16"
  ],
  "description": "IP addresses and CIDR ranges to block from accessing the converter",
  "last_updated": "2025-09-17T23:58:20.957239",
  "examples": [
    "192.168.1.100",
    "10.0.0.0/24", 
    "172.16.0.0/16"
  ]
}
```

## API Endpoints

### 1. View Current Blacklist
```bash
GET /api/converter/admin/blacklist
```

**Example:**
```bash
curl http://localhost:8000/api/converter/admin/blacklist
```

**Response:**
```json
{
  "blacklisted_ips": ["192.168.1.100", "10.0.0.0/24"],
  "total_count": 2,
  "config_file": "/path/to/config/ip_blacklist.json"
}
```

### 2. Add IP/Range to Blacklist
```bash
POST /api/converter/admin/blacklist/add
Content-Type: application/json
```

**Add Individual IP:**
```bash
curl -X POST -H "Content-Type: application/json" \
  -d '{"ip": "192.168.1.100"}' \
  http://localhost:8000/api/converter/admin/blacklist/add
```

**Add CIDR Range:**
```bash
curl -X POST -H "Content-Type: application/json" \
  -d '{"ip": "10.0.0.0/24"}' \
  http://localhost:8000/api/converter/admin/blacklist/add
```

**Response:**
```json
{
  "message": "Successfully added 192.168.1.100 to blacklist",
  "blacklisted_ips": ["192.168.1.100"],
  "total_count": 1
}
```

### 3. Remove IP/Range from Blacklist
```bash
POST /api/converter/admin/blacklist/remove
Content-Type: application/json
```

**Example:**
```bash
curl -X POST -H "Content-Type: application/json" \
  -d '{"ip": "192.168.1.100"}' \
  http://localhost:8000/api/converter/admin/blacklist/remove
```

**Response:**
```json
{
  "message": "Successfully removed 192.168.1.100 from blacklist",
  "blacklisted_ips": [],
  "total_count": 0
}
```

### 4. Check if IP is Blacklisted
```bash
POST /api/converter/admin/blacklist/check
Content-Type: application/json
```

**Example:**
```bash
curl -X POST -H "Content-Type: application/json" \
  -d '{"ip": "192.168.1.100"}' \
  http://localhost:8000/api/converter/admin/blacklist/check
```

**Response:**
```json
{
  "ip": "192.168.1.100",
  "is_blacklisted": true,
  "matched_rule": "192.168.1.100",
  "total_blacklist_entries": 2
}
```

### 5. Reload Blacklist from File
```bash
POST /api/converter/admin/blacklist/reload
```

**Example:**
```bash
curl -X POST http://localhost:8000/api/converter/admin/blacklist/reload
```

**Response:**
```json
{
  "message": "Blacklist reloaded successfully",
  "old_count": 1,
  "new_count": 2,
  "blacklisted_ips": ["192.168.1.100", "10.0.0.0/24"]
}
```

## How It Works

### 1. Rate Limiting Integration
When a request is made to any rate-limited endpoint, the system:
1. **Extracts client IP** (handling proxies via `X-Forwarded-For` and `X-Real-IP` headers)
2. **Checks blacklist first** before applying rate limits
3. **Returns 403 Forbidden** if IP is blacklisted
4. **Continues with rate limiting** if IP is allowed

### 2. IP Matching Logic
- **Individual IPs**: Exact match (e.g., `192.168.1.100`)
- **CIDR Ranges**: Network membership check (e.g., `10.0.0.50` matches `10.0.0.0/24`)
- **IPv4 Support**: Currently supports IPv4 addresses and ranges
- **Validation**: All IPs and ranges are validated before being added

### 3. Error Responses

**Blacklisted IP attempting access:**
```json
{
  "error": "Access denied",
  "message": "Your IP address has been blocked",
  "ip": "192.168.1.100"
}
```
*HTTP Status: 403 Forbidden*

**Rate limit exceeded (for allowed IPs):**
```json
{
  "error": "Rate limit exceeded",
  "message": "Maximum 5 requests per 60 seconds allowed",
  "retry_after": 60,
  "ip": "8.8.8.8"
}
```
*HTTP Status: 429 Too Many Requests*

## Common Use Cases

### 1. Block Malicious IPs
```bash
# Block a specific attacking IP
curl -X POST -H "Content-Type: application/json" \
  -d '{"ip": "203.0.113.100"}' \
  http://localhost:8000/api/converter/admin/blacklist/add
```

### 2. Block Entire Networks
```bash
# Block an entire subnet (e.g., compromised hosting provider)
curl -X POST -H "Content-Type: application/json" \
  -d '{"ip": "198.51.100.0/24"}' \
  http://localhost:8000/api/converter/admin/blacklist/add
```

### 3. Block Private Networks (if public-facing)
```bash
# Block RFC 1918 private networks
curl -X POST -H "Content-Type: application/json" \
  -d '{"ip": "10.0.0.0/8"}' \
  http://localhost:8000/api/converter/admin/blacklist/add

curl -X POST -H "Content-Type: application/json" \
  -d '{"ip": "172.16.0.0/12"}' \
  http://localhost:8000/api/converter/admin/blacklist/add

curl -X POST -H "Content-Type: application/json" \
  -d '{"ip": "192.168.0.0/16"}' \
  http://localhost:8000/api/converter/admin/blacklist/add
```

### 4. Temporary Blocks
```bash
# Add temporary block
curl -X POST -H "Content-Type: application/json" \
  -d '{"ip": "1.2.3.4"}' \
  http://localhost:8000/api/converter/admin/blacklist/add

# Remove when no longer needed
curl -X POST -H "Content-Type: application/json" \
  -d '{"ip": "1.2.3.4"}' \
  http://localhost:8000/api/converter/admin/blacklist/remove
```

## Security Considerations

1. **Admin Endpoints**: The blacklist management endpoints have higher rate limits but should still be protected
2. **Configuration File**: Ensure the `config/ip_blacklist.json` file has appropriate permissions
3. **Proxy Headers**: The system respects `X-Forwarded-For` and `X-Real-IP` headers for proxy environments
4. **Validation**: All IP addresses and CIDR ranges are validated before being added
5. **Persistence**: Changes are immediately saved to disk and persist across server restarts

## Testing

Use the included test script to verify functionality:

```bash
python test_ip_blacklist.py
```

This script tests:
- Adding/removing individual IPs
- Adding/removing CIDR ranges
- IP checking functionality
- Invalid input handling
- Duplicate prevention
- Configuration persistence

## Rate Limiting Integration

The IP blacklisting is seamlessly integrated with the existing rate limiting system:

- **Upload endpoint**: 5 requests per minute (blocked IPs get 403 before rate limiting)
- **Admin endpoints**: 10-50 requests per minute depending on endpoint
- **Batch processing**: Same rate limits apply
- **Health checks**: Not rate limited

## Troubleshooting

### Issue: IP not being blocked
1. Check if IP is actually in blacklist: `GET /admin/blacklist`
2. Verify IP format is correct
3. Check if using proxy headers correctly
4. Test with the check endpoint: `POST /admin/blacklist/check`

### Issue: Can't add IP to blacklist
1. Verify IP format (use `ipaddress` Python module to validate)
2. Check if IP is already in blacklist
3. Ensure sufficient permissions to write config file

### Issue: Changes not persisting
1. Check file permissions on `config/ip_blacklist.json`
2. Verify disk space availability
3. Check server logs for write errors

## Integration with Monitoring

The blacklist system integrates with the existing conversion logging:
- Blocked requests are not logged in conversion statistics
- Rate limit logs still track blocked IPs for monitoring
- Admin endpoints are rate limited and logged

---

*Last updated: September 17, 2025*
