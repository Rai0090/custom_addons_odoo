# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import pprint
import werkzeug
from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class jccController(http.Controller):
    _return_url = '/payment/jcc/return/'

    @http.route(['/payment/jcc/return', '/payment/jcc/cancel/', '/payment/jcc/error/'], type='http', auth='public', csrf=False)
    def jcc_return(self, **post):

        _logger.info(
            'jcc: entering form_feedback with post data %s', pprint.pformat(post))
        if post:

            request.env['payment.transaction'].sudo().form_feedback(post, 'jcc')
        return werkzeug.utils.redirect('/payment/process')


