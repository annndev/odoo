from odoo import _, fields, models
from odoo.exceptions import UserError


class ResCompany(models.Model):
    _inherit = 'res.company'

    job_wip_account_id = fields.Many2one(
        'account.account', string='Job WIP Account',
        help='Work in progress account debited by issues and cost entries of a job (VN: 154).')
    job_cogs_account_id = fields.Many2one(
        'account.account', string='Job Cost of Sales Account',
        help='Account debited when a job is closed out (VN: 632).')
    job_journal_id = fields.Many2one(
        'account.journal', string='Job Journal',
        help='Miscellaneous journal used for job cost entries and closeouts.')
    job_consumption_location_id = fields.Many2one(
        'stock.location', string='Job Consumption Location',
        help='Virtual location goods are issued to when consumed by a job.')

    def _job_find_account(self, codes):
        """Return the first account of this company whose code is in ``codes`` (in order)."""
        self.ensure_one()
        Account = self.env['account.account'].with_company(self)
        for code in codes:
            account = Account.search([*Account._check_company_domain(self), ('code', '=', code)], limit=1)
            if account:
                return account
        return Account

    def _job_get_wip_account(self):
        self.ensure_one()
        account = self.job_wip_account_id or self._job_find_account(['1541', '154'])
        if not account:
            raise UserError(_('Set a Job WIP account in the settings of company %s.', self.name))
        return account

    def _job_get_cogs_account(self):
        self.ensure_one()
        account = self.job_cogs_account_id or self._job_find_account(['632'])
        if not account:
            raise UserError(_('Set a Job cost of sales account in the settings of company %s.', self.name))
        return account

    def _job_get_journal(self):
        self.ensure_one()
        journal = self.job_journal_id or self.env['account.journal'].search([
            *self.env['account.journal']._check_company_domain(self),
            ('type', '=', 'general'),
        ], limit=1)
        if not journal:
            raise UserError(_('Set a Job journal in the settings of company %s.', self.name))
        return journal

    def _job_get_consumption_location(self):
        self.ensure_one()
        if self.job_consumption_location_id:
            return self.job_consumption_location_id
        location = self.env['stock.location'].sudo().create({
            'name': _('Job Consumption'),
            'usage': 'inventory',
            'company_id': self.id,
            'location_id': self.env.ref('stock.stock_location_locations_virtual').id,
            'valuation_in_account_id': self._job_get_wip_account().id,
        })
        self.sudo().job_consumption_location_id = location
        return location


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    job_wip_account_id = fields.Many2one(related='company_id.job_wip_account_id', readonly=False)
    job_cogs_account_id = fields.Many2one(related='company_id.job_cogs_account_id', readonly=False)
    job_journal_id = fields.Many2one(related='company_id.job_journal_id', readonly=False)
    job_consumption_location_id = fields.Many2one(related='company_id.job_consumption_location_id', readonly=False)
