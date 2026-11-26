import logging

_logger = logging.getLogger(__name__)

# category xmlid -> {field: [account codes to try, in order]} on the VN chart (Circular 200 codes,
# which Circular 99 keeps for these accounts)
CATEGORY_ACCOUNTS = {
    'catering.product_category_raw': {
        'property_stock_valuation_account_id': ['152'],
        'property_account_expense_categ_id': ['1541', '154'],
    },
    'catering.product_category_semi': {
        'property_stock_valuation_account_id': ['155', '1551'],
        'property_account_expense_categ_id': ['1541', '154'],
    },
    'catering.product_category_dish': {
        'property_account_income_categ_id': ['5113'],
    },
    'catering.product_category_set': {
        'property_account_income_categ_id': ['5113'],
    },
    'catering.product_category_eq': {
        'property_stock_valuation_account_id': ['1531', '153'],
        'property_account_expense_categ_id': ['1541', '154'],
    },
    'catering.product_category_lab': {
        'property_account_expense_categ_id': ['1541', '154'],
    },
    'catering.product_category_serv': {
        'property_account_expense_categ_id': ['1541', '154'],
    },
}
STOCKED_CATEGORIES = ('catering.product_category_raw', 'catering.product_category_semi',
                      'catering.product_category_eq')


def _catering_setup_language(env):
    """Vietnamese is the default language; English stays installed and selectable."""
    env['res.lang']._activate_lang('vi_VN')
    env['ir.module.module'].search([('state', 'in', ('installed', 'to install', 'to upgrade'))]) \
        ._update_translations(['vi_VN'])
    env['ir.default'].set('res.partner', 'lang', 'vi_VN')
    admin = env.ref('base.user_admin', raise_if_not_found=False)
    users = (admin | env.ref('base.public_user', raise_if_not_found=False) or env['res.users'])
    users.filtered(lambda u: u.lang == 'en_US').write({'lang': 'vi_VN'})
    env['res.company'].search([]).partner_id.filtered(lambda p: p.lang == 'en_US').write({'lang': 'vi_VN'})


def _catering_prepare_vn_company(env, company):
    """Make a fresh company Vietnamese (country and VND) so that the VN chart can be loaded."""
    vnd = env.ref('base.VND')
    vnd.active = True
    company.write({'country_id': env.ref('base.vn').id, 'currency_id': vnd.id})


def _catering_finish_setup(env):
    """Load the VN chart on the main company when needed, then the catering accounts."""
    company = env.ref('base.main_company')
    if company.chart_template != 'vn' and not company.root_id._existing_accounting():
        env['account.chart.template'].try_loading('vn', company=company, install_demo=False)
    for company in env['res.company'].search([('chart_template', '!=', False)]):
        _catering_setup_accounts(env, company)


def _catering_setup_accounts(env, company):
    Company = company
    Account = env['account.account'].with_company(company)
    if not Company._job_find_account(['5113']):
        parent = Company._job_find_account(['511'])
        Account.create({
            'code': '5113',
            'name': 'Revenue from catering services',
            'account_type': 'income',
            'company_ids': [(6, 0, company.ids)],
            'tag_ids': [(6, 0, parent.tag_ids.ids)] if parent else [],
        }).with_context(lang='vi_VN').name = 'Doanh thu cung cấp dịch vụ tiệc'
    for xmlid, mapping in CATEGORY_ACCOUNTS.items():
        categ = env.ref(xmlid).with_company(company)
        vals = {}
        for fname, codes in mapping.items():
            account = Company._job_find_account(codes)
            if account:
                vals[fname] = account.id
        if xmlid in STOCKED_CATEGORIES:
            vals.update(property_valuation='real_time', property_cost_method='average')
            interim = Company._job_find_account(['151'])
            if interim:
                vals['property_stock_account_input_categ_id'] = interim.id
            output = Company._job_find_account(['632'])
            if output:
                vals['property_stock_account_output_categ_id'] = output.id
            journal = env['account.journal'].search([
                *env['account.journal']._check_company_domain(company), ('code', '=', 'STJ')], limit=1)
            if journal:
                vals['property_stock_journal'] = journal.id
        categ.write(vals)
    company_vals = {}
    if not company.job_wip_account_id:
        company_vals['job_wip_account_id'] = Company._job_find_account(['1541', '154']).id
    if not company.job_cogs_account_id:
        company_vals['job_cogs_account_id'] = Company._job_find_account(['632']).id
    company.write({k: v for k, v in company_vals.items() if v})
    if company.job_wip_account_id:
        company._job_get_consumption_location()


def _catering_post_init(env):
    env['res.lang']._activate_lang('vi_VN')
    company = env.ref('base.main_company')
    if company.chart_template != 'vn' and not company.root_id._existing_accounting():
        # Fresh database: switch the main company to Vietnam. The chart of accounts is only loaded
        # once the registry is ready (account defers it the same way), so the account setup follows it.
        _catering_prepare_vn_company(env, company)
        env.registry._auto_install_template = _catering_finish_setup
    else:
        if company.chart_template != 'vn':
            _logger.warning('Company %s already has accounting entries: the VN chart is not loaded.', company.name)
        for company in env['res.company'].search([('chart_template', '!=', False)]):
            _catering_setup_accounts(env, company)
    _catering_setup_language(env)
