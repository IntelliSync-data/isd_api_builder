# ISD API Builder for Odoo 18

## Overview

**ISD API Builder** is a comprehensive Odoo 18 module that enables you to:
- Connect to external PostgreSQL databases (AWS RDS, EC2, or any PostgreSQL instance)
- Browse database schemas, tables, and columns
- Build dynamic REST APIs with SQL or ORM mode
- Test APIs with a built-in tester
- Authenticate APIs with API keys
- Monitor and log all API requests

## Features

### 1. External Database Connection
- **Direct Connection**: Connect directly to PostgreSQL databases
- **SSH Tunnel**: Secure connection through SSH bastion hosts
- **SSL Support**: Multiple SSL modes (disable, prefer, require, verify-ca, verify-full)
- **Test Connection**: Built-in connection testing

### 2. Schema Browser
- Automatic caching of database schemas with 10-minute TTL
- Browse tables and columns from external databases
- Refresh cache for individual tables or all schemas
- View column metadata (data types, nullability, defaults)

### 3. API Endpoint Builder
- **SQL Mode**: Execute custom SQL queries with parameterized inputs
- **ORM Mode**: Use Odoo ORM to query internal models
- **Multiple HTTP Methods**: GET, POST, PUT, PATCH, DELETE
- **Route Parameters**: Support for dynamic routes (e.g., `/users/:id`)
- **Authentication**: API key authentication via `X-Api-Key` header
- **Pagination**: Built-in pagination support with configurable page sizes

### 4. API Testing
- Interactive test wizard
- Test with custom query parameters, body, and headers
- View response body and status codes
- Generate and copy cURL commands
- Measure request duration

### 5. Request Logging
- Automatic logging of all API requests
- Track request metadata (IP, user agent)
- Monitor response times and status codes
- Error message logging
- Searchable and filterable logs

## Installation

### Prerequisites
Install required Python packages:
```bash
pip install psycopg2-binary paramiko
```

### Install Module
1. Copy the `isd_api_builder` directory to your Odoo addons path
2. Update the apps list: `Settings > Apps > Update Apps List`
3. Search for "ISD API Builder"
4. Click Install

## Configuration

### 1. Database Connection Setup

Navigate to: **External API > Configuration > Settings**

#### Direct Connection
1. Enable "Enable External Database"
2. Select "Direct Connection" mode
3. Fill in database credentials:
   - Host: `your-database.rds.amazonaws.com`
   - Port: `5432`
   - Database Name: `your_database`
   - User: `your_username`
   - Password: `your_password`
   - SSL Mode: `prefer` or `require`
4. Click "Test Connection"

#### SSH Tunnel Connection
1. Enable "Enable External Database"
2. Select "SSH Tunnel" mode
3. Fill in database credentials (same as above)
4. Fill in SSH tunnel settings:
   - SSH Host: `bastion.example.com`
   - SSH Port: `22`
   - SSH User: `ubuntu`
   - SSH PEM Key: Upload your `.pem` private key file
5. Click "Test Connection"

### 2. Schema Browser

Navigate to: **External API > External Database > Schema Browser**

- Click "Refresh All Schemas" to cache all tables from the external database
- View cached tables and their column definitions
- Click "Refresh" on individual tables to update cache

## Creating API Endpoints

### Example 1: SQL Mode - Get All Users

Navigate to: **External API > API Builder > Endpoints**

1. Click "Create"
2. Fill in:
   - **Name**: `Get All Users`
   - **Route**: `/users`
   - **Method**: `GET`
   - **Authentication**: `API Key`
   - **API Key**: Generate a secure key (e.g., `your-secret-api-key-123`)
3. Go to **Execution** tab:
   - **Mode**: `SQL Query`
   - **SQL Query**:
     ```sql
     SELECT id, username, email, created_at
     FROM users
     WHERE active = true
     ORDER BY created_at DESC
     ```
4. Go to **Response** tab:
   - **Response Mode**: `With Metadata`
   - **Enable Pagination**: ✓
   - **Page Size**: `20`
5. Save

### Example 2: SQL Mode with Parameters

1. Create new endpoint:
   - **Name**: `Get User by ID`
   - **Route**: `/users/:id`
   - **Method**: `GET`
2. **SQL Query**:
   ```sql
   SELECT id, username, email, phone, created_at
   FROM users
   WHERE id = %(id)s
   ```

### Example 3: SQL Mode with Query Parameters

1. Create new endpoint:
   - **Name**: `Search Users`
   - **Route**: `/users/search`
   - **Method**: `GET`
2. **SQL Query**:
   ```sql
   SELECT id, username, email
   FROM users
   WHERE username ILIKE '%%' || %(query)s || '%%'
      OR email ILIKE '%%' || %(query)s || '%%'
   ORDER BY username
   ```
3. Use: `/ext/users/search?query=john`

### Example 4: ORM Mode - Get Odoo Partners

1. Create new endpoint:
   - **Name**: `Get Customers`
   - **Route**: `/customers`
   - **Method**: `GET`
2. Go to **Execution** tab:
   - **Mode**: `Odoo ORM`
   - **Model Name**: `res.partner`
   - **Domain (JSON)**:
     ```json
     [["customer_rank", ">", 0], ["active", "=", true]]
     ```
   - **Fields (JSON)**:
     ```json
     ["id", "name", "email", "phone", "city", "country_id"]
     ```

### Example 5: POST Endpoint with Body Parameters

1. Create new endpoint:
   - **Name**: `Create User`
   - **Route**: `/users`
   - **Method**: `POST`
2. **SQL Query**:
   ```sql
   INSERT INTO users (username, email, phone)
   VALUES (%(username)s, %(email)s, %(phone)s)
   RETURNING id, username, email, created_at
   ```

## Testing Endpoints

1. Open an endpoint
2. Click "Test API" button
3. In the wizard:
   - Add query parameters: `{"page": 1, "page_size": 10}`
   - Add body (for POST/PUT): `{"username": "john", "email": "john@example.com"}`
   - Add custom headers if needed
4. Click "Run Test"
5. View response body, status code, and duration
6. Click "Copy cURL" to get command line example

## Making API Calls

### Using cURL

```bash
# GET request
curl -X GET \
  -H 'X-Api-Key: your-secret-api-key-123' \
  'https://your-odoo-instance.com/ext/users?page=1&page_size=10'

# GET with route parameter
curl -X GET \
  -H 'X-Api-Key: your-secret-api-key-123' \
  'https://your-odoo-instance.com/ext/users/123'

# POST request
curl -X POST \
  -H 'Content-Type: application/json' \
  -H 'X-Api-Key: your-secret-api-key-123' \
  -d '{"username": "john", "email": "john@example.com"}' \
  'https://your-odoo-instance.com/ext/users'
```

### Using Python requests

```python
import requests

base_url = 'https://your-odoo-instance.com'
headers = {
    'X-Api-Key': 'your-secret-api-key-123',
    'Content-Type': 'application/json'
}

# GET request with pagination
response = requests.get(
    f'{base_url}/ext/users',
    headers=headers,
    params={'page': 1, 'page_size': 20}
)

data = response.json()
print(f"Total users: {data['metadata']['total_count']}")
print(f"Users: {data['data']}")

# POST request
response = requests.post(
    f'{base_url}/ext/users',
    headers=headers,
    json={'username': 'john', 'email': 'john@example.com'}
)
```

### Using JavaScript (fetch)

```javascript
const baseUrl = 'https://your-odoo-instance.com';
const apiKey = 'your-secret-api-key-123';

// GET request
fetch(`${baseUrl}/ext/users?page=1&page_size=20`, {
  headers: {
    'X-Api-Key': apiKey
  }
})
.then(response => response.json())
.then(data => {
  console.log('Total:', data.metadata.total_count);
  console.log('Users:', data.data);
});

// POST request
fetch(`${baseUrl}/ext/users`, {
  method: 'POST',
  headers: {
    'X-Api-Key': apiKey,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    username: 'john',
    email: 'john@example.com'
  })
})
.then(response => response.json())
.then(data => console.log('Created:', data));
```

## Response Format

### With Metadata (default)

```json
{
  "success": true,
  "data": [
    {
      "id": 1,
      "username": "john_doe",
      "email": "john@example.com"
    }
  ],
  "metadata": {
    "total_count": 150,
    "page": 1,
    "page_size": 20,
    "total_pages": 8
  }
}
```

### Data Only

```json
[
  {
    "id": 1,
    "username": "john_doe",
    "email": "john@example.com"
  }
]
```

## Monitoring and Logs

Navigate to: **External API > API Builder > API Logs**

View detailed logs including:
- Request timestamp
- Endpoint and route
- HTTP method and status code
- Request parameters (query and body)
- Response preview
- Request duration in milliseconds
- Error messages

### Filter Options
- Success (2xx responses)
- Client errors (4xx)
- Server errors (5xx)
- By endpoint
- By date range (today, last 7 days, last 30 days)

## Security Best Practices

1. **API Keys**: Use strong, randomly generated API keys
2. **HTTPS**: Always use HTTPS in production
3. **SQL Injection**: The module uses parameterized queries to prevent SQL injection
4. **Access Control**: Only users with "External API Administrator" role can manage endpoints
5. **SSH Keys**: Store PEM files securely as attachments, not in plain text
6. **Database Permissions**: Use database users with minimal required permissions

## Error Handling

The API returns standard HTTP status codes:

- **200**: Success
- **400**: Bad Request (invalid parameters)
- **401**: Unauthorized (missing or invalid API key)
- **404**: Not Found (endpoint doesn't exist)
- **405**: Method Not Allowed (wrong HTTP method)
- **500**: Internal Server Error (query execution failed)
- **503**: Service Unavailable (database connection failed)

## Troubleshooting

### Connection Issues

**Problem**: "Connection failed: could not connect to server"
- Verify database host and port
- Check firewall rules (PostgreSQL port 5432)
- Verify security groups (AWS RDS)
- Test network connectivity: `telnet your-host 5432`

**Problem**: "SSH tunnel connection failed"
- Verify SSH host and port (usually 22)
- Check PEM key file format
- Ensure PEM key has correct permissions
- Verify bastion host security groups

### API Issues

**Problem**: "Endpoint not found" (404)
- Verify endpoint is active
- Check route matches exactly (case-sensitive)
- Ensure HTTP method matches

**Problem**: "Unauthorized" (401)
- Verify `X-Api-Key` header is sent
- Check API key matches endpoint configuration
- Ensure no extra spaces in API key

**Problem**: "SQL execution failed" (500)
- Check SQL syntax
- Verify table and column names exist
- Test query directly in database
- Check parameter names match (%(param_name)s)

## Module Structure

```
isd_api_builder/
├── __init__.py
├── __manifest__.py
├── README.md
├── controllers/
│   ├── __init__.py
│   └── api_router.py          # HTTP request routing and handling
├── data/
│   └── ir_config_params.xml   # Default configuration parameters
├── models/
│   ├── __init__.py
│   ├── endpoint.py            # API endpoint model
│   ├── log.py                 # Request log model
│   ├── schema_cache.py        # Schema cache model
│   ├── services.py            # SSH tunnel and DB client helpers
│   └── settings.py            # Configuration settings
├── security/
│   ├── ir.model.access.csv    # Access rights
│   └── security.xml           # Security groups
├── static/
│   └── description/
│       └── icon.png           # Module icon
├── views/
│   ├── endpoint_views.xml     # Endpoint UI
│   ├── log_views.xml          # Log UI
│   ├── menuitems.xml          # Menu structure
│   ├── schema_views.xml       # Schema browser UI
│   ├── settings_view.xml      # Settings UI
│   └── test_api_wizard_views.xml  # Test wizard UI
└── wizards/
    ├── __init__.py
    └── test_api_wizard.py     # API testing wizard
```

## Support

For issues, questions, or feature requests, please contact:
- **Author**: IntelliSyncdata
- **Website**: https://intellisyncdata.com

## License

LGPL-3

## Changelog

### Version 18.0.1.0.0
- Initial release for Odoo 18
- External PostgreSQL connection (direct and SSH tunnel)
- Database schema browser with caching
- SQL and ORM mode API endpoints
- API key authentication
- Request logging and monitoring
- Built-in API testing wizard
- Pagination support
