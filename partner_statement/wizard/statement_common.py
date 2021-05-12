# Copyright 2018 Graeme Gellatly
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from dateutil.relativedelta import relativedelta
from odoo import api, fields, models
import logging
import base64
import calendar
from datetime import datetime

_logger = logging.getLogger(__name__)



class StatementCommon(models.AbstractModel):

    _name = 'statement.common.wizard'
    _description = 'Statement Reports Common Wizard'
    _inherit = ['mail.thread','mail.activity.mixin']
    def _get_company(self):
        return (
            self.env['res.company'].browse(
                self.env.context.get('force_company')) or
            self.env.user.company_id
        )

    name = fields.Char()
    company_id = fields.Many2one(
        comodel_name='res.company',
        default=_get_company,
        string='Company',
        required=True,
    )
    date_end = fields.Date(required=True, default=fields.Date.context_today)
    show_aging_buckets = fields.Boolean(default=True)
    number_partner_ids = fields.Integer(
        default=lambda self: len(self._context['active_ids'])
    )
    filter_partners_non_due = fields.Boolean(
        string="Don't show partners with no due entries", default=True)
    filter_negative_balances = fields.Boolean(
        "Exclude Negative Balances", default=True
    )
    target_move = fields.Selection([
        ('posted', 'All Posted Entries'),
        ('all', 'All Entries'),
    ], 'Target Moves', required=True, default='posted')

    aging_type = fields.Selection(
        [("days", "Age by Days"), ("months", "Age by Months")],
        string="Aging Method",
        default="days",
        required=True,)

    account_type = fields.Selection(
        [('receivable', 'Receivable'),
         ('payable', 'Payable')], string='Account type', default='receivable')




    def send_mail_template_out(self):
        template = self.env.ref('partner_statement.outstanding_statement_email_template')
        # if template:
        #     template.write({
        #         'email_to': self.partner_id.email,
        #     })
        context = dict(self._context or {})
        active_ids = context.get('active_ids', []) or []
        for record in self.env['res.partner'].browse(active_ids):

            template.send_mail(record.id, force_send=True)

    @api.multi
    def send_mail_template(self):
        self.ensure_one()
        return self._mail()

    # @api.multi
    # def send_monthly_mail(self):
    #
    #     mail_mail = self.env['mail.mail']
    #     template = self.env.ref('partner_statement.outstanding_statement_email_template')
    #     ids=[]
    #     emails = []
    #     email_to = ''
    #     partner_obj = self.env['res.partner'].search([["name","=","Christos"]])
    #     _logger.info("PARTNER OBJECT : %r", partner_obj)
    #     ir_model_obj = self.env['ir.model.data']
    #     template_browse = ir_model_obj.get_object_reference('partner_statement', 'statements_email_template')[1]
    #     email_template_obj = self.env['mail.template'].browse(template_browse)
    #     today = datetime.today()
    #     monthname = today.month
    #     _logger.info("Monthname: %r", monthname)
    #
    #     monthname -= 1
    #     if monthname == 0:
    #         monthname = 12
    #
    #     month1 = calendar.month_name[monthname]
    #     # ATTACHMENT_NAME_out = "Outstanding_statement_"+month1
    #     # ATTACHMENT_NAME_act = "Activity_statement_"+month1
    #
    #
    #     for partner_ids in partner_obj:
    #         ids.append(partner_ids.id)
    #
    #     for partner in self.env['res.partner'].browse(ids):
    #         emails.append(partner.email)
    #
    #     for record in self.env['res.partner'].browse(ids):
    #         ATTACHMENT_NAME_act = "SOA_" + record.name+"_"+datestart+"_to_"+dateend
    #         ATTACHMENT_NAME_out = "Outstanding_statement_" + record.name+"_"+dateend
    #
    #         values = email_template_obj.generate_email(record.id)  # it is to generate email for specific object record
    #         data = self._prepare_statement()
    #         datestart = self.date_start.strftime("%d-%b-%Y")
    #         dateend = self.date_end.strftime("%d-%b-%Y")
    #
    #         pdf = self.env.ref('partner_statement.action_print_outstanding_statement').sudo().render_qweb_pdf([record.id],data=data)
    #         pdf1 = self.env.ref('partner_statement.action_print_activity_statement').sudo().render_qweb_pdf([record.id],data=data)
    #         b64_pdf = base64.b64encode(pdf[0])
    #         b64_pdf1 = base64.b64encode(pdf1[0])
    #
    #
    #         att1 =  self.env['ir.attachment'].create({
    #             'name': 'Outstanding_statement_'+month1 +'.pdf',
    #             'type': 'binary',
    #             'datas': b64_pdf,   #TESTTESTTEST
    #             'datas_fname': ATTACHMENT_NAME_out + '.pdf',
    #             'store_fname': ATTACHMENT_NAME_out,
    #             'res_model': 'res.partner',
    #             'res_id': record.id,
    #             'res_field': 1,
    #             'mimetype': 'application/pdf'
    #         })
    #         att2 = self.env['ir.attachment'].create({
    #             'name': 'Activity_statement_'+month1 +'.pdf',
    #             'type': 'binary',
    #             'datas': b64_pdf1,  # TESTTESTTEST
    #             'datas_fname': ATTACHMENT_NAME_act + '.pdf',
    #             'store_fname': ATTACHMENT_NAME_act,
    #             'res_model': 'res.partner',
    #             'res_id': record.id,
    #             'res_field': 1,
    #             'mimetype': 'application/pdf'
    #
    #         })
    #         values.update({
    #             'attachment_ids':[att1.id, att2.id],
    #
    #         })
    #         record.message_post(type="notification",subtype="mt_comment",force_send=True,**values)
    #
    #     try:
    #         today = datetime.today()
    #         year = today.year
    #         month = today.month
    #         month+=1
    #         if month ==13:
    #             month=1
    #         test = datetime(year, month, 7,8,30)
    #         format = test.strftime("%m-%d-%Y %H:%M:%S")
    #         cron = self.sudo().env.ref('partner_statement.send_monthly_mails_cron')
    #         cron.sudo().write({'nextcall': format}) #change nextcall to the 7th of next month
    #         _logger.info("nextcall: %r", format)
    #
    #     except Exception as e:
    #         _logger.info("Nextcall assignment failed with format: %r", format)
    #         pass


    @api.onchange('aging_type')
    def onchange_aging_type(self):
        if self.aging_type == 'months':
            self.date_end = (
                fields.Date.context_today(self).replace(day=1) -
                relativedelta(days=1)
            )
        else:
            self.date_end = fields.Date.context_today(self)

    @api.multi
    def button_export_pdf(self):
        # self.ensure_one()
        return self._export()

    @api.multi
    def button_export_pdf1(self):
        # self.ensure_one()
        return self._export2()



    def _prepare_statement(self):
        self.ensure_one()
        return {
            'date_end': self.date_end,
            'company_id': self.company_id.id,
            'partner_ids': self._context['active_ids'],
            'show_aging_buckets': self.show_aging_buckets,
            'filter_non_due_partners': self.filter_partners_non_due,
            'account_type': self.account_type,
            'aging_type': self.aging_type,
            'filter_negative_balances': self.filter_negative_balances,
        }


    def _export(self):
        raise NotImplementedError

    def _mail(self):
        raise NotImplementedError



