from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    billing_basis = fields.Selection(
        [
            ("normal", "Normal"),
            ("hour", "Hour Based"),
            ("month", "Monthly Based"),
        ],
        string="Qty Type",
        default="normal",
        tracking=True,
        help="Defines whether sales quantity represents hours, months, or normal quantity.",
    )

    @api.onchange("partner_id")
    def _onchange_partner_id_set_billing_basis(self):
        for order in self:
            if order.partner_id:
                order.billing_basis = order.partner_id.billing_basis or "normal"
                for line in order.order_line:
                    line.billing_basis = order.billing_basis


    def _apply_statewise_gst(self):
        for order in self:
            partner = order.partner_shipping_id or order.partner_id
            if not partner or not partner.country_id:
                continue

            country_code = (partner.country_id.code or "").strip()
            customer_state_id = partner.state_id.id if partner.state_id else False
            company_state_id = order.company_id.partner_id.state_id.id if order.company_id.partner_id.state_id else False

            # Prefetch all taxes for the company to perform fast in-memory filtering
            # We do not restrict by type_tax_use here since child sales taxes are often 'none'
            all_taxes = self.env["account.tax"].search([
                ("company_id", "=", order.company_id.id),
            ])

            for line in order.order_line.filtered(lambda l: not l.display_type):
                if not line.product_id:
                    line.tax_ids = False
                    continue

                # Foreign customer -> No GST
                if country_code != "IN":
                    line.tax_ids = False
                    continue

                # Determine the target tax rate from the product's default taxes
                product_taxes = line.product_id.taxes_id.filtered(
                    lambda t: t.company_id == order.company_id
                )
                
                # If product has taxes, sum their amounts to get the total rate (e.g., 9% + 9% = 18%)
                target_rate = sum(product_taxes.mapped('amount')) if product_taxes else 18.0
                if target_rate <= 0:
                    target_rate = 18.0  # Fallback to standard 18% GST

                # Same state as company -> CGST + SGST (Grouped under "{rate}% GST S" or individual cgst/sgst)
                if customer_state_id and company_state_id and customer_state_id == company_state_id:
                    cgst_rate = target_rate / 2.0
                    sgst_rate = target_rate / 2.0

                    cgst = all_taxes.filtered(lambda t: "cgst s" in (t.name or "").lower() and t.amount == cgst_rate)[:1]
                    if not cgst:
                        cgst = all_taxes.filtered(lambda t: "cgst" in (t.name or "").lower() and t.amount == cgst_rate and "cgst p" not in (t.name or "").lower())[:1]

                    sgst = all_taxes.filtered(lambda t: "sgst s" in (t.name or "").lower() and t.amount == sgst_rate)[:1]
                    if not sgst:
                        sgst = all_taxes.filtered(lambda t: "sgst" in (t.name or "").lower() and t.amount == sgst_rate and "sgst p" not in (t.name or "").lower())[:1]

                    if cgst or sgst:
                        line.tax_ids = cgst | sgst
                    else:
                        # Fallback to grouped GST tax (e.g. "18% GST S") if individual ones not found
                        gst_s = all_taxes.filtered(
                            lambda t: "gst s" in (t.name or "").lower() 
                            and "igst" not in (t.name or "").lower() 
                            and "rc" not in (t.name or "").lower()
                            and t.amount == target_rate
                        )[:1]
                        line.tax_ids = gst_s
                else:
                    # Different state or missing state -> IGST
                    igst = all_taxes.filtered(lambda t: "igst s" in (t.name or "").lower() and t.amount == target_rate)[:1]
                    if not igst:
                        igst = all_taxes.filtered(lambda t: "igst" in (t.name or "").lower() and t.amount == target_rate and "igst p" not in (t.name or "").lower())[:1]
                    
                    # If specific IGST tax rate is not found, fallback to any sale IGST tax
                    if not igst:
                        igst = all_taxes.filtered(lambda t: "igst s" in (t.name or "").lower())[:1]
                    if not igst:
                        igst = all_taxes.filtered(lambda t: "igst" in (t.name or "").lower() and "igst p" not in (t.name or "").lower())[:1]

                    line.tax_ids = igst

    @api.onchange("partner_id", "partner_shipping_id", "order_line")
    def _onchange_auto_gst(self):
        self._apply_statewise_gst()