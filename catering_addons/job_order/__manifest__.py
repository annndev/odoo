{
    'name': 'Job Order Core',
    'version': '18.0.1.0.0',
    'category': 'Services/Project',
    'summary': 'Job-order ERP core: one analytic account per job, yield-based '
               'costing, procurement to the central store, issue to job (WIP), '
               'deposits, closeout to COGS and job P&L',
    'description': """
Generic job-order engine (the reusable 80% core of the blueprint).

* Job record that owns one analytic account; every revenue and cost line of the
  job carries it.
* Cost sheet in four resource groups (M material, L labour, E equipment,
  S subcontract/transport) with BoM kit explosion and yield factor:
  gross = net x quantity / yield.
* Purchase RFQs per vendor from the gross requirements.
* Issue-to-job pickings that post Dr WIP / Cr inventory with the job analytic.
* Customer deposits as advance payments on the receivable, reconciled on the
  final invoice (no revenue booked on deposit).
* Manual job cost entries (labour, breakage, subcontract) on WIP.
* Closeout wizard moving WIP to cost of goods sold, and a planned vs actual P&L.
""",
    'author': 'Oxy',
    'license': 'LGPL-3',
    'depends': ['sale_management', 'sale_stock', 'purchase_stock', 'stock_account', 'mrp', 'analytic'],
    'data': [
        'security/job_order_security.xml',
        'security/ir.model.access.csv',
        'data/job_order_data.xml',
        'wizard/job_cost_entry_views.xml',
        'wizard/job_deposit_views.xml',
        'views/job_order_views.xml',
        'views/product_views.xml',
        'views/res_config_settings_views.xml',
        'views/sale_purchase_stock_views.xml',
        'views/job_order_menus.xml',
    ],
    'installable': True,
    'application': True,
}
