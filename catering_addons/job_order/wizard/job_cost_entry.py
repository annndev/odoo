from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..models.product import COST_GROUPS


class JobCostEntryWizard(models.TransientModel):
    _name = 'job.cost.entry.wizard'
    _description = 'Record a cost on a job (labour, breakage, subcontract)'

    job_id = fields.Many2one('job.order', required=True)
    company_id = fields.Many2one(related='job_id.company_id')
    currency_id = fields.Many2one(related='job_id.currency_id')
    cost_group = fields.Selection(COST_GROUPS, string='Group', required=True, default='labour')
    name = fields.Char(string='Description', required=True)
    amount = fields.Monetary(required=True)
    date = fields.Date(required=True, default=fields.Date.context_today)
    credit_account_id = fields.Many2one(
        'account.account', string='Counterpart Account', required=True,
        domain="[('company_ids', 'in', company_id), ('deprecated', '=', False)]",
        help='Account credited, e.g. 3341/33881 payable to shift staff, 1531 tools and supplies '
             'for breakage, 3311 a subcontractor.')
    partner_id = fields.Many2one('res.partner', string='Partner')

    @api.onchange('cost_group')
    def _onchange_cost_group(self):
        codes = {
            'labour': ['33881', '3388', '3341', '334'],
            'equipment': ['1531', '153'],
            'subcontract': ['3311', '331'],
        }.get(self.cost_group)
        if codes and self.job_id:
            self.credit_account_id = self.job_id.company_id._job_find_account(codes)

    def action_confirm(self):
        self.ensure_one()
        job = self.job_id
        job._check_not_closed()
        if self.currency_id.compare_amounts(self.amount, 0.0) <= 0:
            raise UserError(_('The amount must be positive.'))
        company = job.company_id
        label = f'{job.code} - {self.name}'
        move = self.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': company._job_get_journal().id,
            'date': self.date,
            'ref': label,
            'job_id': job.id,
            'line_ids': [
                (0, 0, {'name': label, 'account_id': company._job_get_wip_account().id,
                        'balance': self.amount, 'analytic_distribution': job._analytic_distribution(),
                        'job_cost_group': self.cost_group, 'partner_id': self.partner_id.id}),
                (0, 0, {'name': label, 'account_id': self.credit_account_id.id,
                        'balance': -self.amount, 'partner_id': self.partner_id.id}),
            ],
        })
        move.action_post()
        return {'type': 'ir.actions.act_window_close'}
