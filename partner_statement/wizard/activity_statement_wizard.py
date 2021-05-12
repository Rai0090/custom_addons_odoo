# Copyright 2018 Eficent Business and IT Consulting Services S.L.
#   (http://www.eficent.com)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from dateutil.relativedelta import relativedelta
from odoo import api, fields, models
import logging
import base64
from datetime import datetime

_logger = logging.getLogger(__name__)


class ActivityStatementWizard(models.TransientModel):
    """Activity Statement wizard."""

    _inherit = 'statement.common.wizard'
    _name = 'activity.statement.wizard'
    _description = 'Activity Statement Wizard'

    @api.model
    def _get_date_start(self):
        return (
                fields.Date.context_today(self).replace(day=1) -
                relativedelta(days=1)
        ).replace(day=1)

    date_start = fields.Date(required=True, default=_get_date_start)
    include_outstanding = fields.Boolean(default=False, string='Include outstanding report')

    @api.onchange('aging_type')
    def onchange_aging_type(self):
        super().onchange_aging_type()
        if self.aging_type == 'months':
            self.date_start = self.date_end.replace(day=1)
        else:
            self.date_start = self.date_end - relativedelta(days=30)

    def _export(self):
        """Export to PDF."""
        data = self._prepare_statement()
        r1 = self.env.ref('partner_statement''.action_print_activity_statement').report_action(self, data=data)

        return r1

    def _export2(self):
        """Export to PDF."""
        data = self._prepare_statement()
        r2 = self.env.ref('partner_statement''.action_print_outstanding_statement').report_action(self, data=data)

        return r2

    def _prepare_statement(self):
        res = super()._prepare_statement()
        res.update({'date_start': self.date_start})
        return res

    def _mail(self):

        if self.include_outstanding == True:

            datestart = self.date_start.strftime("%d-%b-%Y")
            dateend = self.date_end.strftime("%d-%b-%Y")
            partner_obj = self.env['res.partner'].search([["customer", "=", True]])
            _logger.info("PARTNER OBJECT : %r", partner_obj)
            ir_model_obj = self.env['ir.model.data']
            template_browse = ir_model_obj.get_object_reference('partner_statement', 'statements_email_template')[1]
            email_template_obj = self.env['mail.template'].browse(template_browse)
            # today = datetime.today()
            # monthname = today.month
            # _logger.info("Monthname: %r", monthname)
            #
            # monthname -= 1
            # if monthname == 0:
            #     monthname = 12
            #
            # month1 = calendar.month_name[monthname]
            # ATTACHMENT_NAME_out = "Outstanding_statement_"+month1
            # ATTACHMENT_NAME_act = "Activity_statement_"+month1

            context = dict(self._context or {})

            active_ids = context.get('active_ids', []) or []
            for record in self.env['res.partner'].browse(active_ids):
                if record.search([("message_partner_ids","not ilike",record.id)]):
                    partner_ids = []
                    partner_ids.append(record.id)
                    record.message_subscribe(partner_ids=partner_ids)
                    _logger.info("message partner ids with added: %r", record.message_partner_ids)


                ATTACHMENT_NAME_act = "SOA_" + record.name + "_" + datestart + "_to_" + dateend
                ATTACHMENT_NAME_out = "Outstanding_statement_" + record.name + "_" + dateend

                values = email_template_obj.generate_email(
                    record.id)  # it is to generate email for specific object record
                data = self._prepare_statement()
                data.update({'partner_ids': [record.id]})
                _logger.info("dataupdate: %r", data)
                datestart = self.date_start.strftime("%d-%b-%Y")
                dateend = self.date_end.strftime("%d-%b-%Y")

                pdf = self.env.ref('partner_statement.action_print_outstanding_statement').sudo().render_qweb_pdf(
                    [record.id], data=data)
                pdf1 = self.env.ref('partner_statement.action_print_activity_statement').sudo().render_qweb_pdf(
                    [record.id], data=data)
                b64_pdf = base64.b64encode(pdf[0])
                b64_pdf1 = base64.b64encode(pdf1[0])

                att1 = self.env['ir.attachment'].create({
                    'name': 'Outstanding_statement_' + record.name + '_' + dateend + '.pdf',
                    'type': 'binary',
                    'datas': b64_pdf,  # TESTTESTTEST
                    'datas_fname': ATTACHMENT_NAME_out + '.pdf',
                    'store_fname': ATTACHMENT_NAME_out,
                    'res_model': 'res.partner',
                    'res_id': record.id,
                    'res_field': 1,
                    'mimetype': 'application/pdf'
                })
                att2 = self.env['ir.attachment'].create({
                    'name': 'SOA_' + record.name + '_' + datestart + '_to_' + dateend + '.pdf',
                    'type': 'binary',
                    'datas': b64_pdf1,  # TESTTESTTEST
                    'datas_fname': ATTACHMENT_NAME_act + '.pdf',
                    'store_fname': ATTACHMENT_NAME_act,
                    'res_model': 'res.partner',
                    'res_id': record.id,
                    'res_field': 1,
                    'mimetype': 'application/pdf'

                })
                values.update({
                    'attachment_ids': [att1.id, att2.id],

                })
                record.message_post(type="email", subtype="mt_comment", force_send=True, notif_layout=False, **values)

        else:
            datestart = self.date_start.strftime("%d-%b-%Y")
            dateend = self.date_end.strftime("%d-%b-%Y")
            template = self.env.ref('partner_statement.activity_statement_email_template')
            ir_model_obj = self.env['ir.model.data']
            template_browse = \
            ir_model_obj.get_object_reference('partner_statement', 'activity_statement_email_template')[1]
            email_template_obj = self.env['mail.template'].browse(template_browse)

            context = dict(self._context or {})
            active_ids = context.get('active_ids', []) or []

            for record in self.env['res.partner'].browse(active_ids):
                if record.search([("message_partner_ids","not ilike",record.id)]):
                    partner_ids = []
                    partner_ids.append(record.id)
                    record.message_subscribe(partner_ids=partner_ids)
                    _logger.info("message partner ids with added: %r", record.message_partner_ids)

                data = self._prepare_statement()
                _logger.info("data: %r", data)
                data.update({'partner_ids': [record.id]})
                _logger.info("dataupdate: %r", data)
                emails = []
                pdf = self.env.ref('partner_statement.action_print_activity_statement').sudo().render_qweb_pdf(
                    [record.id], data=data)
                b64_pdf = base64.b64encode(pdf[0])

                ATTACHMENT_NAME_out = "SOA_" + record.name + "_" + datestart + "_to_" + dateend

                att1 = self.env['ir.attachment'].create({
                    'name': 'SOA_' + record.name + '_' + datestart + '_to_' + dateend + '.pdf',
                    'type': 'binary',
                    'datas': b64_pdf,  # TESTTESTTEST
                    'datas_fname': ATTACHMENT_NAME_out + '.pdf',
                    'store_fname': ATTACHMENT_NAME_out,
                    'res_model': 'res.partner',
                    'res_id': record.id,
                    'res_field': 1,
                    'mimetype': 'application/pdf'
                })

                for partner in record.message_partner_ids:
                    emails.append(partner.email)

                values = email_template_obj.generate_email(
                    record.id)  # it is to generate email for specific object record
                values.update({
                    'attachment_ids': [att1.id],
                    'email_cc': [emails],

                })
                _logger.info("values: %r", values)
                record.message_post(type="email", subtype="mt_comment", force_send=True, notif_layout=False, **values)
