# ISD API Builder - Installation Guide

## Prerequisites

### Python Dependencies
```bash
pip install psycopg2-binary paramiko
```

### System Requirements
- Odoo 18 Community Edition
- Python 3.10+
- PostgreSQL database access

## Installation Steps

### 1. Copy Module
```bash
cp -r isd_api_builder /path/to/odoo/addons/
```

### 2. Update Odoo
```bash
# Restart Odoo server
sudo service odoo restart

# Or if using command line
./odoo-bin -c odoo.conf -u all
```

### 3. Install from Odoo UI
1. Login as Administrator
2. Go to **Apps**
3. Click **Update Apps List**
4. Search for "ISD API Builder"
5. Click **Install**

## First-Time Configuration

### 1. Assign Administrator Rights
1. Go to **Settings → Users & Companies → Users**
2. Select user
3. In **Technical Settings** tab
4. Check **External API Administrator**

### 2. Configure Database Connection

#### Option A: Direct Connection
1. Go to **External API → Configuration → Settings**
2. Enable **Enable External Database**
3. Select **Direct Connection**
4. Fill in:
   - Host: `your-db.rds.amazonaws.com`
   - Port: `5432`
   - Database: `your_database`
   - User: `your_username`
   - Password: `your_password`
   - SSL Mode: `require`
5. Click **Test Connection**
6. Save settings

#### Option B: SSH Tunnel (for EC2)
1. Select **SSH Tunnel** mode
2. Fill in database info (same as above)
3. Fill in SSH settings:
   - SSH Host: `ec2-xx-xxx-xxx-xxx.compute.amazonaws.com`
   - SSH Port: `22`
   - SSH User: `ubuntu`
   - Upload PEM Key file
4. Click **Test Connection**
5. Save settings

### 3. Browse Database Schema
1. Go to **External API → External Database → Schema Browser**
2. Click **Refresh All Schemas**
3. Browse tables and columns

### 4. Create Your First API

#### Example: Get All Records
1. Go to **External API → API Builder → Endpoints**
2. Click **Create**
3. Fill in:
   - Name: `Get Users`
   - Route: `users`
   - Method: `GET`
   - Auth Mode: `API Key`
   - API Key: `your-secret-key-123` (generate strong key)
4. Go to **Execution** tab:
   - Mode: `SQL Query`
   - SQL:
     ```sql
     SELECT id, name, email, created_at
     FROM users
     WHERE active = true
     ORDER BY created_at DESC
     LIMIT 100
     ```
5. Go to **Response** tab:
   - Response Mode: `With Metadata`
   - Enable Pagination: ✓
   - Page Size: `20`
6. Click **Save**
7. Click **Test API** to test

### 5. Test Your API
```bash
curl -X GET \
  -H 'X-Api-Key: your-secret-key-123' \
  'http://localhost:8069/ext/users?page=1&page_size=10'
```

## Troubleshooting

### Connection Issues

**Error**: `Connection refused`
- Check if PostgreSQL is running
- Verify firewall rules allow connection on port 5432
- For AWS RDS: Check security group inbound rules

**Error**: `Authentication failed`
- Verify username and password
- Check database user permissions
- Ensure database exists

**Error**: `SSH tunnel failed`
- Verify PEM key format (OpenSSH format)
- Check bastion host accessibility
- Verify SSH user has permissions
- Test SSH manually: `ssh -i key.pem ubuntu@ec2-host`

### API Issues

**Error**: `Endpoint not found (404)`
- Verify endpoint is enabled (Active = True)
- Check route matches exactly
- Ensure correct HTTP method

**Error**: `Unauthorized (401)`
- Verify X-Api-Key header is present
- Check API key matches configuration
- No extra spaces in key value

**Error**: `SQL execution failed (500)`
- Test query directly in database
- Check table/column names exist
- Verify SQL syntax
- Use parameterized queries: `%(param)s`

### Performance Tips

1. **Use Pagination**: Always enable for large datasets
2. **Cache Schemas**: Refresh only when schema changes
3. **Limit Results**: Use LIMIT in SQL queries
4. **Index Columns**: Ensure filtered columns are indexed
5. **Connection Pool**: Module manages connections efficiently

## Security Recommendations

1. **Strong API Keys**: Use 32+ character random keys
2. **HTTPS Only**: Never use HTTP in production
3. **Minimal DB Permissions**: Grant only SELECT for read-only endpoints
4. **Regular Key Rotation**: Change API keys periodically
5. **Monitor Logs**: Check API logs for suspicious activity

## Next Steps

- Read full [README.md](README.md) for detailed usage
- Check [examples](README.md#creating-api-endpoints) for common use cases
- Review [API logs](README.md#monitoring-and-logs) to monitor usage

## Support

Need help? Contact IntelliSyncdata:
- Website: https://intellisyncdata.com
- Documentation: See README.md

## License

LGPL-3
