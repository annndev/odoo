from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    job_id = fields.Many2one('job.order', string='Job', index=True, copy=False,
                             domain="[('company_id', '=', company_id), ('state', 'not in', ('closed', 'cancel'))]")

    def action_confirm(self):
        res = super().action_confirm()
        self.job_id._on_sale_confirmed()
        return res


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def _action_launch_stock_rule(self, previous_product_uom_qty=False):
        """Goods of a job leave the store through issue-to-job transfers, not customer deliveries."""
        return super(SaleOrderLine, self.filtered(lambda l: not l.order_id.job_id))._action_launch_stock_rule(
            previous_product_uom_qty=previous_product_uom_qty)

    @api.depends('order_id.job_id')
    def _compute_analytic_distribution(self):
        super()._compute_analytic_distribution()
        for line in self:
            job = line.order_id.job_id
            if job.analytic_account_id and not line.display_type:
                line.analytic_distribution = job._analytic_distribution()
