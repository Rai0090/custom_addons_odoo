import logging
import datetime
import traceback
import math
import calendar
import requests
import time
import pytz

import pandas as pd
from dateutil.relativedelta import relativedelta
from uuid import uuid4

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.osv import expression
from odoo.tools import format_date
from odoo.tools.safe_eval import safe_eval

from odoo.addons import decimal_precision as dp

_logger = logging.getLogger(__name__)

#update product_id to yiannis
#update sale_order_template_id (quotation template)

class PostBillingTemplate(models.Model):
    _inherit = 'sale.subscription.template'
    post_billed = fields.Boolean(string='Post Billing', default=False, copy=False)
    is_telephony = fields.Boolean(string='Hosted Telephony', default=False, copy=False)


class PostBillingAccountInvoice(models.Model):
    _inherit = 'account.invoice'
    telephony_id = fields.Char(string='UID', help='UID from PBX platform, to be imported through API or '
                                                  'manually inserted by user.')


class PostBillingSaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    # fix invoicing period in invoice lines if uid is set but set to if template is set instead
    def _prepare_invoice_line(self, qty):
        """
        Override to add subscription-specific behaviours.

        Display the invoicing period in the invoice line description, link the invoice line to the
        correct subscription and to the subscription's analytic account if present.
        """
        res = super(PostBillingSaleOrderLine, self)._prepare_invoice_line(qty)
        dt = datetime.datetime.today()
        if self.subscription_id:
            res.update(subscription_id=self.subscription_id.id)
            if self.order_id.subscription_management != 'upsell':
                next_date = fields.Date.from_string(self.subscription_id.recurring_next_date)
                periods = {'daily': 'days', 'weekly': 'weeks', 'monthly': 'months', 'yearly': 'years'}
                previous_date = next_date - relativedelta(
                    **{periods[self.subscription_id.recurring_rule_type]: self.subscription_id.recurring_interval})
                lang = self.order_id.partner_invoice_id.lang
                format_date = self.env['ir.qweb.field.date'].with_context(lang=lang).value_to_html

                # Ugly workaround to display the description in the correct language
                if lang:
                    self = self.with_context(lang=lang)
                if self.subscription_id.telephony_id or self.order_id.telephony_id:
                    period_msg = _("Invoicing period: %s - %s") % (
                        format_date(fields.Date.to_string(previous_date.replace(day=dt.day)), {}),
                        format_date(fields.Date.to_string(previous_date.replace(
                            day=calendar.monthrange(previous_date.year, previous_date.month)[1])), {}))
                    res.update(name=self.name + '\n' + period_msg)
                else:
                    period_msg = _("Invoicing period: %s - %s") % (format_date(fields.Date.to_string(previous_date), {}),
                                                                   format_date(fields.Date.to_string(
                                                                       next_date - relativedelta(days=1)), {}))
                    res.update(name=res['name'] + '\n' + period_msg)

            if self.subscription_id.analytic_account_id:
                res['account_analytic_id'] = self.subscription_id.analytic_account_id.id
        return res

    # def _prepare_invoice_line(self, qty):
    #     """
    #     Override to add subscription-specific behaviours.
    #
    #     Display the invoicing period in the invoice line description, link the invoice line to the
    #     correct subscription and to the subscription's analytic account if present.
    #     """
    #     res = super(PostBillingSaleOrderLine, self)._prepare_invoice_line(qty)
    #     if self.subscription_id.telephony_id:
    #         dt = datetime.datetime.today()
    #         if self.subscription_id:
    #             res.update(subscription_id=self.subscription_id.id)
    #             if self.order_id.subscription_management != 'upsell':
    #                 next_date = fields.Date.from_string(self.subscription_id.recurring_next_date)
    #                 periods = {'daily': 'days', 'weekly': 'weeks', 'monthly': 'months', 'yearly': 'years'}
    #                 previous_date = next_date - relativedelta(
    #                     **{periods[self.subscription_id.recurring_rule_type]: self.subscription_id.recurring_interval})
    #                 lang = self.order_id.partner_invoice_id.lang
    #                 format_date = self.env['ir.qweb.field.date'].with_context(lang=lang).value_to_html
    #
    #                 # Ugly workaround to display the description in the correct language
    #                 if lang:
    #                     self = self.with_context(lang=lang)
    #                 period_msg = _("Invoicing period: %s - %s") % (
    #                     format_date(fields.Date.to_string(previous_date.replace(day=dt.day)), {}),
    #                     format_date(fields.Date.to_string(previous_date), {}))
    #                 res.update(name=res['name'] + '\n' + period_msg)
    #             if self.subscription_id.analytic_account_id:
    #                 res['account_analytic_id'] = self.subscription_id.analytic_account_id.id
    #         return res


class PostBillingSaleOrder(models.Model):
    _inherit = 'sale.order'
    telephony_id = fields.Char(string='UID', help='UID from PBX platform, to be imported through API or '
                                                  'manually inserted by user.')

    @api.multi
    def _prepare_invoice(self):
        """
        Prepare the dict of values to create the new invoice for a sales order. This method may be
        overridden to implement custom invoice generation (making sure to call super() to establish
        a clean extension chain).
        """
        self.ensure_one()
        journal_id = self.env['account.invoice'].default_get(['journal_id'])['journal_id']
        if not journal_id:
            raise UserError(_('Please define an accounting sales journal for this company.'))
        invoice_vals = {
            'name': self.client_order_ref or '',
            'origin': self.name,
            'type': 'out_invoice',
            'account_id': self.partner_invoice_id.property_account_receivable_id.id,
            'partner_id': self.partner_invoice_id.id,
            'partner_shipping_id': self.partner_shipping_id.id,
            'journal_id': journal_id,
            'currency_id': self.pricelist_id.currency_id.id,
            'comment': self.note,
            'payment_term_id': self.payment_term_id.id,
            'fiscal_position_id': self.fiscal_position_id.id or self.partner_invoice_id.property_account_position_id.id,
            'company_id': self.company_id.id,
            'user_id': self.user_id and self.user_id.id,
            'team_id': self.team_id.id,
            'transaction_ids': [(6, 0, self.transaction_ids.ids)],
        }
        orderLineID = self.env['sale.order.line'].search(["&",["order_id","=",self.id],"|",["product_id","=",943],["product_id","=",932]]) # if uid exists on subscription instead of sale, copy to invoice
        if orderLineID.subscription_id.telephony_id:
            invoice_vals.update({
                'telephony_id': orderLineID.subscription_id.telephony_id
            })
        if self.telephony_id:
            invoice_vals.update({
                'telephony_id': self.telephony_id
            })
        if orderLineID.subscription_id.post_billed:
            if not self.telephony_id and not orderLineID.subscription_id.telephony_id:
                raise UserError(_("Please fill UID field on either sale order or subscription"))

        return invoice_vals

    def _prepare_subscription_data(self, template):
        """Prepare a dictionnary of values to create a subscription from a template."""
        #if sale order has lines with either telephony product then pass recurring date to subscription created as last day of month
        self.ensure_one()
        values = {
            'name': template.name,
            'template_id': template.id,
            'partner_id': self.partner_invoice_id.id,
            'user_id': self.user_id.id,
            'team_id': self.team_id.id,
            'date_start': fields.Date.today(),
            'description': self.note or template.description,
            'pricelist_id': self.pricelist_id.id,
            'company_id': self.company_id.id,
            'analytic_account_id': self.analytic_account_id.id,
            'payment_token_id': self.transaction_ids.get_last_transaction().payment_token_id.id if template.payment_mode not in [
                'validate_send_payment', 'success_payment'] else False,
            'telephony_id': self.telephony_id,
        }
        default_stage = self.env['sale.subscription.stage'].search([('in_progress', '=', True)], limit=1)
        if default_stage:
            values['stage_id'] = default_stage.id
        # compute the next date
        today = datetime.date.today()
        periods = {'daily': 'days', 'weekly': 'weeks', 'monthly': 'months', 'yearly': 'years'}
        invoicing_period = relativedelta(**{periods[template.recurring_rule_type]: template.recurring_interval})
        recurring_next_date = today + invoicing_period
        values['recurring_next_date'] = fields.Date.to_string(recurring_next_date)
        # if self.sale_order_template_id:
        _logger.error('self id of sale.order %s', self.id)
        if self.env['sale.order.line'].search(["&",["order_id","=",self.id],"|","|",["product_id","=",943],["product_id","=",932],["product_id","=",645]]):
            recurring_next_date = today + invoicing_period
            recurring_next_date_endofmonth = recurring_next_date.replace(
                day=calendar.monthrange(recurring_next_date.year, recurring_next_date.month)[1])
            values.update({
                'telephony_id': self.telephony_id,
                'recurring_next_date': fields.Date.to_string(recurring_next_date_endofmonth),
            })

        return values


class PostBilling(models.Model):
    _inherit = 'sale.subscription'
    post_billed = fields.Boolean(related="template_id.post_billed", string="Post billed", readonly=True)
    is_telephony = fields.Boolean(related="template_id.is_telephony", string="Hosted telephony", readonly=True)
    telephony_id = fields.Char(string='UID', help='UID from PBX platform, to be imported through API or '
                                                  'manually inserted by user.')
    _sql_constraints = [
        ('unique_telephony_id', 'unique (telephony_id)', 'A subscription already exists for this UID. UID must be unique!')
    ]

    def _prepare_invoice_data(self):
        #fix invoicing period dates for yearly/monthly subs and fail to generate inv if sub is postbilled and recurring date not end of month
        self.ensure_one()
        if not self.partner_id:
            raise UserError(_("You must first select a Customer for Subscription %s!") % self.name)

        if 'force_company' in self.env.context:
            company = self.env['res.company'].browse(self.env.context['force_company'])
        else:
            company = self.company_id
            self = self.with_context(force_company=company.id, company_id=company.id)

        fpos_id = self.env['account.fiscal.position'].get_fiscal_position(self.partner_id.id)
        journal = self.template_id.journal_id or self.env['account.journal'].search(
            [('type', '=', 'sale'), ('company_id', '=', company.id)], limit=1)
        if not journal:
            raise UserError(_('Please define a sale journal for the company "%s".') % (company.name or '',))

        next_date = fields.Date.from_string(self.recurring_next_date)
        months_interval = self.recurring_interval

        next_date_start = next_date.replace(day=1)
        next_date_start_month = next_date_start - (relativedelta(months=months_interval - 1))  # startdate if months

        if not next_date:
            raise UserError(_('Please define Date of Next Invoice of "%s".') % (self.display_name,))
        periods = {'daily': 'days', 'weekly': 'weeks', 'monthly': 'months', 'yearly': 'years'}
        end_date = next_date + relativedelta(**{periods[self.recurring_rule_type]: self.recurring_interval})

        end_date = end_date - relativedelta(days=1)  # remove 1 day as normal people thinks in term of inclusive ranges.
        end_date_month = end_date.replace(day=calendar.monthrange(end_date.year, end_date.month)[1])
        next_date_month = next_date.replace(day=calendar.monthrange(next_date.year, next_date.month)[1])
        # next_date_start_years = next_date_month - relativedelta(**{periods[self.recurring_rule_type]: self.recurring_interval})  # startdate if years
        next_date_start_years = next_date_month - relativedelta(years=self.recurring_interval,
                                                                days=-1)  # startdate if years
        _logger.error('startdate if years %s', next_date_start_years)
        sub_f_ids = self.env['sale.subscription'].search([["message_channel_ids", "=", "sales"]])
        for record in sub_f_ids:
            _logger.error('unsubscribe %s', record.message_channel_ids.ids)

            record.message_unsubscribe(channel_ids=record.message_channel_ids.ids)
        addr = self.partner_id.address_get(['delivery', 'invoice'])
        sale_order = self.env['sale.order'].search([('order_line.subscription_id', 'in', self.ids)], order="id desc",
                                                   limit=1)
        last_day_of_month = calendar.monthrange(self.recurring_next_date.year, self.recurring_next_date.month)[1]
        if self.post_billed == True:
            try:
                _logger.error("Writing nextcall")
                cron = self.sudo().env.ref('sale_sub_postbill._telecom_cron')
                cron.sudo().write({'nextcall': (
                    (datetime.datetime.now() + (relativedelta(months=1))).replace(day=1, hour=2, minute=0, second=0,
                                                                                  microsecond=0)).strftime('%m/%d/%Y %H:%M:%S')})
            except Exception as e:
                _logger.error("Failed to write nextcall: %s", e)
                pass
            if self.recurring_next_date != datetime.date(self.recurring_next_date.year, self.recurring_next_date.month,
                                                         last_day_of_month):
                raise UserError(_('Subscriptions app failed to generate a post-billed invoice: %s'
                                  ' Can only generate post-billed invoices if Date of next invoice is set on the last day of a month: "%s".') % (
                                    self.name, self.recurring_next_date,))
            else:
                recurringnextdate = next_date_month.replace(day=1)
                self.write({'recurring_next_date': recurringnextdate.replace(
                    day=calendar.monthrange(recurringnextdate.year, recurringnextdate.month)[1])})
                _logger.error('recurringnextdate: %s', recurringnextdate)  # startdate
                _logger.error('recurring_next_date: %s', self.recurring_next_date)  # enddate
                if self.recurring_rule_type == 'yearly':
                    return {
                        'account_id': self.partner_id.property_account_receivable_id.id,
                        'type': 'out_invoice',
                        'partner_id': addr['invoice'],
                        'partner_shipping_id': addr['delivery'],
                        'currency_id': self.pricelist_id.currency_id.id,
                        'journal_id': journal.id,
                        'origin': self.code,
                        'fiscal_position_id': fpos_id,
                        'payment_term_id': sale_order.payment_term_id.id if sale_order else self.partner_id.property_payment_term_id.id,
                        'company_id': company.id,
                        'comment': _("This invoice covers the following period: %s - %s") % (
                            format_date(self.env, next_date_start_years), format_date(self.env, next_date_month)),
                        'user_id': self.user_id.id,
                        'date_invoice': next_date_month,  # set invoice date to last date of month
                        'recurring_next_date': self.recurring_next_date,
                        'telephony_id': self.telephony_id
                    }
                else:
                    return {
                        'account_id': self.partner_id.property_account_receivable_id.id,
                        'type': 'out_invoice',
                        'partner_id': addr['invoice'],
                        'partner_shipping_id': addr['delivery'],
                        'currency_id': self.pricelist_id.currency_id.id,
                        'journal_id': journal.id,
                        'origin': self.code,
                        'fiscal_position_id': fpos_id,
                        'payment_term_id': sale_order.payment_term_id.id if sale_order else self.partner_id.property_payment_term_id.id,
                        'company_id': company.id,
                        'comment': _("This invoice covers the following period: %s - %s") % (
                            format_date(self.env, next_date_start_month), format_date(self.env, next_date_month)),
                        'user_id': self.user_id.id,
                        'date_invoice': next_date_month,  # set invoice date to last date of month
                        'recurring_next_date': self.recurring_next_date,
                        'telephony_id': self.telephony_id
                    }
        else:
            return {
                'account_id': self.partner_id.property_account_receivable_id.id,
                'type': 'out_invoice',
                'partner_id': addr['invoice'],
                'partner_shipping_id': addr['delivery'],
                'currency_id': self.pricelist_id.currency_id.id,
                'journal_id': journal.id,
                'origin': self.code,
                'fiscal_position_id': fpos_id,
                'payment_term_id': sale_order.payment_term_id.id if sale_order else self.partner_id.property_payment_term_id.id,
                'company_id': company.id,
                'comment': _("This invoice covers the following period: %s - %s") % (
                    format_date(self.env, next_date), format_date(self.env, end_date)),
                'user_id': self.user_id.id,
                'date_invoice': self.recurring_next_date,
            }

    @api.multi
    def _recurring_create_invoice(self, automatic=False):
        #fix subscription dates
        auto_commit = self.env.context.get('auto_commit', True)
        cr = self.env.cr
        invoices = self.env['account.invoice']
        current_date = datetime.date.today()
        imd_res = self.env['ir.model.data']
        template_res = self.env['mail.template']
        if len(self) > 0:
            subscriptions = self
        else:
            domain = [('recurring_next_date', '<=', current_date),
                      '|', ('in_progress', '=', True), ('to_renew', '=', True)]
            subscriptions = self.search(domain)
        if subscriptions:
            sub_data = subscriptions.read(fields=['id', 'company_id'])
            for company_id in set(data['company_id'][0] for data in sub_data):
                sub_ids = [s['id'] for s in sub_data if s['company_id'][0] == company_id]
                subs = self.with_context(company_id=company_id, force_company=company_id).browse(sub_ids)
                context_company = dict(self.env.context, company_id=company_id, force_company=company_id)
                for subscription in subs:
                    subscription = subscription[
                        0]  # Trick to not prefetch other subscriptions, as the cache is currently invalidated at each iteration
                    if automatic and auto_commit:
                        cr.commit()
                    # payment + invoice (only by cron)
                    if subscription.template_id.payment_mode in ['validate_send_payment',
                                                                 'success_payment'] and subscription.recurring_total and automatic:
                        try:
                            payment_token = subscription.payment_token_id
                            tx = None
                            if payment_token:
                                invoice_values = subscription.with_context(
                                    lang=subscription.partner_id.lang)._prepare_invoice()
                                new_invoice = self.env['account.invoice'].with_context(context_company).create(
                                    invoice_values)
                                new_invoice.message_post_with_view(
                                    'mail.message_origin_link',
                                    values={'self': new_invoice, 'origin': subscription},
                                    subtype_id=self.env.ref('mail.mt_note').id)
                                tx = subscription._do_payment(payment_token, new_invoice, two_steps_sec=False)[0]
                                # commit change as soon as we try the payment so we have a trace somewhere
                                if auto_commit:
                                    cr.commit()
                                if tx.state in ['done', 'authorized']:
                                    subscription.send_success_mail(tx, new_invoice)
                                    msg_body = 'Automatic payment succeeded. Payment reference: <a href=# data-oe-model=payment.transaction data-oe-id=%d>%s</a>; Amount: %s. Invoice <a href=# data-oe-model=account.invoice data-oe-id=%d>View Invoice</a>.' % (
                                    tx.id, tx.reference, tx.amount, new_invoice.id)
                                    subscription.message_post(body=msg_body)
                                    if subscription.template_id.payment_mode == 'validate_send_payment':
                                        subscription.validate_and_send_invoice(new_invoice)
                                    if auto_commit:
                                        cr.commit()
                                else:
                                    _logger.error('Fail to create recurring invoice for subscription %s',
                                                  subscription.code)
                                    if auto_commit:
                                        cr.rollback()
                                    new_invoice.unlink()
                            if tx is None or tx.state != 'done':
                                amount = subscription.recurring_total
                                date_close = (
                                        subscription.recurring_next_date +
                                        relativedelta(days=subscription.template_id.auto_close_limit or
                                                           15)
                                )
                                close_subscription = current_date >= date_close
                                email_context = self.env.context.copy()
                                email_context.update({
                                    'payment_token': subscription.payment_token_id and subscription.payment_token_id.name,
                                    'renewed': False,
                                    'total_amount': amount,
                                    'email_to': subscription.partner_id.email,
                                    'code': subscription.code,
                                    'currency': subscription.pricelist_id.currency_id.name,
                                    'date_end': subscription.date,
                                    'date_close': date_close
                                })
                                if close_subscription:
                                    _, template_id = imd_res.get_object_reference('sale_subscription',
                                                                                  'email_payment_close')
                                    template = template_res.browse(template_id)
                                    template.with_context(email_context).send_mail(subscription.id)
                                    _logger.debug(
                                        "Sending Subscription Closure Mail to %s for subscription %s and closing subscription",
                                        subscription.partner_id.email, subscription.id)
                                    msg_body = 'Automatic payment failed after multiple attempts. Subscription closed automatically.'
                                    subscription.message_post(body=msg_body)
                                    subscription.set_close()
                                else:
                                    _, template_id = imd_res.get_object_reference('sale_subscription',
                                                                                  'email_payment_reminder')
                                    msg_body = 'Automatic payment failed. Subscription set to "To Renew".'
                                    if (datetime.date.today() - subscription.recurring_next_date).days in [0, 3, 7,
                                                                                                           14]:
                                        template = template_res.browse(template_id)
                                        template.with_context(email_context).send_mail(subscription.id)
                                        _logger.debug(
                                            "Sending Payment Failure Mail to %s for subscription %s and setting subscription to pending",
                                            subscription.partner_id.email, subscription.id)
                                        msg_body += ' E-mail sent to customer.'
                                    subscription.message_post(body=msg_body)
                                    subscription.set_to_renew()
                            if auto_commit:
                                cr.commit()
                        except Exception:
                            if auto_commit:
                                cr.rollback()
                            # we assume that the payment is run only once a day
                            traceback_message = traceback.format_exc()
                            _logger.error(traceback_message)
                            last_tx = self.env['payment.transaction'].search([('reference', 'like',
                                                                               'SUBSCRIPTION-%s-%s' % (
                                                                               subscription.id,
                                                                               datetime.date.today().strftime(
                                                                                   '%y%m%d')))], limit=1)
                            error_message = "Error during renewal of subscription %s (%s)" % (subscription.code,
                                                                                              'Payment recorded: %s' % last_tx.reference if last_tx and last_tx.state == 'done' else 'No payment recorded.')
                            _logger.error(error_message)

                    # invoice only
                    elif subscription.template_id.payment_mode in ['draft_invoice', 'validate_send']:
                        try:
                            invoice_values = subscription.with_context(
                                lang=subscription.partner_id.lang)._prepare_invoice()
                            new_invoice = self.env['account.invoice'].with_context(context_company).create(
                                invoice_values)
                            new_invoice.message_post_with_view(
                                'mail.message_origin_link',
                                values={'self': new_invoice, 'origin': subscription},
                                subtype_id=self.env.ref('mail.mt_note').id)
                            new_invoice.with_context(context_company).compute_taxes()
                            invoices += new_invoice
                            next_date = subscription.recurring_next_date or current_date
                            periods = {'daily': 'days', 'weekly': 'weeks', 'monthly': 'months', 'yearly': 'years'}
                            invoicing_period = relativedelta(
                                **{periods[subscription.recurring_rule_type]: subscription.recurring_interval})
                            new_date = next_date + invoicing_period
                            _logger.error("NEW DATE %s:", new_date)
                            if subscription.post_billed == True:
                                new_date_plus = new_date.replace(
                                    day=calendar.monthrange(new_date.year, new_date.month)[1])
                                _logger.error("post billed ticked and recurring next date is %s:", new_date_plus)
                                subscription.write({'recurring_next_date': new_date_plus.strftime('%Y-%m-%d')})
                            else:
                                subscription.write({'recurring_next_date': new_date.strftime('%Y-%m-%d')})
                                _logger.error("post billed NOT ticked and recurring next date is %s :", new_date)
                            if subscription.template_id.payment_mode == 'validate_send':
                                subscription.validate_and_send_invoice(new_invoice)
                            if automatic and auto_commit:
                                cr.commit()
                        except Exception:
                            if automatic and auto_commit:
                                cr.rollback()
                                _logger.exception('Fail to create recurring invoice for subscription %s',
                                                  subscription.code)
                            else:
                                raise
        return invoices


class AccountBankStatementLine(models.Model):
    _inherit = "account.bank.statement.line"
    _inherit = "account.bank.statement.import"
    _inherit = "account.bank.statement"
    _inherit = "res.partner"
    _inherit = "account.invoice"
    _inherit = "account.invoice.line"

    _name = 'boc.api'

    @api.model
    def _telecom_cron(self):

        todaycsv = str(datetime.date.today())
        timestamp = str(calendar.timegm(time.gmtime()))
        res_partner_model = self.env['res.partner']
        account_invoice_model = self.env['account.invoice']
        account_invoice_line_model = self.env['account.invoice.line']

        urlTransactionsList = 'http://omega-telecom.net/api/json/transactions/list/'
        urlCallHistory = 'http://omega-telecom.net/api/json/cdrs/list/'
        urlCustomerList = 'http://omega-telecom.net/api/json/customers/list/'

        timezone = pytz.timezone('Europe/Nicosia')
        # start
        tod_start = datetime.datetime.utcnow() - relativedelta(months=1)
        today_start = timezone.localize(tod_start)
        offset_start = today_start.utcoffset()
        offsetstr_start = str(offset_start)
        offsetstr2_start = offsetstr_start[0]
        offsetint_start = int(offsetstr2_start)

        # end
        tod_end = datetime.datetime.utcnow()
        today_end = timezone.localize(tod_end)
        offset_end = today_end.utcoffset()
        offsetstr_end = str(offset_end)
        offsetstr2_end = offsetstr_end[0]
        offsetint_end = int(offsetstr2_end)

        back1month = today_start - (relativedelta(months=1))
        startofmonth = back1month.replace(day=1)
        startofdayofmonth = back1month.replace(day=calendar.monthrange(back1month.year, back1month.month)[1])
        startofdayofmonth2 = ((startofdayofmonth.replace(hour=00, minute=00, second=00)) + relativedelta(
            days=1)) - relativedelta(hours=offsetint_start)
        endofmonth = today_start.replace(day=calendar.monthrange(today_start.year, today_start.month)[1])

        # unix start
        startofmonthstring = startofdayofmonth2.strftime("%d/%m/%Y, %H:%M:%S")
        date_startM = int((datetime.datetime.strptime(startofmonthstring, "%d/%m/%Y, %H:%M:%S").timestamp()))

        # unix end
        endofmonthendofday = (endofmonth.replace(hour=23, minute=59, second=59)) - relativedelta(hours=offsetint_end)
        endofmonthendofdaystring = endofmonthendofday.strftime("%d/%m/%Y, %H:%M:%S")
        date_endofday = int((datetime.datetime.strptime(endofmonthendofdaystring, "%d/%m/%Y, %H:%M:%S").timestamp()))
        _logger.error("start timestamp %r", date_startM)
        _logger.error("end timestamp %r", date_endofday)

        # customers NOC.CY.NET
        paramsCustomerList = {
            "auth_username": "NOC@cy.net",
            "auth_password": 'Qklg3Wuo1',
            "deleted": '0',  # MODECSOFT

        }

        r_customers = requests.post(urlCustomerList, params=paramsCustomerList)

        # r_customers
        data_cust = r_customers.json()
        data_customers = data_cust['data']
        customer_id = list((item['id']) for item in data_customers)
        customer_name = list((item['name']) for item in data_customers)


        # # customers NOC RESIDENTIAL parent ---------------------------------------------------------
        # paramsCustomerList2 = {
        #     "auth_username": "NOC@residential",
        #     "auth_password": 'asdm128AadS',
        #     "deleted": '0',
        #     "parent": '1077'
        #
        # }
        #
        #
        #
        # r_customers2 = requests.post(urlCustomerList, params=paramsCustomerList2)
        #
        # # r_customers
        # data_cust2 = r_customers2.json()
        # data_customers2 = data_cust2['data']
        # customer_id2 = list((item['id']) for item in data_customers2)
        # customer_name2 = list((item['name']) for item in data_customers2)

        # customers NOC RESIDENTIAL no parent ---------------------------------------------------------
        paramsCustomerList3 = {
            "auth_username": "NOC@residential",
            "auth_password": 'asdm128AadS',
            "deleted": '0',

        }

        r_customers3 = requests.post(urlCustomerList, params=paramsCustomerList3)

        # r_customers
        data_cust3 = r_customers3.json()
        data_customers3 = data_cust3['data']
        customer_id3 = list((item['id']) for item in data_customers3)
        customer_name3 = list((item['name']) for item in data_customers3)


        # _logger.error("ids from NOC residential parent: %r", customer_id2)
        # _logger.error("names from NOC residential parent: %r", customer_name2)
        _logger.error("ids from NOC cynet %r", customer_id)
        _logger.error("names from NOC cynet %r", customer_name)
        _logger.error("ids from NOC residential (no parent) %r", customer_id3)
        _logger.error("names from NOC residential (no parent) %r", customer_name3)


        # customers NOC RESIDENTIAL parent ---------------------------------------------------------
        # for id, name in zip(customer_id2, customer_name2):
        #     if account_invoice_model.search(["&", ["telephony_id", "=", id], ["state", "=", "draft"]]):
        #         partner_obj = self.env['res.partner'].search([["display_name", "=", name]])
        #         partner_obj_invoice = self.env['account.invoice'].search(
        #             ["&", ["telephony_id", "=", id], ["state", "=", "draft"]])
        #
        #         paramsCallHistory = {
        #             "auth_username": "NOC@residential",
        #             "auth_password": 'asdm128AadS',
        #             "customer": id,
        #             "start": date_startM,  # start of month timestamp
        #             "end": date_endofday,  # end of month timestamp
        #             "cost_customer": "scustomer",
        #             "direction": "out",
        #
        #         }
        #
        #         paramsTranssactionList = {
        #             "auth_username": "NOC@residential",
        #             "auth_password": 'asdm128AadS',
        #             "customer": id,  # loop customers
        #             "start": date_startM,
        #             "end": date_endofday,
        #
        #         }
        #         _logger.error("Customer Name to add to invoice(residential): %r", name)
        #
        #         r_calls = requests.post(urlCallHistory, params=paramsCallHistory)
        #         r_transactions = requests.post(urlTransactionsList, params=paramsTranssactionList)
        #         _logger.error("r_calls cynet parent: %r", r_calls)
        #         _logger.error("r_transactions cynet parent: %r", r_transactions)
        #         # r_calls
        #         data_c = r_calls.json()
        #         data_calls = data_c['data']
        #         sumcost = sum(float(item['cost_excluding_tax']) for item in data_calls)
        #         _logger.error("sum of outbound calls no tax: %r", sumcost)
        #
        #         # r_transactions
        #         data_t = r_transactions.json()
        #         data_transactions = data_t['data']
        #         _logger.info("transactions API: %r", data_t)
        #         transaction_desc = list((item['description']) for item in data_transactions)
        #         transaction_amount = list(float(item['amount_excluding_tax']) for item in data_transactions if
        #                                   float(item['amount_excluding_tax']) < 0)
        #         sumcostT = math.fsum(transaction_amount)
        #         sumTransactions = abs(sumcostT)
        #         _logger.error("sum of negative transactions no tax: %r", sumTransactions)
        #
        #         # line for transactions
        #         transline = account_invoice_line_model.search(
        #             [["product_id", "=", 645], ["invoice_id", "=", partner_obj_invoice.id]])
        #         transline.update({
        #             'price_unit': sumTransactions,
        #         })
        #
        #         # line for calls cost
        #         callsline = account_invoice_line_model.search(
        #             [["product_id", "=", 932], ["invoice_id", "=", partner_obj_invoice.id]])
        #         callsline.update({
        #             'price_unit': sumcost,
        #         })
        #         partner_obj_invoice.compute_taxes()

        # customers NOC RESIDENTIAL ---------------------------------------------------------
        for id, name in zip(customer_id3, customer_name3):
            if account_invoice_model.search(["&", ["telephony_id", "=", id], ["state", "=", "draft"]]):
                partner_obj_invoice = self.env['account.invoice'].search(
                    ["&", ["telephony_id", "=", id], ["state", "=", "draft"]])

                paramsCallHistory = {
                    "auth_username": "NOC@residential",
                    "auth_password": 'asdm128AadS',
                    "customer": id,
                    "start": date_startM,  # start of month timestamp
                    "end": date_endofday,  # end of month timestamp
                    "cost_customer": "scustomer",
                    "direction": "out",

                }

                paramsTranssactionList = {
                    "auth_username": "NOC@residential",
                    "auth_password": 'asdm128AadS',
                    "customer": id,  # loop customers
                    "start": date_startM,
                    "end": date_endofday,

                }
                _logger.error("Customer Name to add to invoice(residential): %r", name)

                r_calls = requests.post(urlCallHistory, params=paramsCallHistory)
                r_transactions = requests.post(urlTransactionsList, params=paramsTranssactionList)
                _logger.error("r_calls residential: %r", r_calls)
                _logger.error("r_transactions residential: %r", r_transactions)
                # r_calls
                data_c = r_calls.json()
                data_calls = data_c['data']
                sumcost = sum(float(item['cost_excluding_tax']) for item in data_calls)
                _logger.error("sum of outbound calls no tax: %r", sumcost)

                # r_transactions
                data_t = r_transactions.json()
                data_transactions = data_t['data']
                _logger.info("transactions API: %r", data_t)
                transaction_desc = list((item['description']) for item in data_transactions)
                transaction_amount = list(float(item['amount_excluding_tax']) for item in data_transactions if
                                          float(item['amount_excluding_tax']) < 0)
                sumcostT = math.fsum(transaction_amount)
                sumTransactions = abs(sumcostT)
                _logger.error("sum of negative transactions no tax: %r", sumTransactions)

                # line for transactions
                transline = account_invoice_line_model.search(
                    [["product_id", "=", 645], ["invoice_id", "=", partner_obj_invoice.id]])
                transline.update({
                    'price_unit': sumTransactions,
                })

                # line for calls cost
                callsline = account_invoice_line_model.search(
                    [["product_id", "=", 932], ["invoice_id", "=", partner_obj_invoice.id]])
                callsline.update({
                    'price_unit': sumcost,
                })
                partner_obj_invoice.compute_taxes()

        # customers NOC@cy.net

        for id, name in zip(customer_id, customer_name):
            if account_invoice_model.search(["&", ["telephony_id", "=", id], ["state", "=", "draft"]]):
                partner_obj_invoice = self.env['account.invoice'].search(
                    ["&", ["telephony_id", "=", id], ["state", "=", "draft"]])

                paramsCallHistory = {
                    "auth_username": "NOC@cy.net",
                    "auth_password": 'Qklg3Wuo1',
                    "customer": id,
                    "start": date_startM,  # start of month timestamp
                    "end": date_endofday,  # end of month timestamp
                    "cost_customer": "scustomer",
                    "direction": "out",

                }

                paramsTranssactionList = {
                    "auth_username": "NOC@cy.net",
                    "auth_password": 'Qklg3Wuo1',
                    "customer": id,  # loop customers
                    "start": date_startM,
                    "end": date_endofday,

                }
                _logger.error("Customer Name to add to invoice (cynet): %r", name)

                r_calls = requests.post(urlCallHistory, params=paramsCallHistory)
                r_transactions = requests.post(urlTransactionsList, params=paramsTranssactionList)
                _logger.error("r_calls cynet: %r", r_calls)
                _logger.error("r_transactions cynet: %r", r_transactions)
                # r_calls
                data_c = r_calls.json()
                data_calls = data_c['data']
                sumcost = sum(float(item['cost_excluding_tax']) for item in data_calls)
                _logger.error("sum of outbound calls no tax: %r", sumcost)

                # r_transactions
                sumTransactions_addtel = 0
                sumTransactions_num = 0
                sumTransactions_tel = 0
                data_t = r_transactions.json()
                data_transactions = data_t['data']
                _logger.info("transactions API: %r", data_t)
                transaction_desc = list((item['description']) for item in data_transactions if 'Recurring fee for number' in (item['description']))
                _logger.error("transaction_desc number : %r", transaction_desc)

                # get total of ALL transactions to compare with sumofall
                alltransactions = list(float(item['amount_excluding_tax']) for item in data_transactions if
                                              float(item['amount_excluding_tax']) < 0)
                sumoftransactions = math.fsum(alltransactions)
                comparesum = abs(sumoftransactions)


                # get total of transactions Recurring fee for number
                transaction_amount_num = list(float(item['amount_excluding_tax']) for item in data_transactions if
                                          float(item['amount_excluding_tax']) < 0 and 'Recurring fee for number' in (item['description']))
                sumcostTnum = math.fsum(transaction_amount_num)
                sumTransactions_num = abs(sumcostTnum)
                _logger.error("sum of negative transactions no tax Recurring fee for number: %r", sumTransactions_num)

                # get total of transactions Recurring fee for telephone
                transaction_amount_tel = list(float(item['amount_excluding_tax']) for item in data_transactions if
                                              float(item['amount_excluding_tax']) < 0 and 'Recurring fee for telephone' in (item['description']))
                sumcostTtel = math.fsum(transaction_amount_tel)
                sumTransactions_tel = abs(sumcostTtel)
                _logger.error("sum of negative transactions no tax Recurring fee for telephone: %r", sumTransactions_tel)

                # get total of transactions Add telephone
                transaction_amount_addtel = list(float(item['amount_excluding_tax']) for item in data_transactions if
                                              float(item['amount_excluding_tax']) < 0 and 'Add telephone' in (item['description']))
                sumcostTaddtel = math.fsum(transaction_amount_addtel)
                sumTransactions_addtel = abs(sumcostTaddtel)
                _logger.error("sum of negative transactions no tax Recurring fee for add tel: %r", sumTransactions_addtel)

                sumofall = sumTransactions_addtel+sumTransactions_num+sumTransactions_tel
                testsum = comparesum - sumofall
                _logger.error("sum of all negative transactions %r", sumofall)
                _logger.error("sum of all transactions minus sum of parsed transactions. If not 0, you have a prob %r", testsum)



                # line for transactions
                transline = account_invoice_line_model.search(
                    [["product_id", "=", 942], ["invoice_id", "=", partner_obj_invoice.id]])
                transline.update({
                    'price_unit': sumTransactions_num,
                })

                transline1 = account_invoice_line_model.search(
                    [["product_id", "=", 947], ["invoice_id", "=", partner_obj_invoice.id]])
                transline1.update({
                    'price_unit': sumTransactions_tel,
                })

                transline2 = account_invoice_line_model.search(
                    [["product_id", "=", 948], ["invoice_id", "=", partner_obj_invoice.id]])
                transline2.update({
                    'price_unit': sumTransactions_addtel,
                })

                # line for calls cost
                callsline = account_invoice_line_model.search(
                    [["product_id", "=", 943], ["invoice_id", "=", partner_obj_invoice.id]])
                callsline.update({
                    'price_unit': sumcost,
                    #'name': 'Total cost of outbound calls for ' + startofmonth.strftime("%B"),
                })
                partner_obj_invoice.compute_taxes()

