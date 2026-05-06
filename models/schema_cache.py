# -*- coding: utf-8 -*-

import json
import logging
from datetime import datetime, timedelta
from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ExtDBSchemaCache(models.Model):
    _name = 'extdb.schema.cache'
    _description = 'External Database Schema Cache'
    _order = 'schema_name, table_name'

    schema_name = fields.Char(string='Schema Name', required=True, index=True)
    table_name = fields.Char(string='Table Name', required=True, index=True)
    column_data = fields.Text(string='Column Data (JSON)', required=True)
    column_data_html = fields.Html(string='Columns', compute='_compute_column_data_html')
    cached_at = fields.Datetime(string='Cached At', default=fields.Datetime.now, required=True)

    _sql_constraints = [
        ('unique_schema_table', 'UNIQUE(schema_name, table_name)',
         'Schema and table combination must be unique!')
    ]

    @api.depends('column_data')
    def _compute_column_data_html(self):
        """Convert JSON column data to HTML table"""
        for record in self:
            if not record.column_data:
                record.column_data_html = '<p>No column data</p>'
                continue

            try:
                columns = json.loads(record.column_data)

                html = '''
                <table class="table table-sm table-striped">
                    <thead>
                        <tr>
                            <th>Column Name</th>
                            <th>Data Type</th>
                            <th>Nullable</th>
                            <th>Default</th>
                            <th>Max Length</th>
                            <th>Precision</th>
                            <th>Scale</th>
                        </tr>
                    </thead>
                    <tbody>
                '''

                for col in columns:
                    nullable = 'Yes' if col.get('is_nullable') == 'YES' else 'No'
                    default = col.get('column_default', '-')
                    max_len = col.get('character_maximum_length', '-')
                    precision = col.get('numeric_precision', '-')
                    scale = col.get('numeric_scale', '-')

                    html += f'''
                        <tr>
                            <td><strong>{col.get('column_name', '')}</strong></td>
                            <td><span class="badge badge-info">{col.get('data_type', '')}</span></td>
                            <td>{nullable}</td>
                            <td><code>{default}</code></td>
                            <td>{max_len}</td>
                            <td>{precision}</td>
                            <td>{scale}</td>
                        </tr>
                    '''

                html += '''
                    </tbody>
                </table>
                '''

                record.column_data_html = html

            except Exception as e:
                _logger.error('Failed to parse column data: %s', str(e))
                record.column_data_html = f'<p class="text-danger">Error parsing column data: {str(e)}</p>'

    @api.model
    def get_cached_columns(self, schema_name, table_name, ttl_minutes=10):
        """
        Get cached column data for a table

        :param schema_name: Schema name
        :param table_name: Table name
        :param ttl_minutes: Cache TTL in minutes (default: 10)
        :return: List of column dicts or None if cache expired/not found
        """
        cache = self.search([
            ('schema_name', '=', schema_name),
            ('table_name', '=', table_name)
        ], limit=1)

        if not cache:
            return None

        # Check if cache is still valid
        ttl_delta = timedelta(minutes=ttl_minutes)
        if datetime.now() - cache.cached_at.replace(tzinfo=None) > ttl_delta:
            _logger.info('Cache expired for %s.%s', schema_name, table_name)
            return None

        try:
            return json.loads(cache.column_data)
        except json.JSONDecodeError:
            _logger.error('Failed to decode cached column data for %s.%s', schema_name, table_name)
            return None

    @api.model
    def set_cached_columns(self, schema_name, table_name, columns):
        """
        Cache column data for a table

        :param schema_name: Schema name
        :param table_name: Table name
        :param columns: List of column dicts
        """
        cache = self.search([
            ('schema_name', '=', schema_name),
            ('table_name', '=', table_name)
        ], limit=1)

        column_json = json.dumps(columns, default=str)

        if cache:
            cache.write({
                'column_data': column_json,
                'cached_at': fields.Datetime.now(),
            })
        else:
            self.create({
                'schema_name': schema_name,
                'table_name': table_name,
                'column_data': column_json,
                'cached_at': fields.Datetime.now(),
            })

    @api.model
    def refresh_all_schemas(self):
        """Refresh cache for all tables in all schemas"""
        try:
            from .services import ExtDBClient

            with ExtDBClient(self.env) as client:
                # Get all schemas
                schemas = client.get_schemas()

                total_tables = 0
                for schema in schemas:
                    # Get tables in schema
                    tables = client.list_tables(schema)

                    # Cache columns for each table
                    for table in tables:
                        columns = client.get_columns(table, schema)
                        self.set_cached_columns(schema, table, columns)
                        total_tables += 1

            _logger.info('Refreshed cache for %s tables across %s schemas', total_tables, len(schemas))

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Cache Refreshed'),
                    'message': _('Successfully cached %s tables from %s schemas.') % (total_tables, len(schemas)),
                    'type': 'success',
                    'sticky': False,
                }
            }

        except Exception as e:
            _logger.error('Failed to refresh schema cache: %s', str(e))
            raise UserError(_('Failed to refresh cache: %s') % str(e))

    @api.model
    def clear_cache(self):
        """Clear all cached schema data"""
        count = self.search_count([])
        self.search([]).unlink()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Cache Cleared'),
                'message': _('Cleared %s cached tables.') % count,
                'type': 'info',
                'sticky': False,
            }
        }

    def action_refresh_table(self):
        """Refresh cache for this specific table"""
        self.ensure_one()

        try:
            from .services import ExtDBClient

            with ExtDBClient(self.env) as client:
                columns = client.get_columns(self.table_name, self.schema_name)
                self.set_cached_columns(self.schema_name, self.table_name, columns)

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Table Refreshed'),
                    'message': _('Successfully refreshed cache for %s.%s') % (self.schema_name, self.table_name),
                    'type': 'success',
                    'sticky': False,
                }
            }

        except Exception as e:
            _logger.error('Failed to refresh table cache: %s', str(e))
            raise UserError(_('Failed to refresh: %s') % str(e))
