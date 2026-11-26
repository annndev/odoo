from odoo import fields, models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    job_id = fields.Many2one('job.order', string='Job', index=True, copy=False)


class StockMove(models.Model):
    _inherit = 'stock.move'

    def _job_get(self):
        return self.picking_id.job_id

    def _generate_valuation_lines_data(self, partner_id, qty, debit_value, credit_value,
                                       debit_account_id, credit_account_id, svl_id, description):
        res = super()._generate_valuation_lines_data(
            partner_id, qty, debit_value, credit_value, debit_account_id, credit_account_id, svl_id, description)
        job = self._job_get()
        if not job or not job.analytic_account_id:
            return res
        wip_account = job.company_id.job_wip_account_id or job.company_id._job_find_account(['1541', '154'])
        if not wip_account:
            return res
        # Issue to (or return from) the job: tag the WIP side with the job analytic and cost group.
        for key in ('debit_line_vals', 'credit_line_vals'):
            line_vals = res.get(key)
            if line_vals and line_vals.get('account_id') == wip_account.id:
                line_vals['analytic_distribution'] = job._analytic_distribution()
                line_vals['job_cost_group'] = self.product_id.job_cost_group or 'material'
        return res
