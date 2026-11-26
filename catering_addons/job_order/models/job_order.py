from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare, float_is_zero, float_round

from .product import COST_GROUPS

JOB_STATES = [
    ('draft', 'New'),
    ('quoted', 'Quoted'),
    ('confirmed', 'Confirmed'),
    ('accepted', 'Accepted'),
    ('closed', 'Closed'),
    ('cancel', 'Cancelled'),
]


class JobOrder(models.Model):
    _name = 'job.order'
    _description = 'Job Order'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_start desc, id desc'
    _rec_names_search = ['name', 'code']

    # ------------------------------------------------------------------ fields
    code = fields.Char(string='Reference', readonly=True, copy=False, default='/', index=True)
    name = fields.Char(string='Title', required=True, tracking=True)
    state = fields.Selection(JOB_STATES, default='draft', required=True, tracking=True, copy=False)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    partner_id = fields.Many2one('res.partner', string='Customer', required=True, tracking=True)
    user_id = fields.Many2one('res.users', string='Responsible', default=lambda self: self.env.user, tracking=True)
    date_start = fields.Datetime(string='Start', tracking=True)
    date_end = fields.Datetime(string='End')
    notes = fields.Html()

    analytic_account_id = fields.Many2one(
        'account.analytic.account', string='Analytic Account', readonly=True, copy=False,
        help='Created with the job; every revenue and cost line of the job carries it.')
    sale_order_ids = fields.One2many('sale.order', 'job_id', string='Quotations')
    sale_order_id = fields.Many2one(
        'sale.order', string='Main Order', compute='_compute_sale_order_id', store=True)
    purchase_ids = fields.One2many('purchase.order', 'job_id', string='Purchase Orders')
    picking_ids = fields.One2many('stock.picking', 'job_id', string='Transfers')
    payment_ids = fields.One2many('account.payment', 'job_id', string='Deposits')
    close_move_id = fields.Many2one('account.move', string='Closeout Entry', readonly=True, copy=False)
    cost_line_ids = fields.One2many('job.cost.line', 'job_id', string='Cost Sheet', copy=True)

    # counts for smart buttons
    sale_order_count = fields.Integer(compute='_compute_counts')
    purchase_count = fields.Integer(compute='_compute_counts')
    picking_count = fields.Integer(compute='_compute_counts')
    invoice_count = fields.Integer(compute='_compute_counts')
    payment_count = fields.Integer(compute='_compute_counts')
    move_line_count = fields.Integer(compute='_compute_counts')

    # planning
    contingency_pct = fields.Float(string='Contingency (%)', default=4.0,
                                   help='Risk reserve added on top of the planned cost to get the floor price.')
    markup_pct = fields.Float(string='Markup (%)', default=30.0,
                              help='Cost-plus markup on the floor price for the suggested price.')
    planned_material = fields.Monetary(compute='_compute_planned', string='Planned M')
    planned_labour = fields.Monetary(compute='_compute_planned', string='Planned L')
    planned_equipment = fields.Monetary(compute='_compute_planned', string='Planned E')
    planned_subcontract = fields.Monetary(compute='_compute_planned', string='Planned S')
    planned_cost = fields.Monetary(compute='_compute_planned', string='Planned Cost')
    floor_price = fields.Monetary(compute='_compute_planned', string='Floor Price',
                                  help='Planned cost plus contingency: the lowest acceptable price.')
    suggested_price = fields.Monetary(compute='_compute_planned', string='Suggested Price')
    quoted_amount = fields.Monetary(compute='_compute_planned', string='Quoted (untaxed)')
    planned_margin = fields.Monetary(compute='_compute_planned', string='Planned Margin')
    below_floor = fields.Boolean(compute='_compute_planned')

    # deposits
    deposit_pct = fields.Float(string='Deposit (%)', default=50.0, tracking=True)
    deposit_amount = fields.Monetary(compute='_compute_deposit', string='Deposit Requested')
    deposit_received = fields.Monetary(compute='_compute_deposit', string='Deposit Received')

    # actuals (from posted journal items carrying the job analytic account)
    actual_revenue = fields.Monetary(compute='_compute_actuals', string='Revenue')
    actual_material = fields.Monetary(compute='_compute_actuals', string='Actual M')
    actual_labour = fields.Monetary(compute='_compute_actuals', string='Actual L')
    actual_equipment = fields.Monetary(compute='_compute_actuals', string='Actual E')
    actual_subcontract = fields.Monetary(compute='_compute_actuals', string='Actual S')
    actual_cost = fields.Monetary(compute='_compute_actuals', string='Actual Cost')
    actual_margin = fields.Monetary(compute='_compute_actuals', string='Gross Margin')
    actual_margin_pct = fields.Float(compute='_compute_actuals', string='Gross Margin (%)')
    wip_balance = fields.Monetary(compute='_compute_actuals', string='Open WIP')

    _sql_constraints = [
        ('code_company_uniq', 'unique(code, company_id)', 'The job reference must be unique per company.'),
    ]

    # ----------------------------------------------------------------- compute
    @api.depends('sale_order_ids.state')
    def _compute_sale_order_id(self):
        for job in self:
            orders = job.sale_order_ids.filtered(lambda so: so.state != 'cancel')
            confirmed = orders.filtered(lambda so: so.state == 'sale')
            job.sale_order_id = (confirmed or orders)[:1]

    def _compute_counts(self):
        for job in self:
            job.sale_order_count = len(job.sale_order_ids)
            job.purchase_count = len(job.purchase_ids)
            job.picking_count = len(job.picking_ids)
            job.invoice_count = len(job._get_invoices())
            job.payment_count = len(job.payment_ids)
            job.move_line_count = len(job._get_job_move_lines())

    @api.depends('cost_line_ids.planned_amount', 'cost_line_ids.cost_group', 'contingency_pct',
                 'markup_pct', 'sale_order_id.amount_untaxed')
    def _compute_planned(self):
        for job in self:
            by_group = defaultdict(float)
            for line in job.cost_line_ids:
                by_group[line.cost_group] += line.planned_amount
            job.planned_material = by_group['material']
            job.planned_labour = by_group['labour']
            job.planned_equipment = by_group['equipment']
            job.planned_subcontract = by_group['subcontract']
            job.planned_cost = sum(by_group.values())
            job.floor_price = job.planned_cost * (1 + job.contingency_pct / 100.0)
            job.suggested_price = job.floor_price * (1 + job.markup_pct / 100.0)
            job.quoted_amount = job.sale_order_id.amount_untaxed
            job.planned_margin = job.quoted_amount - job.planned_cost
            job.below_floor = bool(job.quoted_amount) and job.currency_id.compare_amounts(
                job.quoted_amount, job.floor_price) < 0

    @api.depends('deposit_pct', 'sale_order_id.amount_total', 'payment_ids.state', 'payment_ids.amount')
    def _compute_deposit(self):
        for job in self:
            job.deposit_amount = job.currency_id.round(job.sale_order_id.amount_total * job.deposit_pct / 100.0)
            job.deposit_received = sum(
                job.payment_ids.filtered(lambda p: p.state in ('in_process', 'paid')).mapped('amount'))

    @api.depends('state', 'close_move_id')
    def _compute_actuals(self):
        # Read from posted journal items; not stored, recomputed on every read of a fresh record.
        for job in self:
            revenue = wip = 0.0
            costs = defaultdict(float)
            wip_account = job.company_id.job_wip_account_id or job.company_id._job_find_account(['1541', '154'])
            for line, share in job._get_job_move_lines_with_share():
                amount = line.balance * share
                if line.account_id.internal_group == 'income':
                    revenue -= amount
                    continue
                is_wip = line.account_id == wip_account
                if is_wip:
                    wip += amount
                if line.move_id == job.close_move_id:
                    continue
                if is_wip or line.account_id.internal_group == 'expense':
                    group = line.job_cost_group or line.product_id.job_cost_group or 'material'
                    costs[group] += amount
            job.actual_revenue = revenue
            job.actual_material = costs['material']
            job.actual_labour = costs['labour']
            job.actual_equipment = costs['equipment']
            job.actual_subcontract = costs['subcontract']
            job.actual_cost = sum(costs.values())
            job.actual_margin = revenue - job.actual_cost
            job.actual_margin_pct = revenue and job.actual_margin / revenue * 100.0
            job.wip_balance = wip

    # ------------------------------------------------------------------- CRUD
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('code', '/') == '/':
                vals['code'] = self.env['ir.sequence'].next_by_code('job.order') or '/'
        jobs = super().create(vals_list)
        for job in jobs:
            job._create_analytic_account()
        return jobs

    @api.depends('code', 'name')
    def _compute_display_name(self):
        for job in self:
            job.display_name = f'[{job.code}] {job.name}' if job.code and job.code != '/' else job.name

    def _get_analytic_plan(self):
        plan = self.env.ref('job_order.analytic_plan_jobs', raise_if_not_found=False)
        if not plan:
            plan = self.env['account.analytic.plan'].sudo().create({'name': _('Jobs')})
        return plan

    def _create_analytic_account(self):
        self.ensure_one()
        if self.analytic_account_id:
            return
        self.analytic_account_id = self.env['account.analytic.account'].sudo().create({
            'name': self.name,
            'code': self.code,
            'plan_id': self._get_analytic_plan().id,
            'partner_id': self.partner_id.id,
            'company_id': self.company_id.id,
        })

    def write(self, vals):
        if 'state' not in vals and any(job.state == 'closed' for job in self) and \
                set(vals) - {'message_main_attachment_id', 'notes'}:
            raise UserError(_('A closed job cannot be modified. Reopen it first.'))
        res = super().write(vals)
        if 'name' in vals:
            self.analytic_account_id.sudo().write({'name': vals['name']})
        return res

    # ---------------------------------------------------------------- helpers
    def _analytic_distribution(self):
        self.ensure_one()
        return {str(self.analytic_account_id.id): 100.0} if self.analytic_account_id else False

    def _get_job_move_lines(self):
        self.ensure_one()
        if not self.analytic_account_id:
            return self.env['account.move.line']
        return self.env['account.move.line'].search([
            ('analytic_distribution', 'in', [self.analytic_account_id.id]),
            ('parent_state', '=', 'posted'),
            ('company_id', '=', self.company_id.id),
        ])

    def _get_job_move_lines_with_share(self):
        """Yield (move line, share of the line that belongs to this job)."""
        self.ensure_one()
        key = str(self.analytic_account_id.id)
        for line in self._get_job_move_lines():
            percentage = 0.0
            for keys, pct in (line.analytic_distribution or {}).items():
                if key in keys.split(','):
                    percentage += pct
            if percentage:
                yield line, percentage / 100.0

    def _get_invoices(self):
        self.ensure_one()
        return self.sale_order_ids.invoice_ids

    def _check_not_closed(self):
        for job in self:
            if job.state in ('closed', 'cancel'):
                raise UserError(_('Job %s is closed or cancelled.', job.display_name))

    # ---------------------------------------------------------------- costing
    def _get_kit_bom(self, product):
        bom = self.env['mrp.bom']._bom_find(product, company_id=self.company_id.id, bom_type='phantom')[product]
        return bom

    def _explode_net_requirements(self):
        """Explode the main order's kit products into net quantities of leaf components.

        :return: dict product -> net quantity in the product's UoM
        """
        self.ensure_one()
        needs = defaultdict(float)
        order = self.sale_order_id
        for so_line in order.order_line.filtered(lambda l: l.product_id and not l.display_type):
            product = so_line.product_id
            bom = self._get_kit_bom(product)
            if not bom:
                if product.type == 'consu' and product.purchase_ok:
                    needs[product] += so_line.product_uom._compute_quantity(so_line.product_uom_qty, product.uom_id)
                continue
            qty_bom_uom = so_line.product_uom._compute_quantity(so_line.product_uom_qty, bom.product_uom_id)
            _boms, lines = bom.explode(product, qty_bom_uom / bom.product_qty)
            for bom_line, line_data in lines:
                component = bom_line.product_id
                if component.type != 'consu':
                    continue
                needs[component] += bom_line.product_uom_id._compute_quantity(
                    line_data['qty'], component.uom_id, round=False)
        return needs

    def action_compute_cost_sheet(self):
        """(Re)build the material lines of the cost sheet from the main order's menu/kits."""
        self._check_not_closed()
        for job in self:
            if not job.sale_order_id:
                raise UserError(_('Create a quotation with the menu/kits first.'))
            job.cost_line_ids.filtered('is_auto').unlink()
            vals = []
            for product, net_qty in job._explode_net_requirements().items():
                vals.append({
                    'job_id': job.id,
                    'is_auto': True,
                    'cost_group': product.job_cost_group or 'material',
                    'product_id': product.id,
                    'name': product.display_name,
                    'net_qty': net_qty,
                    'yield_factor': product.yield_factor or 1.0,
                    'uom_id': product.uom_id.id,
                    'unit_cost': product.standard_price,
                })
            self.env['job.cost.line'].create(vals)
        return True

    # ------------------------------------------------------------- quotation
    def _prepare_sale_order_vals(self):
        self.ensure_one()
        return {
            'partner_id': self.partner_id.id,
            'job_id': self.id,
            'company_id': self.company_id.id,
            'user_id': self.user_id.id,
            'origin': self.code,
        }

    def action_create_quotation(self):
        self.ensure_one()
        self._check_not_closed()
        order = self.env['sale.order'].create(self._prepare_sale_order_vals())
        if self.state == 'draft':
            self.state = 'quoted'
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'res_id': order.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _on_sale_confirmed(self):
        self.filtered(lambda j: j.state in ('draft', 'quoted')).write({'state': 'confirmed'})

    # ----------------------------------------------------------- procurement
    def _get_material_lines(self):
        return self.cost_line_ids.filtered(
            lambda l: l.cost_group == 'material' and l.product_id.type == 'consu' and l.product_id.purchase_ok)

    def action_generate_purchases(self):
        """Create draft RFQs (one per vendor) for the gross quantities still to order."""
        self.ensure_one()
        self._check_not_closed()
        PurchaseOrder = self.env['purchase.order']
        picking_type = self.env['stock.picking.type'].search([
            ('code', '=', 'incoming'),
            ('warehouse_id.company_id', '=', self.company_id.id),
        ], limit=1)
        by_vendor = defaultdict(list)
        missing_vendor = self.env['product.product']
        for line in self._get_material_lines():
            to_order = line.gross_qty - line.ordered_qty
            if float_compare(to_order, 0.0, precision_rounding=line.uom_id.rounding) <= 0:
                continue
            seller = line.product_id._select_seller(quantity=to_order, uom_id=line.uom_id)
            if not seller:
                missing_vendor |= line.product_id
                continue
            by_vendor[seller.partner_id].append((line, to_order))
        if not by_vendor and not missing_vendor:
            raise UserError(_('Everything on the cost sheet is already ordered.'))
        orders = PurchaseOrder
        for vendor, lines in by_vendor.items():
            order_lines = []
            for line, qty in lines:
                product = line.product_id
                po_uom = product.uom_po_id or product.uom_id
                order_lines.append((0, 0, {
                    'product_id': product.id,
                    'product_qty': line.uom_id._compute_quantity(qty, po_uom, rounding_method='UP'),
                    'product_uom': po_uom.id,
                }))
            orders |= PurchaseOrder.create({
                'partner_id': vendor.id,
                'job_id': self.id,
                'company_id': self.company_id.id,
                'origin': self.code,
                'picking_type_id': picking_type.id,
                'order_line': order_lines,
            })
        if missing_vendor:
            self.message_post(body=_(
                'No vendor is set for: %s. Add a vendor on these products or buy them manually.',
                ', '.join(missing_vendor.mapped('display_name'))))
        return self._action_view(orders, 'purchase.order')

    def action_issue_materials(self):
        """Create a transfer from the central store to job consumption for the gross quantities not yet issued."""
        self.ensure_one()
        self._check_not_closed()
        warehouse = self.env['stock.warehouse'].search([('company_id', '=', self.company_id.id)], limit=1)
        if not warehouse:
            raise UserError(_('No warehouse found for company %s.', self.company_id.name))
        destination = self.company_id._job_get_consumption_location()
        moves = []
        for line in self._get_material_lines().filtered(lambda l: l.product_id.is_storable):
            to_issue = line.gross_qty - line.issued_qty
            if float_compare(to_issue, 0.0, precision_rounding=line.uom_id.rounding) <= 0:
                continue
            moves.append((0, 0, {
                'name': line.product_id.display_name,
                'product_id': line.product_id.id,
                'product_uom': line.uom_id.id,
                'product_uom_qty': float_round(to_issue, precision_rounding=line.uom_id.rounding, rounding_method='UP'),
                'location_id': warehouse.lot_stock_id.id,
                'location_dest_id': destination.id,
                'company_id': self.company_id.id,
            }))
        if not moves:
            raise UserError(_('Every stocked material on the cost sheet has already been issued.'))
        picking = self.env['stock.picking'].create({
            'picking_type_id': warehouse.int_type_id.id,
            'location_id': warehouse.lot_stock_id.id,
            'location_dest_id': destination.id,
            'job_id': self.id,
            'origin': self.code,
            'partner_id': self.partner_id.id,
            'move_ids': moves,
        })
        picking.action_confirm()
        return self._action_view(picking, 'stock.picking')

    # ---------------------------------------------------------- lifecycle
    def action_accept(self):
        for job in self:
            if job.state != 'confirmed':
                raise UserError(_('Only a confirmed job can be accepted.'))
        self.write({'state': 'accepted'})

    def _prepare_closeout_move(self):
        self.ensure_one()
        company = self.company_id
        wip_account = company._job_get_wip_account()
        wip = sum(line.balance * share for line, share in self._get_job_move_lines_with_share()
                  if line.account_id == wip_account)
        if float_is_zero(wip, precision_rounding=self.currency_id.rounding):
            return False
        distribution = self._analytic_distribution()
        label = _('Closeout %s', self.display_name)
        return {
            'move_type': 'entry',
            'journal_id': company._job_get_journal().id,
            'date': fields.Date.context_today(self),
            'ref': label,
            'job_id': self.id,
            'line_ids': [
                (0, 0, {'name': label, 'account_id': company._job_get_cogs_account().id,
                        'balance': wip, 'analytic_distribution': distribution}),
                (0, 0, {'name': label, 'account_id': wip_account.id,
                        'balance': -wip, 'analytic_distribution': distribution}),
            ],
        }

    def action_close(self):
        """Move the job's work in progress to cost of goods sold and lock the job."""
        for job in self:
            if job.state not in ('confirmed', 'accepted'):
                raise UserError(_('Only a confirmed or accepted job can be closed.'))
            draft_invoices = job._get_invoices().filtered(lambda m: m.state == 'draft')
            if draft_invoices:
                raise UserError(_('Post or cancel the draft invoices of %s before closing it.', job.display_name))
            open_pickings = job.picking_ids.filtered(lambda p: p.state not in ('done', 'cancel'))
            if open_pickings:
                raise UserError(_('Validate or cancel the open transfers of %s before closing it.',
                                  job.display_name))
            vals = job._prepare_closeout_move()
            if vals:
                move = self.env['account.move'].create(vals)
                move.action_post()
                job.close_move_id = move
            job.state = 'closed'
        return True

    def action_reopen(self):
        for job in self:
            if job.state != 'closed':
                continue
            if job.close_move_id:
                job.close_move_id._reverse_moves(
                    [{'ref': _('Reopen %s', job.display_name)}], cancel=True)
            job.write({'state': 'accepted', 'close_move_id': False})

    def action_cancel(self):
        for job in self:
            if job.state == 'closed':
                raise UserError(_('Reopen the job before cancelling it.'))
            if job.sale_order_ids.filtered(lambda so: so.state == 'sale'):
                raise UserError(_('Cancel the confirmed order of %s first.', job.display_name))
        self.write({'state': 'cancel'})

    def action_draft(self):
        self.filtered(lambda j: j.state == 'cancel').write({'state': 'draft'})

    # ------------------------------------------------------------- wizards
    def action_open_deposit_wizard(self):
        self.ensure_one()
        self._check_not_closed()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Register Deposit'),
            'res_model': 'job.deposit.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_job_id': self.id},
        }

    def action_open_cost_entry_wizard(self):
        self.ensure_one()
        self._check_not_closed()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Record Job Cost'),
            'res_model': 'job.cost.entry.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_job_id': self.id},
        }

    # --------------------------------------------------------- smart buttons
    def _action_view(self, records, model):
        action = {
            'type': 'ir.actions.act_window',
            'res_model': model,
            'name': self.env['ir.model']._get(model).name,
            'domain': [('id', 'in', records.ids)],
            'context': {'default_job_id': self.id, 'create': False},
        }
        if len(records) == 1:
            action.update(view_mode='form', res_id=records.id)
        else:
            action.update(view_mode='list,form')
        return action

    def action_view_sale_orders(self):
        self.ensure_one()
        return self._action_view(self.sale_order_ids, 'sale.order')

    def action_view_purchases(self):
        self.ensure_one()
        return self._action_view(self.purchase_ids, 'purchase.order')

    def action_view_pickings(self):
        self.ensure_one()
        return self._action_view(self.picking_ids, 'stock.picking')

    def action_view_invoices(self):
        self.ensure_one()
        return self._action_view(self._get_invoices(), 'account.move')

    def action_view_payments(self):
        self.ensure_one()
        return self._action_view(self.payment_ids, 'account.payment')

    def action_view_move_lines(self):
        self.ensure_one()
        action = self._action_view(self._get_job_move_lines(), 'account.move.line')
        action.update(view_mode='list', res_id=False)
        return action
