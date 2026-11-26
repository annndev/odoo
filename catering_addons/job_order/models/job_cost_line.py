from odoo import api, fields, models

from .product import COST_GROUPS


class JobCostLine(models.Model):
    _name = 'job.cost.line'
    _description = 'Job Cost Sheet Line'
    _order = 'job_id, sequence, cost_group, id'

    job_id = fields.Many2one('job.order', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='job_id.company_id', store=True)
    currency_id = fields.Many2one(related='job_id.currency_id')
    sequence = fields.Integer(default=10)
    is_auto = fields.Boolean(string='From Menu', readonly=True,
                             help='Generated from the order kits; rebuilt on every cost sheet computation.')
    cost_group = fields.Selection(COST_GROUPS, string='Group', required=True, default='material')
    product_id = fields.Many2one('product.product', string='Item')
    name = fields.Char(string='Description', required=True)
    uom_id = fields.Many2one('uom.uom', string='Unit')
    net_qty = fields.Float(string='Net Qty', digits='Product Unit of Measure',
                           help='Quantity actually used/served (after preparation losses).')
    yield_factor = fields.Float(string='Yield', digits=(3, 4), default=1.0)
    gross_qty = fields.Float(string='Gross Qty', digits='Product Unit of Measure',
                             compute='_compute_gross_qty', store=True,
                             help='Quantity to buy and issue: net quantity / yield.')
    unit_cost = fields.Monetary(string='Unit Cost')
    planned_amount = fields.Monetary(string='Planned', compute='_compute_planned_amount', store=True)
    ordered_qty = fields.Float(string='Ordered', compute='_compute_progress', digits='Product Unit of Measure')
    issued_qty = fields.Float(string='Issued', compute='_compute_progress', digits='Product Unit of Measure')

    @api.depends('net_qty', 'yield_factor')
    def _compute_gross_qty(self):
        for line in self:
            line.gross_qty = self.env['product.template']._job_gross_qty(line.net_qty, line.yield_factor)

    @api.depends('gross_qty', 'unit_cost')
    def _compute_planned_amount(self):
        for line in self:
            line.planned_amount = line.currency_id.round(line.gross_qty * line.unit_cost) \
                if line.currency_id else line.gross_qty * line.unit_cost

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.name = self.product_id.display_name
            self.uom_id = self.product_id.uom_id
            self.unit_cost = self.product_id.standard_price
            self.cost_group = self.product_id.job_cost_group or self.cost_group
            self.yield_factor = self.product_id.yield_factor or 1.0

    @api.depends('product_id', 'uom_id',
                 'job_id.purchase_ids.state', 'job_id.purchase_ids.order_line.product_qty',
                 'job_id.picking_ids.move_ids.state', 'job_id.picking_ids.move_ids.quantity')
    def _compute_progress(self):
        for line in self:
            ordered = issued = 0.0
            product = line.product_id
            if product and line.uom_id:
                for po_line in line.job_id.purchase_ids.filtered(lambda po: po.state != 'cancel').order_line:
                    if po_line.product_id == product:
                        ordered += po_line.product_uom._compute_quantity(po_line.product_qty, line.uom_id)
                consumption = line.job_id.company_id.job_consumption_location_id
                for move in line.job_id.picking_ids.move_ids.filtered(lambda m: m.state == 'done'):
                    if move.product_id != product:
                        continue
                    qty = move.product_uom._compute_quantity(move.quantity, line.uom_id)
                    if move.location_dest_id == consumption:
                        issued += qty
                    elif move.location_id == consumption:
                        issued -= qty
            line.ordered_qty = ordered
            line.issued_qty = issued
