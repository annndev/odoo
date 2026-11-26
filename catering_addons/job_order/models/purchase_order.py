from odoo import fields, models


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    job_id = fields.Many2one('job.order', string='Job', index=True, copy=False,
                             domain="[('company_id', '=', company_id), ('state', 'not in', ('closed', 'cancel'))]")

    def _prepare_picking(self):
        vals = super()._prepare_picking()
        if self.job_id:
            vals['job_id'] = self.job_id.id
        return vals
