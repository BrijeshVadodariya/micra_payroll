# -*- coding: utf-8 -*-
import babel
import calendar
from datetime import date, datetime, time, timedelta
from dateutil.relativedelta import relativedelta
import logging
import pytz
from pytz import timezone

from odoo import api, fields, models, tools, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

# This will generate 16th of days
ROUNDING_FACTOR = 16


class HrPayslip(models.Model):
    """Payroll Pay Slip for an Employee with Attendance and Leave Integration"""
    _name = 'hr.payslip'
    _inherit = 'mail.thread'
    _description = 'Pay Slip'

    struct_id = fields.Many2one(
        comodel_name='hr.payroll.structure',
        string='Structure',
        help='Defines the rules that have to be applied to this payslip.'
    )
    name = fields.Char(string='Payslip Name', help="Enter Payslip Name")
    number = fields.Char(string='Reference', copy=False, help="References for Payslip")
    employee_id = fields.Many2one(
        comodel_name='hr.employee',
        string='Employee',
        required=True,
        help="Choose Employee for Payslip"
    )
    date_from = fields.Date(
        string='Date From',
        required=True,
        help="Start date for Payslip",
        default=lambda self: fields.Date.to_string(date.today().replace(day=1))
    )
    date_to = fields.Date(
        string='Date To',
        required=True,
        help="End date for Payslip",
        default=lambda self: fields.Date.to_string(
            (datetime.now() + relativedelta(months=+1, day=1, days=-1)).date())
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('verify', 'Waiting'),
            ('done', 'Done'),
            ('cancel', 'Rejected'),
        ],
        string='Status',
        index=True,
        readonly=True,
        copy=False,
        default='draft',
        help="* Draft: Payslip is created\n"
             "* Waiting: Under verification\n"
             "* Done: Payslip is confirmed\n"
             "* Rejected: Payslip is cancelled"
    )
    line_ids = fields.One2many(
        'hr.payslip.line',
        'slip_id',
        string='Payslip Lines',
        help="Choose Payslip for line"
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company.id
    )
    worked_days_line_ids = fields.One2many(
        'hr.payslip.worked.days',
        'payslip_id',
        string='Payslip Worked Days',
        copy=True,
        help="Payslip worked days for line"
    )
    input_line_ids = fields.One2many(
        'hr.payslip.input',
        'payslip_id',
        string='Payslip Inputs',
        help="Choose Payslip Input"
    )
    paid = fields.Boolean(
        string='Made Payment Order ? ',
        copy=False,
        help="Is Payment Order"
    )
    note = fields.Text(string='Internal Note', help="Description for Payslip")
    contract_id = fields.Many2one(
        'hr.version',
        string='Contract',
        help="Choose Contract for Payslip"
    )
    details_by_salary_rule_category_ids = fields.One2many(
        comodel_name='hr.payslip.line',
        compute='_compute_details_by_salary_rule_category_ids',
        string='Details by Salary Rule Category',
        help="Details from the salary rule category"
    )
    credit_note = fields.Boolean(
        string='Credit Note',
        help="Indicates this payslip has a refund of another"
    )
    payslip_run_id = fields.Many2one(
        'hr.payslip.run',
        string='Payslip Batches',
        copy=False,
        help="Choose Payslip Run"
    )
    payslip_count = fields.Integer(
        compute='_compute_payslip_count',
        string="Payslip Computation Details",
        help="Set Payslip Count"
    )

    # Attendance and working days extension fields
    employee_wage = fields.Float(
        compute="_compute_employee_wage",
        string="Employee Monthly Wage",
        readonly=True
    )
    net_wage = fields.Float(
        string="Net Wage",
        compute="_compute_net_wage",
        store=True
    )
    micra_month_working_days = fields.Float(
        string="Month Working Days",
        compute="_compute_micra_worked_day_stats"
    )
    micra_employee_worked_days = fields.Float(
        string="Employee Worked Days",
        compute="_compute_micra_worked_day_stats"
    )
    paid_leave_days = fields.Float(
        string="Paid Leave Days",
        compute="_compute_micra_worked_day_stats"
    )
    unpaid_leave_days = fields.Float(
        string="Unpaid Leave Days",
        compute="_compute_micra_worked_day_stats"
    )
    micra_salary_payable_days = fields.Float(
        string="Salary Payable Days",
        compute="_compute_micra_worked_day_stats"
    )
    micra_salary_payable_hours = fields.Float(
        string="Salary Payable Hours",
        compute="_compute_micra_worked_day_stats"
    )
    manual_days_override = fields.Boolean(
        string="Manual Work Days Override",
        help="Check this to manually edit worked days without them being recalculated automatically.",
        default=False
    )
    manual_paid_leaves = fields.Float(
        string="Manual Paid Leaves Adjustment",
        help="Adjust paid leaves for this payslip period.",
        default=0.0
    )
    extra_bonus = fields.Float(
        string="Extra Bonus",
        default=0.0,
        help="One-time bonus amount to be added to the net salary for this payslip period. Only editable by Payroll Manager."
    )

    @api.depends('employee_id', 'contract_id')
    def _compute_employee_wage(self):
        for slip in self:
            wage = 0.0
            if slip.contract_id and 'wage' in slip.contract_id._fields and slip.contract_id.wage:
                wage = slip.contract_id.wage
            elif slip.contract_id and hasattr(slip.contract_id, 'contract_template_id') and slip.contract_id.contract_template_id and slip.contract_id.contract_template_id.wage:
                wage = slip.contract_id.contract_template_id.wage
            elif slip.employee_id and 'wage' in slip.employee_id._fields and slip.employee_id.wage:
                wage = slip.employee_id.wage
            slip.employee_wage = wage

    @api.depends('line_ids.total', 'extra_bonus')
    def _compute_net_wage(self):
        for slip in self:
            net_line = slip.line_ids.filtered(lambda l: l.code == 'NET')
            slip.net_wage = sum(net_line.mapped('total'))

    def _is_working_day(self, current_date):
        current_date = fields.Date.to_date(current_date)
        config = self.env['hr.working.days.config'].search([
            ('year', '=', current_date.year),
            ('month', '=', str(current_date.month)),
            ('company_ids', '=', self.company_id.id or self.env.company.id),
        ], limit=1)
        if config:
            return config.is_calendar_date_working(current_date)
        return current_date.weekday() < 6

    @api.depends('worked_days_line_ids.number_of_days', 'worked_days_line_ids.number_of_hours',
                 'worked_days_line_ids.code', 'manual_days_override', 'manual_paid_leaves',
                 'employee_id', 'date_from', 'date_to')
    def _compute_micra_worked_day_stats(self):
        for slip in self:
            db_stats = {'working_days': 0.0, 'attended_days': 0.0, 'paid_leave_days': 0.0, 'unpaid_leave_days': 0.0,
                        'global_days': 0.0, 'global_hours': 0.0}
            if slip.employee_id and slip.date_from and slip.date_to:
                db_stats = slip._get_micra_month_stats(
                    slip.employee_id,
                    slip.contract_id,
                    slip.date_from,
                    slip.date_to,
                )

            if slip.manual_days_override:
                work_days_line = slip.worked_days_line_ids.filtered(lambda l: l.code == 'WORK_DAYS_MONTH')
                global_line = slip.worked_days_line_ids.filtered(lambda l: l.code == 'GLOBAL')

                slip.micra_month_working_days = sum(work_days_line.mapped('number_of_days'))
                slip.micra_salary_payable_days = sum(global_line.mapped('number_of_days'))
                slip.micra_salary_payable_hours = sum(global_line.mapped('number_of_hours'))

                slip.paid_leave_days = db_stats['paid_leave_days']
                slip.unpaid_leave_days = db_stats['unpaid_leave_days']
                slip.micra_employee_worked_days = max(0.0, slip.micra_salary_payable_days - slip.paid_leave_days)
            else:
                slip.micra_month_working_days = db_stats['working_days']
                slip.micra_employee_worked_days = db_stats['attended_days']
                slip.paid_leave_days = db_stats['paid_leave_days']
                slip.unpaid_leave_days = db_stats['unpaid_leave_days']
                slip.micra_salary_payable_days = db_stats['global_days']
                slip.micra_salary_payable_hours = db_stats['global_hours']

    def _get_configured_working_days_in_period(self, date_from, date_to):
        date_from = fields.Date.to_date(date_from)
        date_to = fields.Date.to_date(date_to)
        if (
                date_from and date_to and
                date_from.day == 1 and
                date_from.year == date_to.year and
                date_from.month == date_to.month
        ):
            month_last_day = calendar.monthrange(date_from.year, date_from.month)[1]
            if date_to.day == month_last_day:
                config = self.env['hr.working.days.config'].search([
                    ('year', '=', date_from.year),
                    ('month', '=', str(date_from.month)),
                    ('company_ids', '=', self.company_id.id or self.env.company.id),
                ], limit=1)
                if config:
                    return config.working_days

        config_cache = {}
        working_days = 0
        current_date = date_from

        while current_date <= date_to:
            key = (current_date.year, current_date.month)
            if key not in config_cache:
                config = self.env['hr.working.days.config'].search([
                    ('year', '=', current_date.year),
                    ('month', '=', str(current_date.month)),
                    ('company_ids', '=', self.company_id.id or self.env.company.id),
                ], limit=1)
                config_cache[key] = config
            config = config_cache[key]

            if config:
                if config.is_calendar_date_working(current_date):
                    working_days += 1
            elif current_date.weekday() < 6:
                working_days += 1

            current_date += timedelta(days=1)

        return working_days

    def _get_attendance_utc_bounds(self, date_from, date_to):
        date_from = fields.Date.to_date(date_from)
        date_to = fields.Date.to_date(date_to)
        user_tz = self.env.user.tz or 'UTC'
        try:
            tz = pytz.timezone(user_tz)
        except Exception:
            tz = pytz.UTC
        start_local = tz.localize(datetime.combine(date_from, time.min))
        end_local = tz.localize(
            datetime.combine(date_to + timedelta(days=1), time.min))
        return (
            start_local.astimezone(pytz.utc).replace(tzinfo=None),
            end_local.astimezone(pytz.utc).replace(tzinfo=None),
        )

    def _get_micra_month_stats(self, employee, contract, date_from, date_to):
        date_from = fields.Date.to_date(date_from)
        date_to = fields.Date.to_date(date_to)
        start_utc, end_utc = self._get_attendance_utc_bounds(date_from, date_to)

        attendances = self.env['hr.attendance'].sudo().search([
            ('employee_id', '=', employee.id),
            ('check_in', '>=', fields.Datetime.to_string(start_utc)),
            ('check_in', '<', fields.Datetime.to_string(end_utc)),
        ])

        attended_dates = set()
        user_tz = employee.tz or employee.resource_calendar_id.tz or self.env.user.tz or 'Asia/Calcutta'
        emp_tz = self.with_context(tz=user_tz)

        for att in attendances:
            if att.check_in:
                local_dt = fields.Datetime.context_timestamp(emp_tz, att.check_in)
                day = local_dt.date()
                if date_from <= day <= date_to:
                    attended_dates.add(day)

        leaves = self.env['hr.leave'].sudo().search([
            ('employee_id', '=', employee.id),
            ('state', '=', 'validate'),
            ('request_date_from', '<=', date_to),
            ('request_date_to', '>=', date_from),
        ])

        paid_leave_dict = {}
        unpaid_leave_dict = {}
        for leave in leaves:
            all_leave_dates = leave._micra_get_leave_dates() if hasattr(leave, '_micra_get_leave_dates') else []
            if not all_leave_dates:
                current = max(leave.request_date_from, date_from)
                limit = min(leave.request_date_to, date_to)
                while current <= limit:
                    all_leave_dates.append(current)
                    current += timedelta(days=1)

            working_leave_dates = [d for d in all_leave_dates if self._is_working_day(d)]
            total_duration = leave.number_of_days
            duration_per_date = total_duration / float(len(working_leave_dates)) if working_leave_dates else 1.0

            for d in working_leave_dates:
                if date_from <= d <= date_to:
                    if leave.holiday_status_id.unpaid:
                        unpaid_leave_dict[d] = unpaid_leave_dict.get(d, 0.0) + duration_per_date
                    else:
                        paid_leave_dict[d] = paid_leave_dict.get(d, 0.0) + duration_per_date

        attended_days = 0.0
        for d in attended_dates:
            unpaid_dur = unpaid_leave_dict.get(d, 0.0)
            paid_dur = paid_leave_dict.get(d, 0.0)
            day_weight = max(0.0, 1.0 - unpaid_dur - paid_dur)
            attended_days += day_weight

        paid_leave_days = sum(paid_leave_dict.values())
        unpaid_leave_days = sum(unpaid_leave_dict.values())

        # Adjust with manual paid leaves adjustment
        paid_leave_days += self.manual_paid_leaves

        global_days = attended_days + paid_leave_days
        global_days = max(global_days, 0.0)
        global_hours = global_days * 8.0
        contract_id = contract.id if contract else False

        working_days_in_period = self._get_configured_working_days_in_period(date_from, date_to)
        if not working_days_in_period:
            working_days_in_period = self.env.company.working_days_in_month or 23

        return {
            'working_days': float(working_days_in_period),
            'attended_days': attended_days,
            'paid_leave_days': paid_leave_days,
            'unpaid_leave_days': unpaid_leave_days,
            'global_days': global_days,
            'global_hours': global_hours,
            'contract_id': contract_id,
        }

    def _get_micra_worked_day_lines(self, employee, contract, date_from, date_to):
        stats = self._get_micra_month_stats(employee, contract, date_from, date_to)
        return [
            {
                'name': _('Total Working Days in Month'),
                'sequence': 1,
                'code': 'WORK_DAYS_MONTH',
                'number_of_days': stats['working_days'],
                'number_of_hours': stats['working_days'] * 8.0,
                'contract_id': stats['contract_id'],
            },
            {
                'name': _('Salary Payable Days (Attendance + Paid Leave)'),
                'sequence': 2,
                'code': 'GLOBAL',
                'number_of_days': stats['global_days'],
                'number_of_hours': stats['global_hours'],
                'contract_id': stats['contract_id'],
            },
        ]

    def action_prepare_micra_worked_days(self):
        for payslip in self:
            if not payslip.employee_id or not payslip.contract_id or not payslip.date_from or not payslip.date_to:
                continue

            if not payslip.struct_id:
                struct = (
                    payslip.contract_id.struct_id
                    or payslip.contract_id.contract_template_id.struct_id
                    or self.env.ref('micra_payroll.structure_base', raise_if_not_found=False)
                )
                if struct:
                    payslip.sudo().write({'struct_id': struct.id})

            vals_to_write = {
                'line_ids': [(5, 0, 0)],
                'state': 'draft',
            }
            if not payslip.manual_days_override:
                worked_day_vals = payslip._get_micra_worked_day_lines(
                    payslip.employee_id,
                    payslip.contract_id,
                    payslip.date_from,
                    payslip.date_to,
                )
                vals_to_write['worked_days_line_ids'] = [(5, 0, 0)] + [(0, 0, vals) for vals in worked_day_vals]

            payslip.write(vals_to_write)
        return True

    def get_employee_leave_calendar_data(self, year=False, month=False):
        self.ensure_one()
        date_from = fields.Date.to_date(self.date_from)
        year = int(year or (date_from.year if date_from else fields.Date.today().year))
        month = int(month or (date_from.month if date_from else fields.Date.today().month))
        month_start = fields.Date.to_date('%04d-%02d-01' % (year, month))
        month_end = fields.Date.to_date('%04d-%02d-%02d' % (
            year, month, calendar.monthrange(year, month)[1]))

        leaves = self.env['hr.leave'].search([
            ('employee_id', '=', self.employee_id.id),
            ('state', 'not in', ['cancel', 'refuse']),
            ('request_date_from', '<=', month_end),
            ('request_date_to', '>=', month_start),
        ], order='request_date_from, id')

        leaves_by_date = {}
        for leave in leaves:
            all_leave_dates = leave._micra_get_leave_dates(month_start, month_end)
            for leave_date in all_leave_dates:
                date_key = fields.Date.to_string(leave_date)
                leaves_by_date.setdefault(date_key, []).append({
                    'id': leave.id,
                    'name': leave.display_name,
                    'type': leave.holiday_status_id.display_name,
                    'state': leave.state,
                    'date_from': fields.Date.to_string(leave.request_date_from),
                    'date_to': fields.Date.to_string(leave.request_date_to),
                    'unpaid': bool(leave.holiday_status_id.unpaid),
                })

        return {
            'year': year,
            'month': month,
            'employee_name': self.employee_id.name or '',
            'display_name': '%s %s' % (calendar.month_name[month], year),
            'leaves_by_date': leaves_by_date,
            'can_edit': self.env.user.has_group('hr_holidays.group_hr_holidays_user'),
        }

    def _compute_details_by_salary_rule_category_ids(self):
        """Compute function for Salary Rule Category for getting all Categories"""
        for payslip in self:
            payslip.details_by_salary_rule_category_ids = payslip.mapped(
                'line_ids').filtered(lambda line: line.category_id)

    def _compute_payslip_count(self):
        """Compute function for getting Total count of Payslips"""
        for payslip in self:
            payslip.payslip_count = len(payslip.line_ids)

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        if any(self.filtered(
                lambda payslip: payslip.date_from > payslip.date_to)):
            raise ValidationError(
                _("Payslip 'Date From' must be earlier 'Date To'."))

    def action_payslip_draft(self):
        return self.write({'state': 'draft'})

    def action_payslip_done(self):
        self.action_compute_sheet()
        return self.write({'state': 'done'})

    def action_payslip_cancel(self):
        return self.write({'state': 'cancel'})

    def action_refund_sheet(self):
        """Function for refund the Payslip sheet"""
        for payslip in self:
            copied_payslip = payslip.copy(
                {'credit_note': True, 'name': _('Refund: ') + payslip.name})
            copied_payslip.action_compute_sheet()
            copied_payslip.action_payslip_done()
        formview_ref = self.env.ref('micra_payroll.hr_payslip_view_form', False)
        treeview_ref = self.env.ref('micra_payroll.hr_payslip_view_tree', False)
        return {
            'name': _("Refund Payslip"),
            'view_mode': 'list, form',
            'view_id': False,
            'res_model': 'hr.payslip',
            'type': 'ir.actions.act_window',
            'target': 'current',
            'domain': "[('id', 'in', %s)]" % copied_payslip.ids,
            'views': [
                (treeview_ref and treeview_ref.id or False, 'list'),
                (formview_ref and formview_ref.id or False, 'form')],
            'context': {}
        }

    def check_done(self):
        return True

    def unlink(self):
        for payslip in self:
            if payslip.state not in ['draft', 'cancel']:
                raise UserError(
                    _('You cannot delete a payslip which is not draft or cancelled!'))
        return super(HrPayslip, self).unlink()

    def get_contract(self, employee, date_from, date_to):
        if not employee:
            return []
        clause_1 = ['&', ('date_end', '<=', date_to), ('date_end', '>=', date_from)]
        clause_2 = ['&', ('date_start', '<=', date_to), ('date_start', '>=', date_from)]
        clause_3 = ['&', ('date_start', '<=', date_from), '|', ('date_end', '=', False), ('date_end', '>=', date_to)]
        clause_final = [('employee_id', '=', employee.id), '|', '|'] + clause_1 + clause_2 + clause_3
        contracts = self.env['hr.version'].search(clause_final)
        if not contracts:
            fallback_domain = [
                ('employee_id', '=', employee.id),
                '|', ('date_version', '<=', date_to), ('date_version', '=', False),
            ]
            contracts = self.env['hr.version'].search(fallback_domain, order='date_version desc, id desc')
        if not contracts and getattr(employee, 'version_id', False):
            contracts = employee.version_id
        if not contracts and getattr(employee, 'current_version_id', False):
            contracts = employee.current_version_id
        if not contracts:
            contracts = self.env['hr.version'].search([('employee_id', '=', employee.id)], order='id desc')
        return contracts.ids

    def action_compute_sheet(self):
        """Function to compute Payslip sheet"""
        for payslip in self:
            number = payslip.number or self.env['ir.sequence'].next_by_code('salary.slip')

            # Respect the structure selected by the user on the payslip
            if not payslip.struct_id:
                struct = (
                    payslip.contract_id.struct_id
                    or payslip.contract_id.contract_template_id.struct_id
                    or self.env.ref('micra_payroll.structure_base', raise_if_not_found=False)
                )
                if struct:
                    payslip.sudo().write({'struct_id': struct.id})

            # Ensure contract has struct_id aligned with payslip.struct_id
            if payslip.contract_id and payslip.struct_id and payslip.contract_id.struct_id != payslip.struct_id:
                payslip.contract_id.sudo().write({'struct_id': payslip.struct_id.id})

            # Calculate attendance & worked days lines
            if not payslip.manual_days_override:
                worked_day_vals = payslip._get_micra_worked_day_lines(
                    payslip.employee_id,
                    payslip.contract_id,
                    payslip.date_from,
                    payslip.date_to,
                )
                payslip.write({
                    'worked_days_line_ids': [(5, 0, 0)] + [(0, 0, vals) for vals in worked_day_vals],
                })

            # delete old payslip lines
            payslip.line_ids.unlink()

            contract_ids = payslip.contract_id.ids or \
                           self.get_contract(payslip.employee_id,
                                             payslip.date_from, payslip.date_to)
            lines = [(0, 0, line) for line in
                     self._get_payslip_lines(contract_ids, payslip.id)]
            vals = {'line_ids': lines, 'number': number}
            if lines:
                vals['state'] = 'verify'
            payslip.write(vals)
        return True

    @api.model
    def get_worked_day_lines(self, contracts, date_from, date_to):
        """Calculate worked days based on monthly config, public holidays, attendance and leaves"""
        contracts = self.env['hr.version'].browse(contracts.ids if hasattr(contracts, 'ids') else contracts)
        if contracts:
            contract = contracts[0]
            return self._get_micra_worked_day_lines(contract.employee_id, contract, date_from, date_to)
        return []

    @api.model
    def get_inputs(self, contracts, date_from, date_to):
        """Function for getting contracts upon date_from and date_to fields"""
        res = []
        structure_ids = contracts.get_all_structures()
        rule_ids = self.env['hr.payroll.structure'].browse(
            structure_ids).get_all_rules()
        sorted_rule_ids = [id for id, sequence in
                           sorted(rule_ids, key=lambda x: x[1])]
        seen_rule_ids = set()
        unique_rule_ids = []
        for r_id in sorted_rule_ids:
            if r_id not in seen_rule_ids:
                seen_rule_ids.add(r_id)
                unique_rule_ids.append(r_id)
        inputs = self.env['hr.salary.rule'].browse(unique_rule_ids).mapped(
            'input_ids')
        for contract in contracts:
            for input in inputs:
                input_data = {
                    'name': input.name,
                    'code': input.code,
                    'contract_id': contract.id,
                    'date_from': date_from,
                    'date_to': date_to,
                }
                res.append(input_data)
        return res

    @api.model
    def _get_payslip_lines(self, contract_ids, payslip_id):
        """Function for getting Payslip Lines"""

        def _sum_salary_rule_category(localdict, category, amount):
            if category.parent_id:
                localdict = _sum_salary_rule_category(localdict,
                                                      category.parent_id,
                                                      amount)
            localdict['categories'].dict[category.code] \
                = category.code in localdict[
                'categories'].dict and localdict['categories'].dict[
                      category.code] + amount or amount
            return localdict

        class BrowsableObject(object):
            def __init__(self, employee_id, dict, env):
                self.employee_id = employee_id
                self.dict = dict
                self.env = env

            def __getattr__(self, attr):
                return attr in self.dict and self.dict.__getitem__(attr) or 0.0

        class InputLine(BrowsableObject):
            def __init__(self, employee_id, dict, env):
                self.employee_id = employee_id
                self.dict = dict
                self.env = env

            def __getattr__(self, attr):
                return attr in self.dict and self.dict.__getitem__(attr) or 0.0

            def __getitem__(self, item):
                return item in self.dict and self.dict.__getitem__(item) or 0.0

        class WorkedDays(BrowsableObject):
            def _sum(self, code, field='number_of_days'):
                return sum(line[field] for line in self.dict.values() if line.code == code)

            def __getattr__(self, attr):
                return attr in self.dict and self.dict.__getitem__(attr) or 0.0

        class Payslips(BrowsableObject):
            def __getattr__(self, attr):
                return attr in self.dict and self.dict.__getitem__(attr) or 0.0

        result_dict = {}
        rules_dict = {}
        worked_days_dict = {}
        inputs_dict = {}
        blacklist = []
        payslip = self.env['hr.payslip'].browse(payslip_id)
        for worked_days_line in payslip.worked_days_line_ids:
            worked_days_dict[worked_days_line.code] = worked_days_line
        for input_line in payslip.input_line_ids:
            inputs_dict[input_line.code] = input_line

        categories = BrowsableObject(payslip.employee_id.id, {}, self.env)
        inputs = InputLine(payslip.employee_id.id, inputs_dict, self.env)
        worked_days = WorkedDays(payslip.employee_id.id, worked_days_dict,
                                 self.env)
        payslips = Payslips(payslip.employee_id.id, payslip, self.env)
        rules = BrowsableObject(payslip.employee_id.id, rules_dict, self.env)

        baselocaldict = {
            'categories': categories,
            'rules': rules,
            'payslip': payslips,
            'worked_days': worked_days,
            'inputs': inputs,
            'hasattr': hasattr,
            'getattr': getattr,
            'bool': bool,
            'float': float,
            'int': int,
            'round': round,
            'max': max,
            'min': min,
            'abs': abs,
        }
        contracts = self.env['hr.version'].browse(contract_ids)
        if len(contracts) == 1 and payslip.struct_id:
            structure_ids = list(
                set(payslip.struct_id._get_parent_structure().ids))
        else:
            structure_ids = contracts.get_all_structures()
        rule_ids = self.env['hr.payroll.structure'].browse(
            structure_ids).get_all_rules()
        sorted_rule_ids = [id for id, sequence in
                           sorted(rule_ids, key=lambda x: x[1])]
        seen_rule_ids = set()
        unique_rule_ids = []
        for r_id in sorted_rule_ids:
            if r_id not in seen_rule_ids:
                seen_rule_ids.add(r_id)
                unique_rule_ids.append(r_id)
        sorted_rules = self.env['hr.salary.rule'].browse(unique_rule_ids)

        for contract in contracts:
            employee = contract.employee_id
            localdict = dict(baselocaldict, employee=employee,
                             contract=contract)
            for rule in sorted_rules:
                key = rule.code + '-' + str(contract.id)
                if rule.category_id:
                    category = rule.category_id
                else:
                    category = None
                if key in blacklist:
                    continue
                if rule._satisfy_condition(localdict):
                    amount, qty, rate = rule._compute_rule(localdict)
                    tot_rule = amount * qty * rate / 100.0
                    if category:
                        localdict = _sum_salary_rule_category(localdict,
                                                              category,
                                                              tot_rule)
                    rules_dict[rule.code] = rule
                    result_dict[key] = {
                        'salary_rule_id': rule.id,
                        'contract_id': contract.id,
                        'name': rule.name,
                        'code': rule.code,
                        'category_id': rule.category_id.id,
                        'sequence': rule.sequence,
                        'condition_select': rule.condition_select,
                        'condition_python': rule.condition_python,
                        'condition_range': rule.condition_range,
                        'condition_range_min': rule.condition_range_min,
                        'condition_range_max': rule.condition_range_max,
                        'amount_select': rule.amount_select,
                        'amount_fix': rule.amount_fix,
                        'amount_python_compute': rule.amount_python_compute,
                        'amount_percentage': rule.amount_percentage,
                        'amount_percentage_base': rule.amount_percentage_base,
                        'register_id': rule.register_id.id,
                        'amount': amount,
                        'employee_id': contract.employee_id.id,
                        'quantity': qty,
                        'rate': rate,
                        'total': tot_rule,
                    }
                else:
                    blacklist.append(key)
        return list(result_dict.values())

    def onchange_employee_id(self, date_from, date_to, employee_id=False,
                             contract_id=False):
        """Function for return worked days when changing onchange_employee_id"""
        res = {
            'value': {
                'line_ids': [],
                'input_line_ids': [(2, x,) for x in self.input_line_ids.ids],
                'worked_days_line_ids': [(2, x,) for x in
                                         self.worked_days_line_ids.ids],
                'name': '',
                'contract_id': False,
                'struct_id': False,
            }
        }
        if (not employee_id) or (not date_from) or (not date_to):
            return res
        ttyme = datetime.combine(fields.Date.from_string(date_from), time.min)
        employee = self.env['hr.employee'].browse(employee_id)
        locale = self.env.context.get('lang') or 'en_US'
        res['value'].update({
            'name': _('Salary Slip of %s for %s') % (
                employee.name, tools.ustr(
                    babel.dates.format_date(date=ttyme, format='MMMM-y',
                                            locale=locale))),
            'company_id': employee.company_id.id,
        })
        if not self.env.context.get('contract'):
            contract_ids = self.get_contract(employee, date_from, date_to)
        else:
            if contract_id:
                contract_ids = [contract_id]
            else:
                contract_ids = self.get_contract(employee, date_from, date_to)
        if not contract_ids:
            return res
        contract = self.env['hr.version'].browse(contract_ids[0])
        res['value'].update({
            'contract_id': contract.id
        })
        struct = contract.struct_id or contract.contract_template_id.struct_id or self.env.ref('micra_payroll.structure_base', raise_if_not_found=False)
        if not struct:
            return res
        res['value'].update({
            'struct_id': struct.id,
        })
        contracts = self.env['hr.version'].browse(contract_ids)
        worked_days_line_ids = self.get_worked_day_lines(contracts, date_from, date_to)
        input_line_ids = self.get_inputs(contracts, date_from, date_to)
        res['value'].update({
            'worked_days_line_ids': worked_days_line_ids,
            'input_line_ids': input_line_ids,
        })
        return res

    @api.onchange('employee_id')
    def onchange_employee(self):
        """Function for getting contract for employee"""
        if (not self.employee_id) or (not self.date_from) or (not self.date_to):
            return
        employee = self.employee_id
        date_from = self.date_from
        date_to = self.date_to
        contract_ids = []
        ttyme = datetime.combine(fields.Date.from_string(date_from), time.min)
        locale = self.env.context.get('lang') or 'en_US'
        self.name = _('Salary Slip of %s for %s') % (
            employee.name, tools.ustr(
                babel.dates.format_date(date=ttyme, format='MMMM-y',
                                        locale=locale)))
        self.company_id = employee.company_id
        if not self.env.context.get('contract') or not self.contract_id:
            contract_ids = self.get_contract(employee, date_from, date_to)
            if not contract_ids:
                return
            self.contract_id = self.env['hr.version'].browse(contract_ids[0])

        struct = (
            self.contract_id.struct_id
            or self.contract_id.contract_template_id.struct_id
            or self.env.ref('micra_payroll.structure_base', raise_if_not_found=False)
            or self.env['hr.payroll.structure'].search([], limit=1)
        )
        if struct:
            self.struct_id = struct

        if self.contract_id:
            contract_ids = self.contract_id.ids
        contracts = self.env['hr.version'].browse(contract_ids)
        worked_days_line_ids = self.get_worked_day_lines(contracts, date_from, date_to)
        worked_days_lines = self.worked_days_line_ids.browse([])
        for r in worked_days_line_ids:
            worked_days_lines += worked_days_lines.new(r)
        self.worked_days_line_ids = worked_days_lines

        input_line_ids = self.get_inputs(contracts, date_from, date_to)
        input_lines = self.input_line_ids.browse([])
        for r in input_line_ids:
            input_lines += input_lines.new(r)
        self.input_line_ids = input_lines

    @api.onchange('contract_id')
    def onchange_contract_id(self):
        """Function for getting structure when changing contract"""
        if not self.contract_id:
            self.struct_id = False
        self.with_context(contract=True).onchange_employee()

    def get_salary_line_total(self, code):
        """Function for getting total salary line"""
        self.ensure_one()
        line = self.line_ids.filtered(lambda line: line.code == code)
        if line:
            return line[0].total
        return 0.0

    @api.onchange('date_from')
    def onchange_date_from(self):
        date_from = self.date_from
        date_to = self.date_to
        contract_ids = []
        if self.contract_id:
            contract_ids = self.contract_id.ids
        contracts = self.env['hr.version'].browse(contract_ids)
        worked_days_line_ids = self.get_worked_day_lines(contracts, date_from, date_to)
        worked_days_lines = self.worked_days_line_ids.browse([])
        for r in worked_days_line_ids:
            worked_days_lines += worked_days_lines.new(r)
        self.worked_days_line_ids = worked_days_lines
        input_line_ids = self.get_inputs(contracts, date_from, date_to)
        input_lines = self.input_line_ids.browse([])
        for r in input_line_ids:
            input_lines += input_lines.new(r)
        self.input_line_ids = input_lines

    @api.onchange('date_to')
    def onchange_date_to(self):
        if (not self.employee_id) or (not self.date_from) or (not self.date_to):
            return
        date_from = self.date_from
        date_to = self.date_to
        contract_ids = []
        if self.contract_id:
            contract_ids = self.contract_id.ids
        contracts = self.env['hr.version'].browse(contract_ids)
        worked_days_line_ids = self.get_worked_day_lines(contracts, date_from, date_to)
        worked_days_lines = self.worked_days_line_ids.browse([])
        for r in worked_days_line_ids:
            worked_days_lines += worked_days_lines.new(r)
        self.worked_days_line_ids = worked_days_lines
        input_line_ids = self.get_inputs(contracts, date_from, date_to)
        input_lines = self.input_line_ids.browse([])
        for r in input_line_ids:
            input_lines += input_lines.new(r)
        self.input_line_ids = input_lines

    def get_payslip_earnings(self):
        """Return list of earnings lines (excluding gross, net, deductions)."""
        self.ensure_one()
        return self.line_ids.filtered(
            lambda l: l.appears_on_payslip and l.code not in ('GROSS', 'NET') and l.category_id.code != 'DED'
        )

    def get_payslip_deductions(self):
        """Return list of deduction lines."""
        self.ensure_one()
        return self.line_ids.filtered(
            lambda l: l.appears_on_payslip and (l.category_id.code == 'DED' or l.code == 'UNPAID')
        )

    def get_total_earnings(self):
        """Return gross earnings total."""
        self.ensure_one()
        gross = self.line_ids.filtered(lambda l: l.code == 'GROSS')
        if gross:
            return sum(gross.mapped('total'))
        earnings = self.get_payslip_earnings()
        return sum(earnings.mapped('total'))

    def get_total_deductions(self):
        """Return total deductions amount."""
        self.ensure_one()
        deductions = self.get_payslip_deductions()
        return sum(deductions.mapped('total'))

    def get_net_payable(self):
        """Return net payable salary."""
        self.ensure_one()
        net = self.line_ids.filtered(lambda l: l.code == 'NET')
        if net:
            return net[0].total
        return self.net_wage or 0.0

    def get_net_payable_words(self):
        """Return net payable amount in words."""
        self.ensure_one()
        amount = self.get_net_payable()
        if self.company_id and self.company_id.currency_id:
            try:
                return self.company_id.currency_id.amount_to_text(amount)
            except Exception:
                pass
        return f"{amount:.2f}"

    def get_payslip_paired_rows(self):
        """Return aligned list of dict pairs for side-by-side earnings and deductions:
           [{'earning_name': ..., 'earning_amount': ..., 'deduction_name': ..., 'deduction_amount': ...}, ...]
        """
        self.ensure_one()
        earnings = []
        for l in self.get_payslip_earnings():
            earnings.append({'name': l.name, 'amount': l.total})
        if self.extra_bonus and self.extra_bonus > 0:
            earnings.append({'name': 'Extra Bonus', 'amount': self.extra_bonus})

        deductions = []
        for l in self.get_payslip_deductions():
            deductions.append({'name': l.name, 'amount': abs(l.total)})

        max_rows = max(len(earnings), len(deductions), 1)
        paired = []
        for i in range(max_rows):
            e_item = earnings[i] if i < len(earnings) else None
            d_item = deductions[i] if i < len(deductions) else None

            d_name = ''
            d_amount = None
            if d_item:
                d_name = d_item['name']
                d_amount = d_item['amount']
            elif i == 0 and not deductions:
                d_name = 'No Deductions'
                d_amount = 0.0

            paired.append({
                'earning_name': e_item['name'] if e_item else '',
                'earning_amount': e_item['amount'] if e_item else None,
                'deduction_name': d_name,
                'deduction_amount': d_amount,
            })
        return paired


