# -*- coding: utf-8 -*-
{
    'name': "Post Billing PBX",
    'summary': "Adds post billing functionallity to sale_subscriptions. Adds scheduled action to import PBX transacitons.",
    'description': """
    """,
    'author': "cm",
    'version': '1.0.0',
    'depends': ['sale_subscription','sale'],
    'data': [
        'views/postbill_view.xml',
    ],
    'installable': True,
    'auto_install': False,
}
