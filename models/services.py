# -*- coding: utf-8 -*-

import io
import logging
import psycopg2
import socket
import select
import threading
from contextlib import contextmanager

_logger = logging.getLogger(__name__)

try:
    import paramiko
except ImportError:
    _logger.warning('paramiko not installed. SSH tunnel features will not work.')
    paramiko = None


class SSHTunnelManager:
    """Context manager for SSH tunnel connections using pure paramiko"""

    def __init__(self, ssh_host, ssh_port, ssh_user, ssh_pem_content, remote_host, remote_port):
        """
        Initialize SSH tunnel manager

        :param ssh_host: SSH server hostname
        :param ssh_port: SSH server port
        :param ssh_user: SSH username
        :param ssh_pem_content: PEM key file content (bytes)
        :param remote_host: Remote database host (from SSH server perspective)
        :param remote_port: Remote database port
        """
        if not paramiko:
            raise ImportError('paramiko library is required for SSH tunnel connections')

        self.ssh_host = ssh_host
        self.ssh_port = ssh_port
        self.ssh_user = ssh_user
        self.ssh_pem_content = ssh_pem_content
        self.remote_host = remote_host
        self.remote_port = remote_port
        self.client = None
        self.transport = None
        self.local_port = None
        self.server_socket = None
        self.forward_thread = None
        self.shutdown_flag = threading.Event()

    def _load_private_key(self):
        """Load private key from PEM content, trying multiple key types"""
        if isinstance(self.ssh_pem_content, str):
            pem_content = self.ssh_pem_content.encode('utf-8')
        else:
            pem_content = self.ssh_pem_content

        pem_file = io.StringIO(pem_content.decode('utf-8'))

        # Try different key types in order of likelihood
        key_types = [
            ('RSA', paramiko.RSAKey),
            ('Ed25519', paramiko.Ed25519Key),
            ('ECDSA', paramiko.ECDSAKey),
        ]

        last_error = None
        for key_name, key_class in key_types:
            try:
                pem_file.seek(0)
                return key_class.from_private_key(pem_file)
            except Exception as e:
                last_error = e
                continue

        raise Exception(f'Failed to load private key. Tried RSA, Ed25519, ECDSA. Last error: {last_error}')

    def _get_available_port(self):
        """Find an available local port"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(('127.0.0.1', 0))
        _, port = sock.getsockname()
        sock.close()
        return port

    def _forward_tunnel(self, local_port):
        """Port forwarding handler running in background thread"""
        try:
            # Create server socket
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(('127.0.0.1', local_port))
            self.server_socket.listen(5)
            self.server_socket.settimeout(1.0)

            _logger.info('Port forwarding listening on 127.0.0.1:%s', local_port)

            while not self.shutdown_flag.is_set():
                try:
                    client_socket, addr = self.server_socket.accept()
                    _logger.debug('Connection from %s', addr)

                    # Open channel to remote server
                    channel = self.transport.open_channel(
                        'direct-tcpip',
                        (self.remote_host, self.remote_port),
                        client_socket.getpeername()
                    )

                    if channel is None:
                        client_socket.close()
                        _logger.error('Could not open channel to %s:%s', self.remote_host, self.remote_port)
                        continue

                    # Start forwarding thread
                    threading.Thread(
                        target=self._forward_data,
                        args=(client_socket, channel),
                        daemon=True
                    ).start()

                except socket.timeout:
                    continue
                except Exception as e:
                    if not self.shutdown_flag.is_set():
                        _logger.error('Error accepting connection: %s', e)

        except Exception as e:
            _logger.error('Port forwarding error: %s', e)
        finally:
            if self.server_socket:
                self.server_socket.close()

    def _forward_data(self, client_socket, channel):
        """Forward data between client socket and SSH channel"""
        try:
            while True:
                r, w, x = select.select([client_socket, channel], [], [], 1.0)

                if client_socket in r:
                    data = client_socket.recv(4096)
                    if len(data) == 0:
                        break
                    channel.send(data)

                if channel in r:
                    data = channel.recv(4096)
                    if len(data) == 0:
                        break
                    client_socket.send(data)

                if channel.closed or client_socket.fileno() == -1:
                    break

        except Exception as e:
            _logger.debug('Forward data error: %s', e)
        finally:
            try:
                channel.close()
                client_socket.close()
            except:
                pass

    def __enter__(self):
        """Open SSH tunnel and return local bind address"""
        try:
            # Load private key
            _logger.info('Loading private key...')
            pkey = self._load_private_key()
            _logger.info('Private key loaded successfully: %s', type(pkey).__name__)

            # Create SSH client
            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            # Connect to SSH server
            _logger.info('Connecting to SSH server %s:%s as user %s',
                        self.ssh_host, self.ssh_port, self.ssh_user)
            self.client.connect(
                hostname=self.ssh_host,
                port=self.ssh_port,
                username=self.ssh_user,
                pkey=pkey,
                timeout=30,  # Increased timeout to 30 seconds
                allow_agent=False,
                look_for_keys=False,
                banner_timeout=30
            )
            _logger.info('SSH connection established successfully')

            self.transport = self.client.get_transport()

            # Get available local port
            self.local_port = self._get_available_port()

            # Start port forwarding in background thread
            self.shutdown_flag.clear()
            self.forward_thread = threading.Thread(
                target=self._forward_tunnel,
                args=(self.local_port,),
                daemon=True
            )
            self.forward_thread.start()

            # Give the thread time to start
            import time
            time.sleep(0.5)

            _logger.info('SSH tunnel opened: %s:%s -> %s:%s (local port: %s)',
                        self.ssh_host, self.ssh_port,
                        self.remote_host, self.remote_port,
                        self.local_port)

            return ('127.0.0.1', self.local_port)

        except paramiko.AuthenticationException as e:
            _logger.error('SSH authentication failed: %s. Check username and PEM key.', str(e))
            self._cleanup()
            raise Exception(f'SSH authentication failed: {str(e)}. Check username and PEM key.')
        except paramiko.SSHException as e:
            _logger.error('SSH error: %s', str(e))
            self._cleanup()
            raise Exception(f'SSH error: {str(e)}')
        except socket.timeout as e:
            _logger.error('Connection timeout: Could not connect to %s:%s within 30 seconds. Check firewall/security groups.',
                         self.ssh_host, self.ssh_port)
            self._cleanup()
            raise Exception(f'Connection timeout: Could not connect to {self.ssh_host}:{self.ssh_port}. Check firewall/security groups.')
        except socket.error as e:
            _logger.error('Network error: %s. Check if host is reachable.', str(e))
            self._cleanup()
            raise Exception(f'Network error: {str(e)}. Check if host {self.ssh_host} is reachable.')
        except Exception as e:
            _logger.error('Failed to open SSH tunnel: %s (type: %s)', str(e), type(e).__name__)
            self._cleanup()
            raise

    def _cleanup(self):
        """Clean up resources"""
        self.shutdown_flag.set()

        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass

        if self.client:
            try:
                self.client.close()
            except:
                pass

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Close SSH tunnel"""
        try:
            self._cleanup()
            _logger.info('SSH tunnel closed')
        except Exception as e:
            _logger.error('Error closing SSH tunnel: %s', str(e))


class ExtDBClient:
    """Client for external PostgreSQL database connections"""

    def __init__(self, env, config_params=None):
        """
        Initialize external database client

        :param env: Odoo environment
        :param config_params: Dict of connection parameters (optional, loads from ir.config_parameter if not provided)
        """
        self.env = env
        self.connection = None
        self.tunnel_manager = None

        # Load configuration
        if config_params:
            self.config = config_params
        else:
            self.config = self._load_config()

    def _load_config(self):
        """Load configuration from ir.config_parameter"""
        params = self.env['ir.config_parameter'].sudo()

        config = {
            'enable': params.get_param('extdb.enable', default=False),
            'mode': params.get_param('extdb.db_conn_mode', default='direct'),
            'db_host': params.get_param('extdb.db_host', default=''),
            'db_port': int(params.get_param('extdb.db_port', default=5432)),
            'db_name': params.get_param('extdb.db_name', default=''),
            'db_user': params.get_param('extdb.db_user', default=''),
            'db_password': params.get_param('extdb.db_password', default=''),
            'db_sslmode': params.get_param('extdb.db_sslmode', default='prefer'),
            'ssh_host': params.get_param('extdb.ssh_host', default=''),
            'ssh_port': int(params.get_param('extdb.ssh_port', default=22)),
            'ssh_user': params.get_param('extdb.ssh_user', default=''),
        }

        # Load SSH PEM attachment
        ssh_pem_id = params.get_param('extdb.ssh_pem_attachment_id', default=False)
        if ssh_pem_id:
            attachment = self.env['ir.attachment'].sudo().browse(int(ssh_pem_id))
            config['ssh_pem_content'] = attachment.raw if attachment.exists() else None
        else:
            config['ssh_pem_content'] = None

        return config

    def __enter__(self):
        """Open database connection"""
        if not self.config.get('enable'):
            raise Exception('External database is not enabled')

        try:
            # Determine connection parameters
            if self.config['mode'] == 'ssh_tunnel':
                # Open SSH tunnel first
                self.tunnel_manager = SSHTunnelManager(
                    ssh_host=self.config['ssh_host'],
                    ssh_port=self.config['ssh_port'],
                    ssh_user=self.config['ssh_user'],
                    ssh_pem_content=self.config['ssh_pem_content'],
                    remote_host=self.config['db_host'],
                    remote_port=self.config['db_port'],
                )
                local_host, local_port = self.tunnel_manager.__enter__()
            else:
                # Direct connection
                local_host = self.config['db_host']
                local_port = self.config['db_port']

            # Connect to PostgreSQL
            self.connection = psycopg2.connect(
                host=local_host,
                port=local_port,
                database=self.config['db_name'],
                user=self.config['db_user'],
                password=self.config['db_password'],
                sslmode=self.config['db_sslmode'],
                connect_timeout=10,
            )

            _logger.info('Connected to external database: %s@%s:%s/%s',
                        self.config['db_user'], local_host, local_port, self.config['db_name'])

            return self

        except Exception as e:
            _logger.error('Failed to connect to external database: %s', str(e))
            if self.tunnel_manager:
                self.tunnel_manager.__exit__(None, None, None)
            raise

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Close database connection and SSH tunnel"""
        if self.connection:
            try:
                self.connection.close()
                _logger.info('Closed external database connection')
            except Exception as e:
                _logger.error('Error closing database connection: %s', str(e))

        if self.tunnel_manager:
            self.tunnel_manager.__exit__(exc_type, exc_val, exc_tb)

    def execute_query(self, query, params=None, fetch=True):
        """
        Execute SQL query with parameters

        :param query: SQL query string (use %s for parameters)
        :param params: Tuple of parameters for query
        :param fetch: Whether to fetch results
        :return: List of dicts (column_name: value) if fetch=True, else None
        """
        if not self.connection:
            raise Exception('No active database connection')

        cursor = self.connection.cursor()
        try:
            # Only pass params if query has placeholders
            if params and ('%(' in query or '%s' in query):
                cursor.execute(query, params)
            else:
                cursor.execute(query)

            if fetch:
                columns = [desc[0] for desc in cursor.description]
                results = []
                for row in cursor.fetchall():
                    results.append(dict(zip(columns, row)))
                return results
            else:
                self.connection.commit()
                return None

        except Exception as e:
            _logger.error('Query execution failed: %s', str(e))
            self.connection.rollback()
            raise
        finally:
            cursor.close()

    def list_tables(self, schema='public'):
        """
        List all tables in a schema

        :param schema: Schema name (default: public)
        :return: List of table names
        """
        query = """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = %s AND table_type = 'BASE TABLE'
            ORDER BY table_name
        """
        results = self.execute_query(query, (schema,))
        return [row['table_name'] for row in results]

    def get_columns(self, table_name, schema='public'):
        """
        Get column information for a table

        :param table_name: Table name
        :param schema: Schema name (default: public)
        :return: List of dicts with column info
        """
        query = """
            SELECT
                column_name,
                data_type,
                is_nullable,
                column_default,
                character_maximum_length,
                numeric_precision,
                numeric_scale
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            ORDER BY ordinal_position
        """
        return self.execute_query(query, (schema, table_name))

    def get_schemas(self):
        """
        List all schemas in the database

        :return: List of schema names
        """
        query = """
            SELECT schema_name
            FROM information_schema.schemata
            WHERE schema_name NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
            ORDER BY schema_name
        """
        results = self.execute_query(query)
        return [row['schema_name'] for row in results]
