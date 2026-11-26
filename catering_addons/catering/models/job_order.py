from odoo import _, api, fields, models
from odoo.exceptions import UserError

EVENT_TYPES = [
    ('buffet', 'Buffet'),
    ('set_menu', 'Set menu'),
    ('tea_break', 'Tea break'),
    ('cocktail', 'Cocktail'),
    ('box_meal', 'Box meal'),
    ('other', 'Other'),
]

# Target cost ratios of the blueprint, as share of the quoted price (%)
FOOD_RATIO = (28.0, 35.0)
LABOUR_RATIO = (12.0, 18.0)


class JobOrder(models.Model):
    _inherit = 'job.order'

    event_type = fields.Selection(EVENT_TYPES, string='Event Type', tracking=True)
    pax_estimated = fields.Integer(string='Estimated Pax', tracking=True)
    pax_actual = fields.Integer(string='Actual Pax', tracking=True,
                                help='Guests actually served, confirmed in the acceptance record.')
    budget_per_pax = fields.Monetary(string='Budget per Pax')
    price_per_pax = fields.Monetary(string='Quoted per Pax', compute='_compute_catering_ratios')
    venue = fields.Char(string='Venue')
    venue_address = fields.Char(string='Venue Address')
    allergy_notes = fields.Text(string='Allergies & Dietary Needs')
    vegetarian_pax = fields.Integer(string='Vegetarian Pax')
    survey_power = fields.Char(string='Power Available', help='e.g. 3-phase 30 kW near the kitchen area')
    survey_field_kitchen = fields.Boolean(string='Field Kitchen Allowed')
    survey_freight_lift = fields.Boolean(string='Freight Lift')
    survey_notes = fields.Text(string='Survey Notes')

    food_cost_ratio = fields.Float(string='Food Cost (%)', compute='_compute_catering_ratios')
    labour_cost_ratio = fields.Float(string='Labour Cost (%)', compute='_compute_catering_ratios')
    food_ratio_warning = fields.Boolean(compute='_compute_catering_ratios')
    labour_ratio_warning = fields.Boolean(compute='_compute_catering_ratios')
    over_budget = fields.Boolean(compute='_compute_catering_ratios')

    @api.depends('quoted_amount', 'planned_material', 'planned_labour', 'pax_estimated', 'budget_per_pax')
    def _compute_catering_ratios(self):
        for job in self:
            quoted = job.quoted_amount
            job.food_cost_ratio = quoted and job.planned_material / quoted * 100.0
            job.labour_cost_ratio = quoted and job.planned_labour / quoted * 100.0
            job.food_ratio_warning = bool(quoted and job.planned_material) and not (
                FOOD_RATIO[0] <= job.food_cost_ratio <= FOOD_RATIO[1])
            job.labour_ratio_warning = bool(quoted and job.planned_labour) and not (
                LABOUR_RATIO[0] <= job.labour_cost_ratio <= LABOUR_RATIO[1])
            job.price_per_pax = job.pax_estimated and quoted / job.pax_estimated
            job.over_budget = bool(job.budget_per_pax and job.pax_estimated) and \
                job.currency_id.compare_amounts(job.price_per_pax, job.budget_per_pax) > 0

    def action_accept(self):
        for job in self:
            if job.pax_estimated and job.pax_actual <= 0:
                raise UserError(_('Enter the actual number of guests served before accepting %s.',
                                  job.display_name))
        return super().action_accept()
