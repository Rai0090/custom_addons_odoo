
# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import pprint
import werkzeug
from suds.transport import https

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class Example(http.Controller):
    @http.route('/academy/academy/', auth='public', website=True)
    def index(self, **kw):
        return "Hello, world"


    #@http.route('/example', type='http', auth='public', website=True)
    #def render_example_page(self):
    #return http.request.render('payment_jcc_test.example_page', {})
