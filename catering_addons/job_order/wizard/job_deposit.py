from odoo import _, api, fields, models
from odoo.exceptions import UserError


class JobDepositWizard(models.TransientModel):
    _name = 'job.deposit.wizard'
    _description = 'Register a customer deposit on a job'

    job_id = fields.Many2one('job.order', required=True)
    company_id = fields.Many2one(related='job_id.company_id')
    currency_id = fields.Many2one(related='job_id.currency_id')
    amount = fields.Monetary(required=True, compute='_compute_amount', store=True, readonly=False)
    date = fields.Date(required=True, default=fields.Date.context_today)
    journal_id = fields.Many2one(
        'account.journal', required=True,
        domain="[('company_id', '=', company_id), ('type', 'in', ('bank', 'cash'))]",
        default=lambda self: self.env['account.journal'].search([
            *self.env['account.journal']._check_company_domain(self.env.company),
            ('type', '=', 'bank')], limit=1))
    memo = fields.Char()

    @api.depends('job_id')
    def _compute_amount(self):
        for wizard in self:
            wizard.amount = max(wizard.job_id.deposit_amount - wizard.job_id.deposit_received, 0.0)

    def action_confirm(self):
        """Post an advance payment: Dr bank / Cr receivable. No revenue is recognised."""
        self.ensure_one()
        job = self.job_id
        job._check_not_closed()
        if self.currency_id.compare_amounts(self.amount, 0.0) <= 0:
            raise UserError(_('The deposit amount must be positive.'))
        payment = self.env['account.payment'].create({
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'partner_id': job.partner_id.commercial_partner_id.id,
            'amount': self.amount,
            'currency_id': self.currency_id.id,
            'date': self.date,
            'journal_id': self.journal_id.id,
            'memo': self.memo or _('Deposit %s', job.code),
            'job_id': job.id,
        })
        payment.action_post()
        return {'type': 'ir.actions.act_window_close'}
