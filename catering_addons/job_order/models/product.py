from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

COST_GROUPS = [
    ('material', 'M - Material'),
    ('labour', 'L - Labour'),
    ('equipment', 'E - Equipment & Rental'),
    ('subcontract', 'S - Subcontract & Transport'),
]


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    job_cost_group = fields.Selection(
        COST_GROUPS, string='Job Cost Group', default='material',
        help='Resource group this item is counted in on job cost sheets and P&L.')
    yield_factor = fields.Float(
        string='Yield', default=1.0, digits=(3, 4),
        help='Usable share after preparation (0 to 1). Purchased (gross) quantity = '
             'net quantity / yield. Example: whole sea bass filleted to 60% -> 0.6.')

    @api.constrains('yield_factor')
    def _check_yield_factor(self):
        for product in self:
            if not 0 < product.yield_factor <= 1:
                raise ValidationError(_('The yield of %s must be greater than 0 and at most 1.', product.display_name))

    @api.model
    def _job_gross_qty(self, net_qty, yield_factor):
        return net_qty / (yield_factor or 1.0)
