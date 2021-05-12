# Copyright 2018 Roel Adriaans <roel@road-support.nl>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    'name': 'Email multiple invoices',
    'version': '12.0.1.0.0',
    'summary': 'Email multiple invoices with proper templating.',
    'author': 'Christos Mylo',
    'description': """Email multiple invoices with proper templating""",
    'depends': [
        'account',
        'mail',
    ],
    'data': [
        'views/account_invoice.xml',
        'wizard/account_invoice_mail.xml',
    ],
    'demo': [],
    'test': [],
    'installable': True,
    'auto_install': False,
}
