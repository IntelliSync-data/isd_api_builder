# -*- coding: utf-8 -*-

import json
import logging
import time
from odoo import http
from odoo.http import request, Response

_logger = logging.getLogger(__name__)


class ExtAPIRouter(http.Controller):
    """Router for external API endpoints"""

    @http.route('/ext/<path:endpoint>', type='http', auth='none', methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE'], csrf=False)
    def handle_request(self, endpoint, **kwargs):
        """
        Handle API requests

        :param endpoint: Request endpoint path
        :param kwargs: Request parameters
        :return: JSON response
        """
        start_time = time.time()
        route = '/' + endpoint
        method = request.httprequest.method
        status_code = 200
        error_message = None
        response_data = None

        try:
            # Find matching endpoint
            Endpoint = request.env['extapi.endpoint'].sudo()
            endpoint_record = Endpoint.find_endpoint(route, method)

            if not endpoint_record:
                status_code = 404
                error_message = 'Endpoint not found'
                return self._json_response(
                    {'error': error_message},
                    status=status_code
                )

            # Check method
            if endpoint_record.method != method:
                status_code = 405
                error_message = 'Method not allowed'
                return self._json_response(
                    {'error': error_message},
                    status=status_code
                )

            # Authenticate
            if endpoint_record.auth_mode == 'api_key':
                api_key = request.httprequest.headers.get('X-Api-Key')
                if not api_key or api_key != endpoint_record.api_key:
                    status_code = 401
                    error_message = 'Unauthorized: Invalid or missing API key'
                    return self._json_response(
                        {'error': error_message},
                        status=status_code
                    )

            # Extract route parameters
            route_params = Endpoint.extract_route_params(endpoint_record.route, route)

            # Get query parameters
            query_params = dict(request.httprequest.args)

            # Get body parameters (for POST/PUT/PATCH)
            body_params = {}
            if method in ['POST', 'PUT', 'PATCH']:
                try:
                    content_type = request.httprequest.headers.get('Content-Type', '')
                    if 'application/json' in content_type:
                        body_params = json.loads(request.httprequest.data.decode('utf-8'))
                    else:
                        body_params = dict(request.httprequest.form)
                except Exception as e:
                    _logger.warning('Failed to parse request body: %s', str(e))

            # Merge all parameters
            all_params = {**route_params, **query_params, **body_params}

            # Execute endpoint
            if endpoint_record.mode == 'sql':
                response_data = self._execute_sql_endpoint(endpoint_record, all_params)
            elif endpoint_record.mode == 'orm':
                response_data = self._execute_orm_endpoint(endpoint_record, all_params)
            else:
                status_code = 500
                error_message = 'Invalid endpoint mode'
                return self._json_response(
                    {'error': error_message},
                    status=status_code
                )

            # Build response
            if endpoint_record.response_mode == 'data_only':
                final_response = response_data
            else:
                # With metadata
                final_response = {
                    'success': True,
                    'data': response_data.get('data', response_data),
                    'metadata': response_data.get('metadata', {})
                }

            return self._json_response(final_response, status=200)

        except Exception as e:
            _logger.error('API request error: %s', str(e), exc_info=True)
            status_code = 500
            error_message = str(e)
            return self._json_response(
                {'error': 'Internal server error: ' + error_message},
                status=status_code
            )

        finally:
            # Log request
            duration_ms = (time.time() - start_time) * 1000

            try:
                if endpoint_record and endpoint_record.enable_logging:
                    request_meta = {
                        'ip': request.httprequest.remote_addr,
                        'user_agent': request.httprequest.headers.get('User-Agent'),
                    }

                    # Pass response_data as dict/object, let log_request format it
                    response_preview = response_data

                    request.env['extapi.log'].sudo().log_request(
                        endpoint_id=endpoint_record.id if endpoint_record else False,
                        route=route,
                        method=method,
                        request_meta=request_meta,
                        query_params=query_params if 'query_params' in locals() else {},
                        body_params=body_params if 'body_params' in locals() else {},
                        status_code=status_code,
                        response_preview=response_preview,
                        error_message=error_message,
                        duration_ms=duration_ms,
                    )
            except Exception as log_error:
                _logger.error('Failed to log API request: %s', str(log_error))

    def _execute_sql_endpoint(self, endpoint, params):
        """
        Execute SQL endpoint

        :param endpoint: Endpoint record
        :param params: Request parameters
        :return: Response data dict
        """
        try:
            from odoo.addons.isd_api_builder.models.services import ExtDBClient

            # Get pagination parameters
            page = int(params.get('page', 1))
            page_size = int(params.get('page_size', endpoint.page_size))

            # Validate page and page_size
            if page < 1:
                page = 1
            if page_size < 1 or page_size > 1000:
                page_size = endpoint.page_size

            # Calculate offset
            offset = (page - 1) * page_size

            # Build SQL query with pagination if enabled
            sql_query = endpoint.sql_text

            # Prepare SQL parameters with defaults for common query params
            sql_params = dict(params)  # Copy original params

            # Auto-detect all parameters in SQL query and set defaults
            import re
            # Find all %(param_name)s patterns in SQL
            param_pattern = re.compile(r'%\((\w+)\)s')
            required_params = set(param_pattern.findall(sql_query))

            # Set default None for all parameters not provided by user
            for param_name in required_params:
                if param_name not in sql_params:
                    sql_params[param_name] = None

            # Override with common defaults
            sql_params.setdefault('order', 'id')
            sql_params.setdefault('order_dir', 'DESC')
            sql_params.setdefault('limit', page_size)
            sql_params.setdefault('offset', offset)

            if endpoint.paginate:
                # Update pagination params
                sql_params['limit'] = page_size
                sql_params['offset'] = offset

            # Execute query
            with ExtDBClient(request.env) as client:
                # Use parameterized query to prevent SQL injection
                results = client.execute_query(sql_query, sql_params, fetch=True)

                # Get total count (if pagination enabled)
                total_count = len(results)
                if endpoint.paginate:
                    # For accurate total count, we'd need to run a COUNT query
                    # For now, we'll just use the result count
                    # In production, you might want to add a separate COUNT query
                    count_query = f'SELECT COUNT(*) as total FROM ({endpoint.sql_text}) as subquery'
                    count_result = client.execute_query(count_query, sql_params, fetch=True)
                    if count_result:
                        total_count = count_result[0].get('total', len(results))

                response = {
                    'data': results,
                    'metadata': {
                        'total_count': total_count,
                        'page': page,
                        'page_size': page_size,
                        'total_pages': (total_count + page_size - 1) // page_size if endpoint.paginate else 1,
                    }
                }

                return response

        except Exception as e:
            _logger.error('SQL execution error: %s', str(e))
            raise Exception(f'SQL execution failed: {str(e)}')

    def _execute_orm_endpoint(self, endpoint, params):
        """
        Execute ORM endpoint

        :param endpoint: Endpoint record
        :param params: Request parameters
        :return: Response data dict
        """
        try:
            # Get model
            model = request.env[endpoint.orm_model].sudo()

            # Parse domain
            domain = json.loads(endpoint.orm_domain_json) if endpoint.orm_domain_json else []

            # Parse fields
            fields_list = json.loads(endpoint.orm_fields_json) if endpoint.orm_fields_json else []

            # Get pagination parameters
            page = int(params.get('page', 1))
            page_size = int(params.get('page_size', endpoint.page_size))

            # Validate page and page_size
            if page < 1:
                page = 1
            if page_size < 1 or page_size > 1000:
                page_size = endpoint.page_size

            # Calculate offset
            offset = (page - 1) * page_size

            # Search records
            if endpoint.paginate:
                records = model.search(domain, limit=page_size, offset=offset)
                total_count = model.search_count(domain)
            else:
                records = model.search(domain)
                total_count = len(records)

            # Read fields
            if fields_list:
                data = records.read(fields_list)
            else:
                # Read all fields
                data = records.read()

            response = {
                'data': data,
                'metadata': {
                    'total_count': total_count,
                    'page': page,
                    'page_size': page_size,
                    'total_pages': (total_count + page_size - 1) // page_size if endpoint.paginate else 1,
                }
            }

            return response

        except KeyError:
            raise Exception(f'Model "{endpoint.orm_model}" not found')
        except Exception as e:
            _logger.error('ORM execution error: %s', str(e))
            raise Exception(f'ORM execution failed: {str(e)}')

    def _json_response(self, data, status=200):
        """
        Create JSON response

        :param data: Response data
        :param status: HTTP status code
        :return: Response object
        """
        return Response(
            json.dumps(data, default=str, indent=2),
            status=status,
            mimetype='application/json'
        )
