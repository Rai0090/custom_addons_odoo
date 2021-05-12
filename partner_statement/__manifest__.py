

{
    'name': 'Partner Statement',
    'version': '12.0.1.0.1',
    'category': 'Accounting & Finance',
    'summary': 'Customer reports',
    'description': """Select customer and print/send statements""",
    'author': "cm",
    'license': 'AGPL-3',
    'depends': [
        'account',
        'mail',
        'contacts'
    ],
    'data': [
        'security/statement_security.xml',
        'views/activity_statement.xml',
        'views/outstanding_statement.xml',
        'views/aging_buckets.xml',
        'views/res_config_settings.xml',
        'wizard/statement_wizard.xml',
    ],
    'installable': True,
    'application': False,
}
