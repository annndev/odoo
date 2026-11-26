{
    'name': 'Catering B2B',
    'version': '18.0.1.0.0',
    'category': 'Services/Catering',
    'summary': 'Catering & event skin on the job-order core: events, menus with '
               'yield, SKU scheme, Vietnamese accounting defaults',
    'description': """
Catering B2B skin for the Job Order Core.

* Jobs become catering events: event type, pax, budget per pax, allergies,
  venue survey (power, field kitchen, freight lift), actual pax at acceptance.
* Won CRM opportunities create the event and its analytic account.
* Product types RAW / SEMI / DISH / SET / EQ / LAB / SERV with the SKU scheme
  TYPE-GROUP-SPEC-NNN and default categories, valuation and accounts
  (VN chart: 152, 1551, 1531, 1541, 5113, 632).
* Target cost ratios on the cost sheet (food 28-35%, labour 12-18%).
* Vietnamese by default, English available.
""",
    'author': 'Oxy',
    'license': 'LGPL-3',
    'depends': ['job_order', 'crm', 'sale_crm', 'l10n_vn'],
    'data': [
        'data/catering_data.xml',
        'views/product_views.xml',
        'views/job_order_views.xml',
        'views/crm_lead_views.xml',
        'views/catering_menus.xml',
    ],
    'demo': [
        'demo/catering_demo.xml',
    ],
    'post_init_hook': '_catering_post_init',
    'installable': True,
    'application': True,
}
