from odoo import _, api, fields, models

from .job_order import EVENT_TYPES


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    event_type = fields.Selection(EVENT_TYPES, string='Event Type')
    pax_estimated = fields.Integer(string='Estimated Pax')
    budget_per_pax = fields.Monetary(string='Budget per Pax', currency_field='company_currency')
    event_date = fields.Datetime(string='Event Date')
    venue = fields.Char(string='Venue')
    allergy_notes = fields.Text(string='Allergies & Dietary Needs')
    job_id = fields.Many2one('job.order', string='Event', copy=False, readonly=True)

    def _prepare_catering_event_vals(self):
        self.ensure_one()
        return {
            'name': self.name,
            'partner_id': self.partner_id.id,
            'user_id': self.user_id.id or self.env.user.id,
            'company_id': (self.company_id or self.env.company).id,
            'event_type': self.event_type,
            'pax_estimated': self.pax_estimated,
            'budget_per_pax': self.budget_per_pax,
            'date_start': self.event_date,
            'venue': self.venue,
            'allergy_notes': self.allergy_notes,
        }

    def action_set_won(self):
        res = super().action_set_won()
        for lead in self.filtered(lambda l: not l.job_id and l.partner_id and (l.pax_estimated or l.event_type)):
            lead.job_id = self.env['job.order'].create(lead._prepare_catering_event_vals())
            lead.message_post(body=_('Event %s created.', lead.job_id._get_html_link()))
        return res

    def action_view_catering_event(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'job.order',
            'res_id': self.job_id.id,
            'view_mode': 'form',
        }
