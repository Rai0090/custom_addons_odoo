# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'JCC Payment Acquirer',
    'category': 'Payment Acquirer',
    'summary': 'Payment Acquirer: JCC Implementation',
    'description': """
    JCC Payment Acquirer


    """,
    'depends': ['payment'],
    'data': [
        'views/payment_views.xml',
        'views/payment_jcc_templates.xml',
        'data/payment_acquirer_data.xml',
    ],

    'installable': True,

    'author': 'Christos Mylordos - Logosnet Services Limited',
}
