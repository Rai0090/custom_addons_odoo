
import hashlib
import base64
import binascii
from werkzeug import urls
from odoo import api, fields, models, _
from odoo.addons.payment.models.payment_acquirer import ValidationError
from odoo.addons.payment_jcc_test.helpers import constants
from odoo.addons.payment_jcc_test.controllers.main import jccController
from odoo.tools.float_utils import float_compare
import logging

_logger = logging.getLogger(__name__)

CURRENCY_CODES = {
    'EUR': '978',
    'USD': '840',
    'CHF': '756',
    'GBP': '826',
    'RUB': '643'
}

class PaymentAcquirerjcc(models.Model):
    _inherit = 'payment.acquirer'

    provider = fields.Selection(selection_add=[('jcc', 'JCC')])
    MerchantID = fields.Char(string='MerchantID', required_if_provider='jcc', groups='base.group_user')
    AcquirerID = fields.Char(string='AcquirerID', required_if_provider='jcc', groups='base.group_user')
    Password = fields.Char(string='Password', required_if_provider='jcc', groups='base.group_user')

    def _get_jcc_urls(self, environment):
        """ JCC URLs"""
        if environment == 'prod':
            return {'jcc_form_url': 'https://jccpg.jccsecure.com/EcomPayment/RedirectAuthLink'}
        else:
            if environment == 'test':
                return {'jcc_form_url': 'https://tjccpg.jccsecure.com/EcomPayment/RedirectAuthLink'}

    def _jcc_generate_sign(self, inout, values):
        """ Generate the shasign for incoming or outgoing communications.
        :param self: the self browse record. It should have a shakey in shakey out
        :param string inout: 'in' (odoo contacting jcc) or 'out' (jcc
                             contacting odoo).

        """
        if inout not in ('in', 'out'):
            raise Exception("Type must be 'in' or 'out'")

        if inout == 'in':

            keys = "Password|MerID|AcqID|OrderID|PurchaseAmt|PurchaseCurrency".split('|')
            sign = ''.join('%s|' % (values.get(k) or '') for k in keys).replace('|','')
        else:
            keys = "Password|MerID|AcqID|OrderID|ResponseCode|ReasonCode".split('|')
            sign = ''.join('%s|' % (values.get(k) or '') for k in keys).replace('|','')

        shasignnoencoding = hashlib.sha1(sign.encode("utf-8")).digest()
        shab = base64.b64encode(shasignnoencoding)
        shasign = str(shab)[2:-1]

        return shasign



    @api.multi
    def jcc_form_generate_values(self, values):
        self.ensure_one()
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        jcc_values = dict(values)
        temp_jcc_values = {
            'Version': '1.0.0',
            'MerID': self.MerchantID,
            'AcqID': self.AcquirerID,
            'MerRespURL': urls.url_join(base_url, jccController._return_url),
            #'MerRespURL': 'https://odoodev.cy.net/payment/jcc/return',
            'PurchaseAmt': ('{0:.2f}'.format(values['amount']).replace('.', '').zfill(12)),
            'PurchaseCurrency':CURRENCY_CODES.get(values['currency'].name),
            'PurchaseCurrencyExponent':'2',
            'OrderID': values['reference'],
            'CaptureFlag': 'A',
            'SignatureMethod':'SHA1',
            'Password':self.Password,

                         }

        jcc_values.update(temp_jcc_values)
        jcc_values['Signature'] = self._jcc_generate_sign('in', jcc_values)
        print(jcc_values['amount'])
        return jcc_values

    @api.multi
    def jcc_get_form_action_url(self):
        self.ensure_one()
        return self._get_jcc_urls(self.environment)['jcc_form_url']


class PaymentTransactionjcc(models.Model):
    _inherit = 'payment.transaction'

    @api.model
    def _jcc_form_get_tx_from_data(self, data):
        """ Given a data dict coming from jcc, verify it and find the related
        transaction record. """
        reference = data.get('OrderID')
        MerID = data.get('MerID')
        AcqID = data.get('AcqID')


        transaction = self.search([('reference', '=', reference)])
        if not reference or not MerID or not AcqID:
            error_msg = 'jcc: received data with missing AcqID (%s) or MerID (%s) or reference (%s)' % (AcqID, MerID, reference)
            _logger.info(error_msg)
            raise ValidationError(_('jcc: received data with missing AcqID (%s) or MerID (%s) or reference (%s)') % (AcqID, MerID, reference))

        if not transaction:
            error_msg = (_('jcc: received data for reference %s; no order found') % (reference))
            _logger.info(error_msg)
            raise ValidationError(error_msg)
        elif len(transaction) > 1:
            error_msg = (_('jcc: received data for reference %s; multiple orders found') % (reference))
            _logger.info(error_msg)
            raise ValidationError(error_msg)

        #verify signature

        #if comparesign != ResponseSignature:
           # _logger.info(comparesign)
            #_logger.info(ResponseSignature)
        #else:
         #   print('SHASIGN == RESPONSESIGNATURE TRUE')
        error_msg = (_('jcc: Received data for odoo reference: (%s)') % (reference))
        _logger.info(error_msg)
        return transaction

    @api.multi
    def _jcc_form_validate(self, data):
        ResponseCode = data.get('ResponseCode')
        result = self.write({
            'acquirer_reference': data.get('ReferenceNo'),
            'date': fields.Datetime.now(),
        })
        if ResponseCode == '1':
            self._set_transaction_done()
            error_msg = 'done'
            _logger.info(error_msg)
        elif ResponseCode =='2':
            self._set_transaction_cancel()

            auth_result = data.get('ReasonCode')
            auth_message = ''
            if auth_result in constants.JCC_AUTH_RESULT:
                auth_message = constants.JCC_AUTH_RESULT[auth_result]

            error_msg = 'JCC payment declined, message %s, code %s' % (auth_message, auth_result)
            _logger.info(error_msg)

        elif ResponseCode =='0':
            self._set_transaction_cancel()
            error_msg = 'token/hash deactivation'
            _logger.info(error_msg)

        else:
            self._set_transaction_cancel()
            auth_result = data.get('ReasonCode')
            auth_message = ''
            if auth_result in constants.JCC_AUTH_RESULT:
                auth_message = constants.JCC_AUTH_RESULT[auth_result]

            error_msg = 'JCC payment error, message %s, code %s' % (auth_message, auth_result)
            _logger.info(error_msg)

        return result
