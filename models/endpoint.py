# -*- coding: utf-8 -*-

import json
import re
import logging
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class ExtAPIEndpoint(models.Model):
    _name = 'extapi.endpoint'
    _description = 'External API Endpoint'
    _order = 'name'

    name = fields.Char(string='Endpoint Name', required=True, index=True)
    route = fields.Char(
        string='Route',
        required=True,
        index=True,
        help='URL path (e.g., /customers, /orders/:id)'
    )
    method = fields.Selection(
        [('GET', 'GET'),
         ('POST', 'POST'),
         ('PUT', 'PUT'),
         ('PATCH', 'PATCH'),
         ('DELETE', 'DELETE')],
        string='HTTP Method',
        required=True,
        default='GET',
    )
    active = fields.Boolean(string='Active', default=True)
    description = fields.Text(string='Description')

    # Authentication
    auth_mode = fields.Selection(
        [('none', 'No Authentication'),
         ('api_key', 'API Key (X-Api-Key header)')],
        string='Authentication',
        required=True,
        default='api_key',
    )
    api_key = fields.Char(
        string='API Key',
        help='Required if auth_mode is api_key',
    )

    # Execution Mode
    mode = fields.Selection(
        [('sql', 'SQL Query'),
         ('orm', 'Odoo ORM')],
        string='Execution Mode',
        required=True,
        default='sql',
    )

    # SQL Mode Fields
    sql_text = fields.Text(
        string='SQL Query',
        help='Use %(param_name)s for URL parameters, e.g., SELECT * FROM users WHERE id = %(id)s',
    )

    # ORM Mode Fields
    orm_model = fields.Char(
        string='Model Name',
        help='Odoo model technical name (e.g., res.partner)',
    )
    orm_domain_json = fields.Text(
        string='Domain (JSON)',
        default='[]',
        help='Search domain in JSON format, e.g., [["customer_rank", ">", 0]]',
    )
    orm_fields_json = fields.Text(
        string='Fields (JSON)',
        default='[]',
        help='List of field names in JSON format, e.g., ["id", "name", "email"]',
    )

    # Response Configuration
    response_mode = fields.Selection(
        [('data_only', 'Data Only'),
         ('with_metadata', 'With Metadata')],
        string='Response Mode',
        default='with_metadata',
        help='Include metadata like total_count, page, page_size in response',
    )
    paginate = fields.Boolean(
        string='Enable Pagination',
        default=True,
    )
    page_size = fields.Integer(
        string='Page Size',
        default=20,
        help='Number of records per page',
    )

    # Logging
    enable_logging = fields.Boolean(
        string='Enable Request Logging',
        default=True,
    )

    # Statistics
    request_count = fields.Integer(
        string='Total Requests',
        compute='_compute_statistics',
        store=False,
    )
    avg_duration_ms = fields.Float(
        string='Avg Duration (ms)',
        compute='_compute_statistics',
        store=False,
    )

    _sql_constraints = [
        ('unique_route_method', 'UNIQUE(route, method)',
         'Route and method combination must be unique!')
    ]

    @api.constrains('route')
    def _check_route_format(self):
        """Validate route format"""
        for record in self:
            if not record.route:
                continue

            # Route must start with /
            if not record.route.startswith('/'):
                raise ValidationError(_('Route must start with /'))

            # Route pattern validation (alphanumeric, -, _, :, /)
            if not re.match(r'^/[a-zA-Z0-9/_:-]*$', record.route):
                raise ValidationError(
                    _('Route can only contain alphanumeric characters, /, -, _, and : for parameters')
                )

    @api.constrains('auth_mode', 'api_key')
    def _check_api_key(self):
        """Ensure API key is set when auth_mode is api_key"""
        for record in self:
            if record.auth_mode == 'api_key' and not record.api_key:
                raise ValidationError(_('API Key is required when authentication mode is "API Key"'))

    @api.constrains('mode', 'sql_text', 'orm_model')
    def _check_mode_fields(self):
        """Validate mode-specific fields"""
        for record in self:
            if record.mode == 'sql' and not record.sql_text:
                raise ValidationError(_('SQL Query is required when mode is "SQL Query"'))
            elif record.mode == 'orm' and not record.orm_model:
                raise ValidationError(_('Model Name is required when mode is "Odoo ORM"'))

    @api.constrains('orm_domain_json')
    def _check_orm_domain_json(self):
        """Validate ORM domain JSON format"""
        for record in self:
            if record.mode == 'orm' and record.orm_domain_json:
                try:
                    domain = json.loads(record.orm_domain_json)
                    if not isinstance(domain, list):
                        raise ValidationError(_('Domain must be a JSON array'))
                except json.JSONDecodeError as e:
                    raise ValidationError(_('Invalid JSON in Domain field: %s') % str(e))

    @api.constrains('orm_fields_json')
    def _check_orm_fields_json(self):
        """Validate ORM fields JSON format"""
        for record in self:
            if record.mode == 'orm' and record.orm_fields_json:
                try:
                    fields_list = json.loads(record.orm_fields_json)
                    if not isinstance(fields_list, list):
                        raise ValidationError(_('Fields must be a JSON array'))
                    if not all(isinstance(f, str) for f in fields_list):
                        raise ValidationError(_('All field names must be strings'))
                except json.JSONDecodeError as e:
                    raise ValidationError(_('Invalid JSON in Fields field: %s') % str(e))

    @api.constrains('page_size')
    def _check_page_size(self):
        """Validate page size"""
        for record in self:
            if record.paginate and (record.page_size < 1 or record.page_size > 1000):
                raise ValidationError(_('Page size must be between 1 and 1000'))

    def _compute_statistics(self):
        """Compute request statistics from logs"""
        for record in self:
            logs = self.env['extapi.log'].search([('endpoint_id', '=', record.id)])
            record.request_count = len(logs)
            if logs:
                record.avg_duration_ms = sum(logs.mapped('duration_ms')) / len(logs)
            else:
                record.avg_duration_ms = 0.0

    def action_open_logs(self):
        """Open logs for this endpoint"""
        self.ensure_one()
        return {
            'name': _('API Logs'),
            'type': 'ir.actions.act_window',
            'res_model': 'extapi.log',
            'view_mode': 'list,form',
            'domain': [('endpoint_id', '=', self.id)],
            'context': {'default_endpoint_id': self.id},
        }

    def action_test_api(self):
        """Open test wizard for this endpoint"""
        self.ensure_one()
        return {
            'name': _('Test API Endpoint'),
            'type': 'ir.actions.act_window',
            'res_model': 'extapi.test.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_endpoint_id': self.id,
                'default_method': self.method,
            },
        }

    @api.model
    def find_endpoint(self, route, method):
        """
        Find endpoint matching route and method

        :param route: Request route
        :param method: HTTP method
        :return: endpoint record or None
        """
        # First try exact match
        endpoint = self.search([
            ('route', '=', route),
            ('method', '=', method),
            ('active', '=', True)
        ], limit=1)

        if endpoint:
            return endpoint

        # Try pattern matching for routes with parameters (e.g., /users/:id)
        all_endpoints = self.search([
            ('method', '=', method),
            ('active', '=', True)
        ])

        for ep in all_endpoints:
            # Convert route pattern to regex
            # /users/:id -> ^/users/(?P<id>[^/]+)$
            pattern = re.sub(r':(\w+)', r'(?P<\1>[^/]+)', ep.route)
            pattern = '^' + pattern + '$'

            if re.match(pattern, route):
                return ep

        return None

    @api.model
    def extract_route_params(self, route_pattern, route):
        """
        Extract parameters from route based on pattern

        :param route_pattern: Pattern like /users/:id
        :param route: Actual route like /users/123
        :return: Dict of parameters
        """
        pattern = re.sub(r':(\w+)', r'(?P<\1>[^/]+)', route_pattern)
        pattern = '^' + pattern + '$'

        match = re.match(pattern, route)
        if match:
            return match.groupdict()
        return {}
