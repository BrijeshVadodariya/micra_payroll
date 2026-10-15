# -*- coding: utf-8 -*-
from odoo import api, fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    def action_print_pdf(self):
        self.ensure_one()
        report = self.env.ref("micra_payroll.action_report_export_invoice_custom", raise_if_not_found=False)
        if report:
            return report.report_action(self)
        return super().action_print_pdf() if hasattr(super(), 'action_print_pdf') else False


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # 1. Check if this is a down payment line
            name_lower = vals.get('name', '').lower() if vals.get('name') else ''
            is_downpayment = vals.get('is_downpayment') or 'down payment' in name_lower

            if is_downpayment:
                # 2. Extract the linked Sales Order line IDs
                sol_ids = []
                for command in vals.get('sale_line_ids') or []:
                    if isinstance(command, (list, tuple)) and len(command) >= 2:
                        if command[0] == 4:
                            sol_ids.append(command[1])
                        elif command[0] == 6 and len(command) >= 3:
                            sol_ids.extend(command[2])
                
                # 3. Match this down payment line to the corresponding original product
                sols = self.env['sale.order.line'].sudo().browse(sol_ids)
                if sols:
                    order = sols[0].order_id
                    non_dp = order.order_line.filtered(lambda l: not l.is_downpayment and not l.display_type)
                    matching = non_dp.filtered(lambda l: l.tax_ids == sols[0].tax_ids) or non_dp
                    if matching:
                        dp_lines = order.order_line.filtered(lambda l: l.is_downpayment and l.tax_ids == sols[0].tax_ids)
                        try:
                            index = dp_lines.ids.index(sols[0].id)
                        except ValueError:
                            index = 0
                        matched_line = matching[index % len(matching)]
                        vals['product_id'] = matched_line.product_id.id
                        
        return super().create(vals_list)


class AccountTax(models.Model):
    _inherit = 'account.tax'

    def _prepare_down_payment_lines(
        self,
        base_lines,
        company,
        amount_type,
        amount,
        computation_key='down_payment',
        grouping_function=None,
    ):
        # Prevent Odoo from grouping different product lines into a single down payment line.
        # This ensures we get a separate down payment line for each product in the Sales Order.
        if computation_key and computation_key.startswith('down_payment'):
            def get_unique_grouping_key(base_line):
                record = base_line.get('record')
                record_id = record.get('id', 0) if isinstance(record, dict) else getattr(record, 'id', 0)
                product = base_line.get('product_id')
                product_id = product.get('id', 0) if isinstance(product, dict) else getattr(product, 'id', 0)
                return {'sol_prod_key': f"{record_id}_{product_id}"}
            grouping_function = get_unique_grouping_key

        return super()._prepare_down_payment_lines(
            base_lines,
            company,
            amount_type,
            amount,
            computation_key=computation_key,
            grouping_function=grouping_function,
        )
