from odoo import api, fields, models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    billing_basis = fields.Selection(
        related="order_id.billing_basis",
        string="Qty Type",
        store=True,
        readonly=True,
    )

    qty_type_label = fields.Char(
        string="Qty Type Label",
        compute="_compute_qty_type_label",
        store=False,
    )

    @api.depends("billing_basis")
    def _compute_qty_type_label(self):
        for line in self:
            if line.billing_basis == "hour":
                line.qty_type_label = "Qty (Hrs)"
            elif line.billing_basis == "month":
                line.qty_type_label = "Qty (Month)"
            else:
                line.qty_type_label = "Qty"

    @api.depends('product_id', 'product_uom_id', 'company_id', 'order_id.partner_id', 'order_id.partner_shipping_id')
    def _compute_tax_ids(self):
        super()._compute_tax_ids()
        for line in self:
            if line.order_id:
                line.order_id._apply_statewise_gst()