# -*- coding: utf-8 -*-
from odoo import api, fields, models


class HrContract(models.Model):
    """
    Employee contract based on the visa, work permits
    allows to configure different Salary structure
    """
    _inherit = 'hr.version'

    struct_id = fields.Many2one(
        'hr.payroll.structure',
        string='Salary Structure',
        help="Choose Payroll Structure"
    )
    schedule_pay = fields.Selection([
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('semi-annually', 'Semi-annually'),
        ('annually', 'Annually'),
        ('weekly', 'Weekly'),
        ('bi-weekly', 'Bi-weekly'),
        ('bi-monthly', 'Bi-monthly'),
    ], string='Scheduled Pay', index=True, default='monthly',
        help="Defines the frequency of the wage payment.")
    hra = fields.Monetary(string='HRA', tracking=True,
                          help="House rent allowance.")
    travel_allowance = fields.Monetary(string="Travel Allowance",
                                       help="Travel allowance")
    da = fields.Monetary(string="DA", help="Dearness allowance")
    meal_allowance = fields.Monetary(string="Meal Allowance",
                                     help="Meal allowance")
    medical_allowance = fields.Monetary(string="Medical Allowance",
                                        help="Medical allowance")
    other_allowance = fields.Monetary(string="Other Allowance",
                                      help="Other allowances")

    def get_all_structures(self):
        """
        @return: the structures linked to the given contracts, ordered by
        hierarchy (parent=False first, then first level children and so on)
        and without duplicate
        """
        structures = self.mapped('struct_id') | self.mapped('contract_template_id.struct_id')
        if not structures:
            return []
        return list(set(structures._get_parent_structure().ids))

    def _get_whitelist_fields_from_template(self):
        fields_list = super()._get_whitelist_fields_from_template() if hasattr(super(), '_get_whitelist_fields_from_template') else []
        fields_list += ['struct_id', 'hra', 'travel_allowance', 'da', 'meal_allowance', 'medical_allowance', 'other_allowance', 'wage']
        return list(set(fields_list))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('wage') and vals.get('contract_template_id'):
                tmpl = self.browse(vals['contract_template_id'])
                if tmpl.wage:
                    vals['wage'] = tmpl.wage
        return super().create(vals_list)

    def write(self, vals):
        if 'contract_template_id' in vals and not vals.get('wage'):
            tmpl = self.browse(vals['contract_template_id'])
            if tmpl.wage:
                vals['wage'] = tmpl.wage
        return super().write(vals)

    def _get_contract_wage(self):
        self.ensure_one()
        wage = super()._get_contract_wage() if hasattr(super(), '_get_contract_wage') else getattr(self, 'wage', 0.0)
        if not wage:
            if self.contract_template_id and self.contract_template_id.wage:
                return self.contract_template_id.wage
            if self.employee_id and getattr(self.employee_id, 'wage', False):
                return self.employee_id.wage
        return wage

    def get_attribute(self, code, attribute):
        """Function to return attribute for Contract Advantage Template"""
        return self.env['hr.contract.advantage.template'].search(
            [('code', '=', code)], limit=1)[attribute]

    def set_attribute_value(self, code, active):
        """Function to set code for Contract"""
        for contract in self:
            if active:
                value = self.env['hr.contract.advantage.template'].search(
                    [('code', '=', code)], limit=1).default_value
                contract[code] = value
            else:
                contract[code] = 0.0
