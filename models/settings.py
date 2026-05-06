# -*- coding: utf-8 -*-

import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # Enable/Disable External Database
    extdb_enable = fields.Boolean(
        string='Enable External Database',
        config_parameter='extdb.enable',
    )

    # Connection Mode
    db_conn_mode = fields.Selection(
        [('direct', 'Direct Connection'),
         ('ssh_tunnel', 'SSH Tunnel')],
        string='Connection Mode',
        default='direct',
        config_parameter='extdb.db_conn_mode',
    )

    # Database Connection Settings
    db_host = fields.Char(
        string='Database Host',
        config_parameter='extdb.db_host',
    )
    db_port = fields.Integer(
        string='Database Port',
        default=5432,
        config_parameter='extdb.db_port',
    )
    db_name = fields.Char(
        string='Database Name',
        config_parameter='extdb.db_name',
    )
    db_user = fields.Char(
        string='Database User',
        config_parameter='extdb.db_user',
    )
    db_password = fields.Char(
        string='Database Password',
        config_parameter='extdb.db_password',
    )
    db_sslmode = fields.Selection(
        [('disable', 'Disable'),
         ('allow', 'Allow'),
         ('prefer', 'Prefer'),
         ('require', 'Require'),
         ('verify-ca', 'Verify CA'),
         ('verify-full', 'Verify Full')],
        string='SSL Mode',
        default='prefer',
        config_parameter='extdb.db_sslmode',
    )

    # SSH Tunnel Settings
    ssh_host = fields.Char(
        string='SSH Host',
        config_parameter='extdb.ssh_host',
    )
    ssh_port = fields.Integer(
        string='SSH Port',
        default=22,
        config_parameter='extdb.ssh_port',
    )
    ssh_user = fields.Char(
        string='SSH User',
        config_parameter='extdb.ssh_user',
    )
    ssh_pem_attachment_id = fields.Many2one(
        'ir.attachment',
        string='SSH PEM Key File',
        domain=[('res_model', '=', 'res.config.settings')],
        config_parameter='extdb.ssh_pem_attachment_id',
    )

    def action_test_connection(self):
        """Test connection to external database"""
        self.ensure_one()

        if not self.extdb_enable:
            raise UserError(_('External Database is not enabled.'))

        # Validate required fields
        if self.db_conn_mode == 'direct':
            if not all([self.db_host, self.db_port, self.db_name, self.db_user, self.db_password]):
                raise ValidationError(_('Please fill in all database connection fields.'))
        elif self.db_conn_mode == 'ssh_tunnel':
            if not all([self.db_host, self.db_port, self.db_name, self.db_user, self.db_password,
                       self.ssh_host, self.ssh_port, self.ssh_user, self.ssh_pem_attachment_id]):
                raise ValidationError(_('Please fill in all database and SSH tunnel fields.'))

        try:
            # Import services
            from .services import ExtDBClient

            # Get connection parameters
            conn_params = {
                'enable': self.extdb_enable,
                'mode': self.db_conn_mode,
                'db_host': self.db_host,
                'db_port': self.db_port,
                'db_name': self.db_name,
                'db_user': self.db_user,
                'db_password': self.db_password,
                'db_sslmode': self.db_sslmode,
                'ssh_host': self.ssh_host,
                'ssh_port': self.ssh_port,
                'ssh_user': self.ssh_user,
                'ssh_pem_content': self.ssh_pem_attachment_id.raw if self.ssh_pem_attachment_id else None,
            }

            # Test connection
            with ExtDBClient(self.env, conn_params) as client:
                # Try to list tables as a test
                tables = client.list_tables()
                table_count = len(tables)

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Connection Successful'),
                    'message': _('Successfully connected to external database. Found %s tables.') % table_count,
                    'type': 'success',
                    'sticky': False,
                }
            }

        except Exception as e:
            _logger.error('External database connection test failed: %s', str(e))
            raise UserError(_('Connection failed: %s') % str(e))

    def action_refresh_schemas(self):
        """Refresh all database schemas"""
        self.ensure_one()

        if not self.extdb_enable:
            raise UserError(_('External Database is not enabled.'))

        try:
            # Call refresh_all_schemas on schema cache model
            schema_cache = self.env['extdb.schema.cache']
            return schema_cache.refresh_all_schemas()

        except Exception as e:
            _logger.error('Schema refresh failed: %s', str(e))
            raise UserError(_('Schema refresh failed: %s') % str(e))

    @api.model
    def get_values(self):
        """Override to load ssh_pem_attachment_id correctly"""
        res = super(ResConfigSettings, self).get_values()
        params = self.env['ir.config_parameter'].sudo()

        # Load SSH PEM attachment ID
        ssh_pem_id = params.get_param('extdb.ssh_pem_attachment_id', default=False)
        if ssh_pem_id:
            res['ssh_pem_attachment_id'] = int(ssh_pem_id)

        return res

    def set_values(self):
        """Override to save ssh_pem_attachment_id correctly"""
        super(ResConfigSettings, self).set_values()
        params = self.env['ir.config_parameter'].sudo()

        # Save SSH PEM attachment ID
        params.set_param('extdb.ssh_pem_attachment_id',
                        self.ssh_pem_attachment_id.id if self.ssh_pem_attachment_id else False)
