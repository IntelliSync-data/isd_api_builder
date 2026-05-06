# -*- coding: utf-8 -*-

import json
import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class ExtAPIGeneratorWizard(models.TransientModel):
    _name = 'extapi.generator.wizard'
    _description = 'API Generator Wizard'

    # Basic Info
    name = fields.Char(string='API Name', required=True, help='e.g., Photo App API')
    route_prefix = fields.Char(string='Route Prefix', required=True, help='e.g., api/photoapp (without /ext/ prefix)')

    # Table Selection
    schema_name = fields.Char(string='Schema Name', default='public', required=True)
    table_name = fields.Char(string='Table Name', required=True, help='e.g., photoapps')

    # Auto-detected info
    table_columns = fields.Text(string='Detected Columns')
    column_count = fields.Integer(string='Column Count', compute='_compute_column_count', store=True)

    # Settings
    auth_mode = fields.Selection([
        ('none', 'No Authentication'),
        ('api_key', 'API Key')
    ], string='Authentication', default='api_key', required=True)
    api_key = fields.Char(string='API Key', help='Leave empty to generate random key')

    enable_logging = fields.Boolean(string='Enable Request Logging', default=True)
    enable_pagination = fields.Boolean(string='Enable Pagination', default=True)
    default_page_size = fields.Integer(string='Default Page Size', default=80)

    # Generation options
    generate_search_read = fields.Boolean(string='Search & Read (GET/POST)', default=True, help='GET/POST /api/table - List with filters')
    generate_read = fields.Boolean(string='Read by ID (GET)', default=True, help='GET /api/table/:id')
    generate_create = fields.Boolean(string='Create (POST)', default=True, help='POST /api/table/create')
    generate_update = fields.Boolean(string='Update (PUT)', default=True, help='PUT /api/table/:id')
    generate_delete = fields.Boolean(string='Delete (DELETE)', default=True, help='DELETE /api/table/:id')

    @api.depends('table_columns')
    def _compute_column_count(self):
        """Count columns from JSON"""
        for record in self:
            if record.table_columns:
                try:
                    columns = json.loads(record.table_columns)
                    record.column_count = len(columns)
                except:
                    record.column_count = 0
            else:
                record.column_count = 0

    @api.onchange('schema_name', 'table_name')
    def _onchange_table(self):
        """Auto-detect columns when table changes"""
        if self.schema_name and self.table_name:
            try:
                # Get cached columns
                schema_cache = self.env['extdb.schema.cache']
                cache = schema_cache.search([
                    ('schema_name', '=', self.schema_name),
                    ('table_name', '=', self.table_name)
                ], limit=1)

                if cache:
                    self.table_columns = cache.column_data
                else:
                    # Try to fetch from database
                    from ..models.services import ExtDBClient

                    with ExtDBClient(self.env) as client:
                        columns = client.get_columns(self.table_name, self.schema_name)

                        if columns:
                            # Cache it
                            schema_cache.set_cached_columns(self.schema_name, self.table_name, columns)
                            self.table_columns = json.dumps(columns, indent=2)
                        else:
                            self.table_columns = False
                            return {
                                'warning': {
                                    'title': _('Table Not Found'),
                                    'message': _('Could not find table %s.%s in external database.') % (self.schema_name, self.table_name)
                                }
                            }
            except Exception as e:
                _logger.error('Failed to fetch table columns: %s', str(e))
                self.table_columns = False
                return {
                    'warning': {
                        'title': _('Error'),
                        'message': _('Failed to fetch table info: %s') % str(e)
                    }
                }

    @api.onchange('route_prefix')
    def _onchange_route_prefix(self):
        """Clean route prefix"""
        if self.route_prefix:
            # Remove leading/trailing slashes and /ext/ prefix
            route = self.route_prefix.strip('/')
            if route.startswith('ext/'):
                route = route[4:]
            # Ensure it starts with /
            if not route.startswith('/'):
                route = '/' + route
            self.route_prefix = route

    def action_generate_apis(self):
        """Generate CRUD API endpoints"""
        self.ensure_one()

        # Re-fetch columns if needed (in case onchange didn't persist)
        if not self.table_columns or self.column_count == 0:
            _logger.info('Re-fetching columns for %s.%s', self.schema_name, self.table_name)

            # Get cached columns
            schema_cache = self.env['extdb.schema.cache']
            cache = schema_cache.search([
                ('schema_name', '=', self.schema_name),
                ('table_name', '=', self.table_name)
            ], limit=1)

            if cache:
                self.table_columns = cache.column_data
            else:
                # Try to fetch from database
                from ..models.services import ExtDBClient

                try:
                    with ExtDBClient(self.env) as client:
                        columns = client.get_columns(self.table_name, self.schema_name)

                        if columns:
                            # Cache it
                            schema_cache.set_cached_columns(self.schema_name, self.table_name, columns)
                            self.table_columns = json.dumps(columns, indent=2)
                        else:
                            raise ValidationError(_('Could not find table %s.%s in external database.') % (self.schema_name, self.table_name))
                except Exception as e:
                    _logger.error('Failed to fetch table columns: %s', str(e))
                    raise ValidationError(_('Failed to fetch table info: %s') % str(e))

        if not self.table_columns:
            raise ValidationError(_('Please select a valid table with columns.'))

        # Parse columns
        columns = json.loads(self.table_columns)
        column_names = [col['column_name'] for col in columns]

        # Ensure route_prefix starts with /
        route_prefix = self.route_prefix
        if not route_prefix.startswith('/'):
            route_prefix = '/' + route_prefix

        # Generate API key if not provided
        api_key = self.api_key
        if self.auth_mode == 'api_key' and not api_key:
            import secrets
            api_key = secrets.token_urlsafe(32)

        # Generate endpoints
        endpoint_model = self.env['extapi.endpoint']
        created_endpoints = []

        try:
            # 1. Search & Read (GET/POST)
            if self.generate_search_read:
                endpoint = self._create_search_read_endpoint(route_prefix, column_names, api_key)
                created_endpoints.append(endpoint)

            # 2. Read by ID (GET)
            if self.generate_read:
                endpoint = self._create_read_endpoint(route_prefix, column_names, api_key)
                created_endpoints.append(endpoint)

            # 3. Create (POST)
            if self.generate_create:
                endpoint = self._create_create_endpoint(route_prefix, column_names, api_key)
                created_endpoints.append(endpoint)

            # 4. Update (PUT)
            if self.generate_update:
                endpoint = self._create_update_endpoint(route_prefix, column_names, api_key)
                created_endpoints.append(endpoint)

            # 5. Delete (DELETE)
            if self.generate_delete:
                endpoint = self._create_delete_endpoint(route_prefix, column_names, api_key)
                created_endpoints.append(endpoint)

            # Log success
            _logger.info('Successfully generated %s API endpoints for table %s.%s',
                        len(created_endpoints), self.schema_name, self.table_name)

            # Log generated endpoints
            for endpoint in created_endpoints:
                _logger.info('  - %s /ext%s (%s)', endpoint.method, endpoint.route, endpoint.name)

            # Log API key if generated
            if self.auth_mode == 'api_key' and api_key:
                _logger.warning('Generated API Key: %s (Save this! Use header: X-Api-Key)', api_key)

            # Return action to open generated endpoints
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'extapi.endpoint',
                'view_mode': 'kanban,list,form',
                'domain': [('id', 'in', [e.id for e in created_endpoints])],
                'name': _('Generated Endpoints'),
                'context': {
                    'create': False,
                    'default_active': True,
                },
            }

        except Exception as e:
            _logger.error('Failed to generate APIs: %s', str(e))
            raise UserError(_('Failed to generate APIs: %s') % str(e))

    def _create_search_read_endpoint(self, route_prefix, column_names, api_key):
        """Generate search_read endpoint with full search/filter/sort support"""
        fields_sql = ', '.join([f'"{col}"' for col in column_names])
        # For json_build_object, we need key-value pairs: 'col1', col1, 'col2', col2, ...
        json_fields = ', '.join([f"'{col}', t.\"{col}\"" for col in column_names])

        # Generate dynamic filters for ALL columns
        filter_conditions = []
        for col in column_names:
            filter_conditions.append(f"""        AND CASE WHEN %(filter_{col})s IS NOT NULL
            THEN "{col}"::text = %(filter_{col})s::text
            ELSE true END""")
        filters_sql = '\n'.join(filter_conditions)

        # Generate dynamic ORDER BY for ALL columns (both ASC and DESC)
        order_cases = []
        for col in column_names:
            order_cases.append(f"""        CASE WHEN %(order)s = '{col}' AND %(order_dir)s = 'ASC' THEN "{col}"::text END ASC,
        CASE WHEN %(order)s = '{col}' AND %(order_dir)s = 'DESC' THEN "{col}"::text END DESC,""")
        order_sql = '\n'.join(order_cases)

        # Build filter examples for documentation
        filter_examples = ', '.join([f'filter_{col}' for col in column_names[:3]])  # Show first 3 as examples

        # Advanced SQL with dynamic filtering, sorting, and pagination
        sql = f"""
-- Advanced Search & Read endpoint for {self.table_name}
-- Supports dynamic filtering for ALL columns:
--   ?filter_<column>=value   - Exact match filter (e.g., ?filter_id=98, ?filter_name=John)
--   Available filters: {filter_examples}, ...
--   ?order=field_name        - Order by any column (default: id DESC)
--   ?order_dir=asc|desc      - Order direction (default: DESC)
--   ?group_by=column_name    - Group by column and count records (e.g., ?group_by=status)
--   ?limit=20                - Limit results (default: {self.default_page_size})
--   ?offset=0                - Offset for pagination (default: 0)

WITH base_query AS (
    SELECT {fields_sql}
    FROM {self.schema_name}.{self.table_name}
    WHERE 1=1
{filters_sql}
),
ordered_query AS (
    SELECT *,
           COUNT(*) OVER() as total_count
    FROM base_query
    ORDER BY
{order_sql}
        -- Default order
        id DESC
    LIMIT COALESCE(%(limit)s::int, {self.default_page_size})
    OFFSET COALESCE(%(offset)s::int, 0)
)
SELECT json_build_object(
    'jsonrpc', '2.0',
    'id', null,
    'result', json_build_object(
        'records', COALESCE(array_to_json(array_agg(
            json_build_object({json_fields})
        )), '[]'::json),
        'length', COUNT(*),
        'total_records', COALESCE(MAX(total_count), 0),
        'limit', COALESCE(%(limit)s::int, {self.default_page_size}),
        'offset', COALESCE(%(offset)s::int, 0)
    )
) as result
FROM ordered_query t
"""

        return self.env['extapi.endpoint'].create({
            'name': f'{self.name} - Search & Read',
            'route': route_prefix,
            'method': 'POST',
            'description': f'Search and read records from {self.table_name} with Odoo-style domain filtering',
            'mode': 'sql',
            'sql_text': sql,
            'auth_mode': self.auth_mode,
            'api_key': api_key if self.auth_mode == 'api_key' else False,
            'enable_logging': self.enable_logging,
            'paginate': self.enable_pagination,
            'page_size': self.default_page_size,
            'response_mode': 'data_only',
            'active': True,
        })

    def _create_read_endpoint(self, route_prefix, column_names, api_key):
        """Generate read by ID endpoint"""
        fields_sql = ', '.join([f'"{col}"' for col in column_names])

        sql = f"""
-- Read single record by ID
SELECT json_build_object(
    'jsonrpc', '2.0',
    'id', null,
    'result', row_to_json(t.*)
) as result
FROM {self.schema_name}.{self.table_name} t
WHERE id = %(id)s::int
"""

        return self.env['extapi.endpoint'].create({
            'name': f'{self.name} - Read',
            'route': f'{route_prefix}/:id',
            'method': 'GET',
            'description': f'Read single record by ID from {self.table_name}',
            'mode': 'sql',
            'sql_text': sql,
            'auth_mode': self.auth_mode,
            'api_key': api_key if self.auth_mode == 'api_key' else False,
            'enable_logging': self.enable_logging,
            'response_mode': 'data_only',
            'active': True,
        })

    def _create_create_endpoint(self, route_prefix, column_names, api_key):
        """Generate create endpoint"""
        # Filter out auto-generated columns
        writable_columns = [col for col in column_names if col not in ['id', 'create_date', 'write_date', 'create_uid', 'write_uid']]

        sql = f"""
-- Create new record
-- Pass vals as JSON in request body: {{"vals": {{"name": "...", "field": "..."}}}}
INSERT INTO {self.schema_name}.{self.table_name}
    ({', '.join([f'"{col}"' for col in writable_columns])})
VALUES
    ({', '.join([f"(%(vals)s::jsonb->'{col}')::text" for col in writable_columns])})
RETURNING json_build_object(
    'jsonrpc', '2.0',
    'id', null,
    'result', json_build_object('id', id)
) as result
"""

        return self.env['extapi.endpoint'].create({
            'name': f'{self.name} - Create',
            'route': f'{route_prefix}/create',
            'method': 'POST',
            'description': f'Create new record in {self.table_name}',
            'mode': 'sql',
            'sql_text': sql,
            'auth_mode': self.auth_mode,
            'api_key': api_key if self.auth_mode == 'api_key' else False,
            'enable_logging': self.enable_logging,
            'response_mode': 'data_only',
            'active': True,
        })

    def _create_update_endpoint(self, route_prefix, column_names, api_key):
        """Generate update endpoint"""
        writable_columns = [col for col in column_names if col not in ['id', 'create_date', 'create_uid']]

        # Build dynamic SET clause
        set_clause = ', '.join([f'"{col}" = (%(vals)s::jsonb->\'{col}\')::text' for col in writable_columns])

        sql = f"""
-- Update existing record
-- Pass vals as JSON in request body: {{"vals": {{"name": "...", "field": "..."}}}}
UPDATE {self.schema_name}.{self.table_name}
SET {set_clause}
WHERE id = %(id)s::int
RETURNING json_build_object(
    'jsonrpc', '2.0',
    'id', null,
    'result', json_build_object('success', true, 'id', id)
) as result
"""

        return self.env['extapi.endpoint'].create({
            'name': f'{self.name} - Update',
            'route': f'{route_prefix}/:id',
            'method': 'PUT',
            'description': f'Update record in {self.table_name}',
            'mode': 'sql',
            'sql_text': sql,
            'auth_mode': self.auth_mode,
            'api_key': api_key if self.auth_mode == 'api_key' else False,
            'enable_logging': self.enable_logging,
            'response_mode': 'data_only',
            'active': True,
        })

    def _create_delete_endpoint(self, route_prefix, column_names, api_key):
        """Generate delete endpoint"""
        sql = f"""
-- Delete record by ID
DELETE FROM {self.schema_name}.{self.table_name}
WHERE id = %(id)s::int
RETURNING json_build_object(
    'jsonrpc', '2.0',
    'id', null,
    'result', json_build_object('success', true, 'id', id)
) as result
"""

        return self.env['extapi.endpoint'].create({
            'name': f'{self.name} - Delete',
            'route': f'{route_prefix}/:id',
            'method': 'DELETE',
            'description': f'Delete record from {self.table_name}',
            'mode': 'sql',
            'sql_text': sql,
            'auth_mode': self.auth_mode,
            'api_key': api_key if self.auth_mode == 'api_key' else False,
            'enable_logging': self.enable_logging,
            'response_mode': 'data_only',
            'active': True,
        })
