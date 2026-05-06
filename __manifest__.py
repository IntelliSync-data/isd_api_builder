# -*- coding: utf-8 -*-
{
    'name': 'ISD API Builder',
    'version': '18.0.1.0.0',
    'category': 'ISD Modules',
    'summary': 'AWS PostgreSQL Connection + DB Schema Browser + API Builder',
    'description': """
        External Database API Builder
        ==============================
        - Connect to external PostgreSQL (AWS/EC2) via direct or SSH tunnel
        - Browse database schemas, tables, and columns
        - Build dynamic REST APIs with SQL or ORM mode
        - Test APIs with built-in tester
        - API authentication with API keys
        - Request logging and monitoring
    """,
    'author': 'IntelliSyncdata',
    'website': 'https://intellisyncdata.com',
    'depends': ['base', 'web', 'web_editor'],
    'external_dependencies': {
        'python': ['psycopg2', 'paramiko'],
    },
    'data': [
        # Security
        'security/security.xml',
        'security/ir.model.access.csv',

        # Views (must load actions before menus)
        'views/settings_view.xml',
        'views/schema_views.xml',
        'views/endpoint_views.xml',
        'views/log_views.xml',
        'views/test_api_wizard_views.xml',
        'views/api_generator_wizard_views.xml',
        'views/menuitems.xml',  # Load menus last
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
