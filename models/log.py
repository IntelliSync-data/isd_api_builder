# -*- coding: utf-8 -*-

import logging
from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class ExtAPILog(models.Model):
    _name = 'extapi.log'
    _description = 'External API Request Log'
    _order = 'create_date desc'
    _rec_name = 'endpoint_id'

    endpoint_id = fields.Many2one(
        'extapi.endpoint',
        string='Endpoint',
        ondelete='set null',
        index=True,
    )
    route = fields.Char(string='Route', index=True)
    method = fields.Selection(
        [('GET', 'GET'),
         ('POST', 'POST'),
         ('PUT', 'PUT'),
         ('PATCH', 'PATCH'),
         ('DELETE', 'DELETE')],
        string='Method',
        index=True,
    )
    request_meta = fields.Text(
        string='Request Metadata',
        help='IP address, user agent, headers, etc.',
    )
    query_params = fields.Text(string='Query Parameters')
    body_params = fields.Text(string='Body Parameters')
    status_code = fields.Integer(string='Status Code', index=True)
    response_preview = fields.Text(
        string='Response Preview',
        help='First 1000 chars of response',
    )
    error_message = fields.Text(string='Error Message')
    duration_ms = fields.Float(string='Duration (ms)', index=True)
    create_date = fields.Datetime(string='Request Time', readonly=True)

    @api.model
    def log_request(self, endpoint_id, route, method, request_meta, query_params,
                   body_params, status_code, response_preview, error_message, duration_ms):
        """
        Create a log entry for an API request

        :param endpoint_id: Endpoint ID (can be False)
        :param route: Request route
        :param method: HTTP method
        :param request_meta: Request metadata (dict or string)
        :param query_params: Query parameters (dict or string)
        :param body_params: Body parameters (dict or string)
        :param status_code: HTTP status code
        :param response_preview: Response preview (first 1000 chars)
        :param error_message: Error message (if any)
        :param duration_ms: Request duration in milliseconds
        :return: Created log record
        """
        # Convert dicts to strings if needed
        if isinstance(request_meta, dict):
            import json
            request_meta = json.dumps(request_meta, indent=2)

        if isinstance(query_params, dict):
            import json
            query_params = json.dumps(query_params, indent=2)

        if isinstance(body_params, dict):
            import json
            body_params = json.dumps(body_params, indent=2)

        # Format and truncate response preview
        if response_preview:
            import json
            try:
                # If it's dict/list, format it
                if isinstance(response_preview, (dict, list)):
                    response_preview = json.dumps(response_preview, indent=2, ensure_ascii=False)
                # If it's string, try to parse and re-format
                elif isinstance(response_preview, str):
                    try:
                        parsed = json.loads(response_preview)
                        response_preview = json.dumps(parsed, indent=2, ensure_ascii=False)
                    except (json.JSONDecodeError, ValueError):
                        # Not JSON string, keep as is
                        pass
            except Exception:
                # Any error, keep original
                pass

            # Truncate if too long
            if isinstance(response_preview, str) and len(response_preview) > 5000:
                response_preview = response_preview[:5000] + '\n\n... (truncated)'

        return self.create({
            'endpoint_id': endpoint_id if endpoint_id else False,
            'route': route,
            'method': method,
            'request_meta': request_meta,
            'query_params': query_params,
            'body_params': body_params,
            'status_code': status_code,
            'response_preview': response_preview,
            'error_message': error_message,
            'duration_ms': duration_ms,
        })

    @api.model
    def cleanup_old_logs(self, days=30):
        """
        Delete logs older than specified days

        :param days: Number of days to keep logs (default: 30)
        :return: Number of deleted logs
        """
        from datetime import datetime, timedelta

        cutoff_date = datetime.now() - timedelta(days=days)
        old_logs = self.search([('create_date', '<', cutoff_date)])
        count = len(old_logs)
        old_logs.unlink()

        _logger.info('Cleaned up %s old API logs (older than %s days)', count, days)
        return count

    def action_view_full_response(self):
        """Action to view full response in a wizard (for future enhancement)"""
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Response Preview'),
                'message': self.response_preview or _('No response data'),
                'type': 'info',
                'sticky': True,
            }
        }
