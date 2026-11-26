from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests import Form, tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon

from ..hooks import _catering_setup_accounts


@tagged('post_install', '-at_install')
class TestCateringFlow(AccountTestInvoicingCommon):
    """End-to-end event: lead won -> costed quote -> deposit -> purchase -> issue -> invoice -> closeout,
    checking every posting of blueprint stages 3, 4, 5, 6 and 7 on the Vietnamese chart."""

    @classmethod
    @AccountTestInvoicingCommon.setup_country('vn')
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.company_data['company']
        _catering_setup_accounts(cls.env, cls.company)
        cls.env.user.groups_id |= cls.env.ref('stock.group_stock_manager') | cls.env.ref('purchase.group_purchase_manager') \
            | cls.env.ref('sales_team.group_sale_manager') | cls.env.ref('mrp.group_mrp_manager')

        def account(code):
            return cls.company._job_find_account([code])

        cls.acc = {code: account(code) for code in
                   ('1131', '1311', '151', '152', '1541', '3311', '33311', '33881', '5113', '632')}
        cls.uom_kg = cls.env.ref('uom.product_uom_kgm')
        cls.uom_g = cls.env.ref('uom.product_uom_gram')
        cls.uom_pax = cls.env.ref('catering.uom_pax')
        cls.uom_portion = cls.env.ref('catering.uom_portion')
        cls.vat10_sale = cls.company_data['default_tax_sale']
        cls.vendor = cls.env['res.partner'].create({'name': 'Seafood vendor'})
        cls.customer = cls.env['res.partner'].create({'name': 'Gala customer', 'is_company': True})

        cls.fish = cls.env['product.product'].create({
            'name': 'Whole sea bass',
            'catering_type': 'raw',
            'sku_group': 'tfish',
            'sku_spec': 'seabass',
            'categ_id': cls.env.ref('catering.product_category_raw').id,
            'type': 'consu',
            'is_storable': True,
            'uom_id': cls.uom_kg.id,
            'uom_po_id': cls.uom_kg.id,
            'standard_price': 180000,
            'yield_factor': 0.6,
            'supplier_taxes_id': [Command.clear()],
            'seller_ids': [Command.create({'partner_id': cls.vendor.id, 'price': 180000})],
        })
        cls.dish = cls.env['product.product'].create({
            'name': 'Pan-seared sea bass',
            'catering_type': 'dish',
            'sku_group': 'MAIN',
            'sku_spec': 'FISH',
            'categ_id': cls.env.ref('catering.product_category_dish').id,
            'type': 'consu',
            'uom_id': cls.uom_portion.id,
            'uom_po_id': cls.uom_portion.id,
        })
        cls.buffet = cls.env['product.product'].create({
            'name': 'Buffet VIP',
            'catering_type': 'set',
            'sku_group': 'TBUFFET',
            'categ_id': cls.env.ref('catering.product_category_set').id,
            'type': 'consu',
            'uom_id': cls.uom_pax.id,
            'uom_po_id': cls.uom_pax.id,
            'list_price': 500000,
            'invoice_policy': 'order',
            'taxes_id': [Command.set(cls.vat10_sale.ids)],
        })
        cls.env['mrp.bom'].create({
            'product_tmpl_id': cls.dish.product_tmpl_id.id,
            'product_uom_id': cls.uom_portion.id,
            'type': 'phantom',
            'bom_line_ids': [Command.create({'product_id': cls.fish.id, 'product_qty': 150,
                                             'product_uom_id': cls.uom_g.id})],
        })
        cls.env['mrp.bom'].create({
            'product_tmpl_id': cls.buffet.product_tmpl_id.id,
            'product_uom_id': cls.uom_pax.id,
            'type': 'phantom',
            'bom_line_ids': [Command.create({'product_id': cls.dish.id, 'product_qty': 1,
                                             'product_uom_id': cls.uom_portion.id})],
        })

    # ------------------------------------------------------------------ helpers
    def _lines(self, moves):
        """{account code: balance} of the given moves."""
        result = {}
        for line in moves.line_ids:
            result[line.account_id.code] = result.get(line.account_id.code, 0.0) + line.balance
        return {code: balance for code, balance in result.items() if balance}

    def _won_event(self, pax=100):
        lead = self.env['crm.lead'].create({
            'name': 'Year-end gala',
            'type': 'opportunity',
            'partner_id': self.customer.id,
            'event_type': 'buffet',
            'pax_estimated': pax,
            'budget_per_pax': 550000,
        })
        lead.action_set_won()
        return lead.job_id

    def _quote(self, job, pax=100):
        action = job.action_create_quotation()
        order = self.env['sale.order'].browse(action['res_id'])
        order.order_line = [Command.create({
            'product_id': self.buffet.id, 'product_uom_qty': pax, 'product_uom': self.uom_pax.id,
            'price_unit': 500000, 'tax_id': [Command.set(self.vat10_sale.ids)]})]
        return order

    # -------------------------------------------------------------------- tests
    def test_sku_codes(self):
        self.assertEqual(self.fish.default_code, 'RAW-TFISH-SEABASS-001')
        self.assertEqual(self.buffet.default_code, 'SET-TBUFFET-001')
        other = self.env['product.product'].create({
            'name': 'Sea bass fillet', 'catering_type': 'raw', 'sku_group': 'TFISH', 'sku_spec': 'SEABASS'})
        self.assertEqual(other.default_code, 'RAW-TFISH-SEABASS-002')
        with self.assertRaises(ValidationError):
            self.env['product.product'].create({'name': 'Bad', 'catering_type': 'raw', 'sku_group': 'MEAT-1'})

    def test_yield_must_be_a_share(self):
        with self.assertRaises(ValidationError):
            self.fish.yield_factor = 1.5
        with self.assertRaises(ValidationError):
            self.fish.yield_factor = 0

    def test_won_lead_creates_event_with_analytic(self):
        job = self._won_event()
        self.assertTrue(job)
        self.assertEqual(job.state, 'draft')
        self.assertEqual(job.pax_estimated, 100)
        self.assertTrue(job.analytic_account_id)
        self.assertEqual(job.analytic_account_id.plan_id, self.env.ref('job_order.analytic_plan_jobs'))

    def test_gross_quantity_uses_yield(self):
        """Blueprint check: 150 g net x 100 pax / 0.6 yield = 25 kg of whole fish."""
        job = self._won_event()
        self._quote(job)
        job.action_compute_cost_sheet()
        line = job.cost_line_ids
        self.assertEqual(len(line), 1)
        self.assertEqual(line.product_id, self.fish)
        self.assertAlmostEqual(line.net_qty, 15.0)
        self.assertAlmostEqual(line.gross_qty, 25.0)
        self.assertAlmostEqual(job.planned_material, 25 * 180000)
        self.assertAlmostEqual(job.quoted_amount, 50000000)
        self.assertAlmostEqual(job.food_cost_ratio, 9.0)
        self.assertTrue(job.food_ratio_warning)
        # recomputing keeps manual lines and rebuilds the menu lines
        job.cost_line_ids = [Command.create({'cost_group': 'labour', 'name': '10 waiters', 'net_qty': 10,
                                             'unit_cost': 400000})]
        job.action_compute_cost_sheet()
        self.assertEqual(len(job.cost_line_ids), 2)
        self.assertAlmostEqual(job.planned_cost, 4500000 + 4000000)
        self.assertAlmostEqual(job.floor_price, 8500000 * 1.04)

    def test_full_event_postings(self):
        job = self._won_event()
        order = self._quote(job)
        job.action_compute_cost_sheet()

        # Stage 3: deposit 50% -> Dr outstanding receipts (bank) / Cr 1311, no revenue
        self.assertEqual(job.state, 'quoted')
        job.deposit_pct = 50
        self.assertAlmostEqual(job.deposit_amount, 27500000)  # 50% of 55,000,000 incl. VAT
        wizard = Form(self.env['job.deposit.wizard'].with_context(default_job_id=job.id)).save()
        wizard.action_confirm()
        payment = job.payment_ids
        self.assertEqual(payment.state, 'in_process')
        self.assertEqual(self._lines(payment.move_id), {'1131': 27500000, '1311': -27500000})
        self.assertAlmostEqual(job.deposit_received, 27500000)

        order.action_confirm()
        self.assertEqual(job.state, 'confirmed')
        self.assertFalse(order.picking_ids, 'job orders must not create customer deliveries')

        # Stage 4: purchase 25 kg to the central kitchen, receive, bill
        action = job.action_generate_purchases()
        po = self.env['purchase.order'].browse(action['res_id'])
        self.assertEqual(po.partner_id, self.vendor)
        self.assertAlmostEqual(po.order_line.product_qty, 25.0)
        po.button_confirm()
        receipt = po.picking_ids
        self.assertEqual(receipt.job_id, job)
        receipt.move_ids.quantity = 25.0
        receipt.button_validate()
        self.assertEqual(self._lines(receipt.move_ids.account_move_ids), {'152': 4500000, '151': -4500000})
        with self.assertRaises(UserError):
            job.action_generate_purchases()

        # issue to the event: Dr 1541 (event analytic) / Cr 152
        action = job.action_issue_materials()
        issue = self.env['stock.picking'].browse(action['res_id'])
        issue.move_ids.quantity = 25.0
        issue.button_validate()
        issue_moves = issue.move_ids.account_move_ids
        self.assertEqual(self._lines(issue_moves), {'1541': 4500000, '152': -4500000})
        wip_line = issue_moves.line_ids.filtered(lambda l: l.account_id == self.acc['1541'])
        self.assertEqual(wip_line.analytic_distribution, {str(job.analytic_account_id.id): 100.0})
        self.assertEqual(wip_line.job_cost_group, 'material')
        self.assertAlmostEqual(job.cost_line_ids.issued_qty, 25.0)

        # Stage 5: shift labour -> Dr 1541 / Cr 33881
        entry = self.env['job.cost.entry.wizard'].create({
            'job_id': job.id, 'cost_group': 'labour', 'name': 'Waiters, 10 shifts', 'amount': 3000000,
            'credit_account_id': self.acc['33881'].id})
        entry.action_confirm()
        self.assertAlmostEqual(job.actual_labour, 3000000)
        self.assertAlmostEqual(job.wip_balance, 7500000)

        # acceptance needs the actual number of guests
        with self.assertRaises(UserError):
            job.action_accept()
        job.pax_actual = 100
        job.action_accept()
        self.assertEqual(job.state, 'accepted')

        # Stage 6: final invoice -> Dr 1311 / Cr 5113 (analytic) + Cr 33311, deposit offset
        invoice = order._create_invoices()
        invoice.action_post()
        self.assertEqual(self._lines(invoice), {'1311': 55000000, '5113': -50000000, '33311': -5000000})
        revenue_line = invoice.line_ids.filtered(lambda l: l.account_id == self.acc['5113'])
        self.assertEqual(revenue_line.analytic_distribution, {str(job.analytic_account_id.id): 100.0})
        self.assertAlmostEqual(invoice.amount_residual, 27500000)
        self.assertAlmostEqual(job.actual_revenue, 50000000)

        # Stage 7: closeout -> Dr 632 / Cr 1541, WIP empty, P&L
        job.action_close()
        self.assertEqual(job.state, 'closed')
        self.assertEqual(self._lines(job.close_move_id), {'632': 7500000, '1541': -7500000})
        self.assertAlmostEqual(job.wip_balance, 0.0)
        self.assertAlmostEqual(job.actual_material, 4500000)
        self.assertAlmostEqual(job.actual_cost, 7500000)
        self.assertAlmostEqual(job.actual_margin, 42500000)
        with self.assertRaises(UserError):
            job.name = 'changed after close'

        # reopening reverses the closeout
        job.action_reopen()
        self.assertEqual(job.state, 'accepted')
        self.assertAlmostEqual(job.wip_balance, 7500000)
