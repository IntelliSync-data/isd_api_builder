# -*- coding: utf-8 -*-

import json
import logging
import requests
from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ExtAPITestWizard(models.TransientModel):
    _name = 'extapi.test.wizard'
    _description = 'API Endpoint Test Wizard'

    endpoint_id = fields.Many2one(
        'extapi.endpoint',
        string='Endpoint',
        required=True,
        ondelete='cascade',
    )
    method = fields.Selection(
        related='endpoint_id.method',
        string='HTTP Method',
        readonly=True,
    )
    route = fields.Char(
        related='endpoint_id.route',
        string='Route',
        readonly=True,
    )

    # Test Parameters
    query_params = fields.Text(
        string='Query Parameters',
        help='JSON format, e.g., {"page": 1, "page_size": 10}',
        default='{}',
    )
    body_json = fields.Text(
        string='Body (JSON)',
        help='For POST/PUT/PATCH requests',
        default='{}',
    )
    headers_json = fields.Text(
        string='Additional Headers (JSON)',
        help='Custom headers in JSON format, e.g., {"X-Custom": "value"}',
        default='{}',
    )

    # Computed Test URL
    test_params = fields.Text(
        string='Test Parameters Preview',
        compute='_compute_test_params',
        store=False,
    )

    # Response
    response_body = fields.Text(string='Response Body', readonly=True)
    status_code = fields.Integer(string='Status Code', readonly=True)
    duration_ms = fields.Float(string='Duration (ms)', readonly=True)
    curl_command = fields.Text(string='cURL Command', compute='_compute_curl_command', store=False)

    @api.depends('endpoint_id', 'query_params', 'body_json')
    def _compute_test_params(self):
        """Compute test parameters preview"""
        for wizard in self:
            try:
                params = []

                # Query params
                if wizard.query_params and wizard.query_params != '{}':
                    query = json.loads(wizard.query_params)
                    params.append(f'Query: {json.dumps(query, indent=2)}')

                # Body params
                if wizard.body_json and wizard.body_json != '{}':
                    body = json.loads(wizard.body_json)
                    params.append(f'Body: {json.dumps(body, indent=2)}')

                wizard.test_params = '\n\n'.join(params) if params else 'No parameters'

            except Exception as e:
                wizard.test_params = f'Error parsing parameters: {str(e)}'

    @api.depends('endpoint_id', 'query_params', 'body_json', 'headers_json')
    def _compute_curl_command(self):
        """Generate cURL command for testing"""
        for wizard in self:
            try:
                base_url = wizard.env['ir.config_parameter'].sudo().get_param('web.base.url')
                url = f"{base_url}/ext{wizard.route}"

                # Add query parameters to URL
                if wizard.query_params and wizard.query_params != '{}':
                    query = json.loads(wizard.query_params)
                    query_string = '&'.join([f'{k}={v}' for k, v in query.items()])
                    url += f'?{query_string}'

                curl_parts = [f'curl -X {wizard.method}']

                # Add headers
                headers = {'Content-Type': 'application/json'}

                # Add API key if required
                if wizard.endpoint_id.auth_mode == 'api_key' and wizard.endpoint_id.api_key:
                    headers['X-Api-Key'] = wizard.endpoint_id.api_key

                # Add custom headers
                if wizard.headers_json and wizard.headers_json != '{}':
                    custom_headers = json.loads(wizard.headers_json)
                    headers.update(custom_headers)

                for key, value in headers.items():
                    curl_parts.append(f"-H '{key}: {value}'")

                # Add body for POST/PUT/PATCH
                if wizard.method in ['POST', 'PUT', 'PATCH']:
                    if wizard.body_json and wizard.body_json != '{}':
                        body = json.loads(wizard.body_json)
                        curl_parts.append(f"-d '{json.dumps(body)}'")

                # Add URL
                curl_parts.append(f"'{url}'")

                wizard.curl_command = ' \\\n  '.join(curl_parts)

            except Exception as e:
                wizard.curl_command = f'Error generating cURL: {str(e)}'

    def action_run_test(self):
        """Execute test request"""
        self.ensure_one()

        try:
            import time
            start_time = time.time()

            # Build URL
            base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
            url = f"{base_url}/ext{self.route}"

            # Prepare headers
            headers = {'Content-Type': 'application/json'}

            # Add API key if required
            if self.endpoint_id.auth_mode == 'api_key' and self.endpoint_id.api_key:
                headers['X-Api-Key'] = self.endpoint_id.api_key

            # Add custom headers
            if self.headers_json and self.headers_json != '{}':
                try:
                    custom_headers = json.loads(self.headers_json)
                    headers.update(custom_headers)
                except json.JSONDecodeError as e:
                    raise UserError(_('Invalid JSON in headers: %s') % str(e))

            # Prepare query parameters
            params = {}
            if self.query_params and self.query_params != '{}':
                try:
                    params = json.loads(self.query_params)
                except json.JSONDecodeError as e:
                    raise UserError(_('Invalid JSON in query parameters: %s') % str(e))

            # Prepare body
            body = None
            if self.method in ['POST', 'PUT', 'PATCH']:
                if self.body_json and self.body_json != '{}':
                    try:
                        body = json.loads(self.body_json)
                    except json.JSONDecodeError as e:
                        raise UserError(_('Invalid JSON in body: %s') % str(e))

            # Make request
            response = requests.request(
                method=self.method,
                url=url,
                headers=headers,
                params=params,
                json=body,
                timeout=30,
            )

            # Calculate duration
            duration_ms = (time.time() - start_time) * 1000

            # Update wizard with response
            self.write({
                'status_code': response.status_code,
                'response_body': json.dumps(response.json(), indent=2) if response.text else '',
                'duration_ms': duration_ms,
            })

            # Show notification
            if response.status_code < 400:
                message = _('Request successful! Status: %s, Duration: %.2f ms') % (response.status_code, duration_ms)
                msg_type = 'success'
            else:
                message = _('Request failed with status %s') % response.status_code
                msg_type = 'warning'

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Test Complete'),
                    'message': message,
                    'type': msg_type,
                    'sticky': False,
                }
            }

        except requests.exceptions.RequestException as e:
            raise UserError(_('Request failed: %s') % str(e))
        except Exception as e:
            _logger.error('Test request failed: %s', str(e), exc_info=True)
            raise UserError(_('Test failed: %s') % str(e))

    def action_copy_curl(self):
        """Copy cURL command to clipboard (shows in notification)"""
        self.ensure_one()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('cURL Command'),
                'message': self.curl_command,
                'type': 'info',
                'sticky': True,
            }
        }
