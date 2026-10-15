from odoo import fields, models, api


class ResPartner(models.Model):
    _inherit = "res.partner"

    billing_basis = fields.Selection(
        [
            ("normal", "Normal"),
            ("hour", "Hour Based"),
            ("month", "Monthly Based"),
        ],
        string="Qty Type",
        default="normal",
        help="Default quantity type for this customer.",
    )

    is_india_partner = fields.Boolean(
        string="Is India Partner",
        compute="_compute_is_india_partner",
        store=False,
    )

    @api.depends("country_id")
    def _compute_is_india_partner(self):
        for rec in self:
            rec.is_india_partner = rec.country_id.code == "IN" if rec.country_id else False