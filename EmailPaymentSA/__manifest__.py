# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Custom Email',
    'summary': 'Adds server action to send automatic emails',
    'description': """


    
    """,
    'depends': ['mail', 'account', 'base_automation'],

    'data': [

        'views/emailtemplate.xml',

    ],

    'installable': True,

    'author': 'Christos Mylordos <christos0090@gmail.com>',
}
