import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

CATERING_TYPES = [
    ('raw', 'RAW - Raw material'),
    ('semi', 'SEMI - Kitchen semi-finished'),
    ('dish', 'DISH - Finished dish'),
    ('set', 'SET - Set menu / package'),
    ('eq', 'EQ - Equipment & tableware'),
    ('lab', 'LAB - Shift labour'),
    ('serv', 'SERV - Outsourced service'),
]

# catering type -> (SKU prefix, category xmlid, product type, storable, job cost group)
TYPE_RULES = {
    'raw': ('RAW', 'catering.product_category_raw', 'consu', True, 'material'),
    'semi': ('SEMI', 'catering.product_category_semi', 'consu', True, 'material'),
    'dish': ('DISH', 'catering.product_category_dish', 'consu', False, 'material'),
    'set': ('SET', 'catering.product_category_set', 'consu', False, 'material'),
    'eq': ('EQ', 'catering.product_category_eq', 'consu', True, 'equipment'),
    'lab': ('LAB', 'catering.product_category_lab', 'service', False, 'labour'),
    'serv': ('SERV', 'catering.product_category_serv', 'service', False, 'subcontract'),
}
SKU_PART = re.compile(r'^[A-Z0-9]{2,12}$')


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    catering_type = fields.Selection(CATERING_TYPES, string='Catering Type', index=True)
    sku_group = fields.Char(string='SKU Group', help='Second part of the code, e.g. MEAT, SAUCE, MAIN, BUFFET.')
    sku_spec = fields.Char(string='SKU Spec', help='Third part of the code, e.g. BEEF, PEP, CHAF.')

    @api.onchange('catering_type')
    def _onchange_catering_type(self):
        rules = TYPE_RULES.get(self.catering_type)
        if not rules:
            return
        _prefix, categ_xmlid, ptype, storable, group = rules
        self.type = ptype
        self.is_storable = storable
        self.job_cost_group = group
        categ = self.env.ref(categ_xmlid, raise_if_not_found=False)
        if categ:
            self.categ_id = categ
        if self.catering_type in ('dish', 'set'):
            self.purchase_ok = False
            self.sale_ok = True
            self.invoice_policy = 'order'
        elif self.catering_type in ('raw', 'eq', 'serv'):
            self.purchase_ok = True

    @api.constrains('sku_group', 'sku_spec')
    def _check_sku_parts(self):
        for product in self:
            for part in (product.sku_group, product.sku_spec):
                if part and not SKU_PART.match(part):
                    raise ValidationError(_(
                        'SKU group and spec must be 2 to 12 capital letters or digits (got "%s").', part))

    @api.model
    def _catering_next_code(self, catering_type, group, spec):
        prefix = TYPE_RULES[catering_type][0]
        stem = '-'.join(p for p in (prefix, group, spec) if p)
        existing = self.with_context(active_test=False).search_read(
            [('default_code', '=like', f'{stem}-%')], ['default_code'])
        numbers = [int(m.group(1)) for r in existing
                   if (m := re.match(rf'^{re.escape(stem)}-(\d+)$', r['default_code'] or ''))]
        return f'{stem}-{(max(numbers) if numbers else 0) + 1:03d}'

    def _catering_normalise(self, vals):
        for key in ('sku_group', 'sku_spec'):
            if vals.get(key):
                vals[key] = vals[key].strip().upper()
        return vals

    def _catering_assign_codes(self):
        """Give a TYPE-GROUP-SPEC-NNN code to catering items that have none yet."""
        for template in self.filtered(lambda t: t.catering_type and t.sku_group and not t.default_code):
            template.default_code = self._catering_next_code(
                template.catering_type, template.sku_group, template.sku_spec)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._catering_normalise(vals)
        templates = super().create(vals_list)
        templates._catering_assign_codes()
        return templates

    def write(self, vals):
        self._catering_normalise(vals)
        res = super().write(vals)
        if {'catering_type', 'sku_group', 'sku_spec'} & set(vals):
            self._catering_assign_codes()
        return res

    def action_catering_generate_code(self):
        for product in self.filtered(lambda p: p.catering_type and p.sku_group):
            product.default_code = self._catering_next_code(
                product.catering_type, product.sku_group, product.sku_spec)


class ProductProduct(models.Model):
    _inherit = 'product.product'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self.env['product.template']._catering_normalise(vals)
        products = super().create(vals_list)
        products.product_tmpl_id._catering_assign_codes()
        return products
