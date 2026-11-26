from odoo import fields, models

from .product import COST_GROUPS


class AccountMove(models.Model):
    _inherit = 'account.move'

    job_id = fields.Many2one('job.order', string='Job', index=True, copy=False)

    def _post(self, soft=True):
        posted = super()._post(soft=soft)
        posted.filtered(lambda m: m.move_type == 'out_invoice')._job_reconcile_deposits()
        return posted

    def _job_reconcile_deposits(self):
        """Offset deposits received for the job against its final invoice."""
        for invoice in self:
            jobs = invoice.invoice_line_ids.sale_line_ids.order_id.job_id
            if not jobs:
                continue
            receivable = invoice.line_ids.filtered(
                lambda l: l.account_id.account_type == 'asset_receivable' and not l.reconciled)
            if not receivable:
                continue
            deposit_lines = jobs.payment_ids.filtered(lambda p: p.state in ('in_process', 'paid')).move_id.line_ids
            deposit_lines = deposit_lines.filtered(
                lambda l: l.account_id in receivable.account_id and not l.reconciled
                and l.partner_id.commercial_partner_id == invoice.commercial_partner_id)
            if deposit_lines:
                (receivable | deposit_lines).reconcile()


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    job_cost_group = fields.Selection(COST_GROUPS, string='Job Cost Group', copy=True)


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    job_id = fields.Many2one('job.order', string='Job', index=True, copy=False)
