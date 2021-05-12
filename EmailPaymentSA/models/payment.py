import hashlib
import base64
import binascii
from werkzeug import urls
import json
import re
import uuid
from functools import partial

from odoo import api, fields, models, _

import logging

_logger = logging.getLogger(__name__)


class EmailReceipt(models.Model):
    _name = 'email.send'
    _inherit = ['account.invoice']

    # def _compute_access_url(self):
    #   super(EmailReceipt, self)._compute_access_url()
    #  for invoice in self:
    #     invoice.access_url = '/my/invoices/%s' % (invoice.id)

    @api.multi
    def auto_mail_send(self):
        self.ensure_one()

        template = self.env.ref('EmailPaymentSA.pog_email_template')
        # template2 = self.env.ref('mail.mail_notification_paynow', False)
        # rec.tmpl_obj = self.pool.get('mail.template')
        # self.pool.get('mail.template').send_mail(self._cr, self._uid, rec.template[0], rec.tmpl_obj.id)
        # compose_form = self.env.ref('account.account_invoice_send_wizard_form', False)


        ctx = dict(
            default_model='account.invoice',
            default_res_id=self.id,
            default_use_template=bool(template),
            default_template_id=template and template.id or False,
            default_composition_mode='comment',
            mark_invoice_as_sent=True,
            custom_layout="mail.mail_notification_paynow",
            force_email=False
        )

        #self.env['mail.template'].browse(template.id).send_mail(self.id,notif_layout="mail.mail_notification_paynow")
        # self.env['mail.template'].browse(template2.id).with_context(ctx).send_mail(self.id)

        return {
            'name': _('Send Invoice'),
            'res_model': 'account.invoice.send',
            'target': 'new',
            'context': ctx,
        }