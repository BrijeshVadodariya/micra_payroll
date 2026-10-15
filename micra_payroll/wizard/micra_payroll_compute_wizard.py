# -*- coding: utf-8 -*-
import calendar
import datetime
from odoo import fields, models, api, _
from odoo.exceptions import UserError

MONTH_SELECTION = [
    ('1', 'January'), ('2', 'February'), ('3', 'March'),
    ('4', 'April'), ('5', 'May'), ('6', 'June'),
    ('7', 'July'), ('8', 'August'), ('9', 'September'),
    ('10', 'October'), ('11', 'November'), ('12', 'December'),
]


class MicraPayrollComputeWizard(models.TransientModel):
    _name = 'micra.payroll.compute.wizard'
    _description = 'Compute Salary for All Employees'

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company.id
    )
    compute_type = fields.Selection([
        ('month', 'Whole Month'),
        ('date_range', 'Date Period'),
    ], string='Compute By', required=True, default='month')
    year = fields.Integer(
        string='Year',
        default=lambda self: fields.Date.context_today(self).year,
    )
    month = fields.Selection(
        MONTH_SELECTION,
        string='Month',
        default=lambda self: str(fields.Date.context_today(self).month),
    )
    date_from = fields.Date(string='Date From')
    date_to = fields.Date(string='Date To')
    working_days_config_id = fields.Many2one(
        'hr.working.days.config',
        string='Working Days Configuration',
        readonly=True,
    )
    working_days = fields.Integer(
        string='Working Days',
        readonly=True,
    )
    public_holiday_count = fields.Integer(
        string='Public Holidays',
        readonly=True,
    )
    public_holiday_line_ids = fields.Many2many(
        'hr.working.days.config.holiday',
        'hr_payroll_wiz_holiday_rel',
        'wizard_id',
        'holiday_id',
        string='Public Holidays',
        readonly=True,
    )

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        today = fields.Date.context_today(self)
        values.setdefault('compute_type', 'month')
        values.setdefault('year', today.year)
        values.setdefault('month', str(today.month))
        values.setdefault('date_from', today.replace(day=1))
        last_day = calendar.monthrange(today.year, today.month)[1]
        values.setdefault('date_to', today.replace(day=last_day))
        values.update(self._compute_period_info(
            compute_type=values.get('compute_type', 'month'),
            year=values.get('year', today.year),
            month=values.get('month', str(today.month)),
            date_from=values.get('date_from'),
            date_to=values.get('date_to'),
        ))
        return values

    def _get_month_period(self, year, month):
        if not year or not month:
            return False, False
        month = int(month)
        date_from = datetime.date(int(year), month, 1)
        date_to = datetime.date(int(year), month, calendar.monthrange(int(year), month)[1])
        return date_from, date_to

    def _get_working_days_config(self, year=False, month=False):
        year = year if year is not False else self.year
        month = month if month is not False else self.month
        if not year or not month:
            return self.env['hr.working.days.config']
        return self.env['hr.working.days.config'].search([
            ('year', '=', int(year)),
            ('month', '=', str(month)),
            ('company_ids', '=', self.company_id.id),
        ], limit=1)

    def _get_fallback_working_days_count(self, date_from, date_to):
        date_from = fields.Date.to_date(date_from)
        date_to = fields.Date.to_date(date_to)
        if not date_from or not date_to:
            return 0
        working_days = 0
        current_date = date_from
        while current_date <= date_to:
            weekday = current_date.weekday()
            if weekday < 6:
                working_days += 1
            current_date += datetime.timedelta(days=1)
        return working_days

    def _get_holidays_for_period(self, date_from, date_to):
        date_from = fields.Date.to_date(date_from)
        date_to = fields.Date.to_date(date_to)
        if not date_from or not date_to:
            return self.env['hr.working.days.config.holiday']
        return self.env['hr.working.days.config.holiday'].search([
            ('date_from', '<=', date_to),
            ('date_to', '>=', date_from),
            ('config_id.company_ids', '=', self.company_id.id),
        ])

    def _get_working_days_for_period(self, date_from, date_to):
        date_from = fields.Date.to_date(date_from)
        date_to = fields.Date.to_date(date_to)
        if not date_from or not date_to:
            return 0
        
        start_month = date_from.month
        start_year = date_from.year
        end_month = date_to.month
        end_year = date_to.year
        
        domain = []
        if start_year == end_year:
            domain = [('year', '=', start_year), ('month', '>=', str(start_month)), ('month', '<=', str(end_month))]
        else:
            domain = [
                '|',
                '&', ('year', '=', start_year), ('month', '>=', str(start_month)),
                '|',
                '&', ('year', '=', end_year), ('month', '<=', str(end_month)),
                '&', ('year', '>', start_year), ('year', '<', end_year)
            ]
        
        domain.append(('company_ids', '=', self.company_id.id))
        configs = self.env['hr.working.days.config'].search(domain)
        config_map = {(c.year, int(c.month)): c for c in configs}
        
        working_days = 0
        current = date_from
        while current <= date_to:
            key = (current.year, current.month)
            config = config_map.get(key)
            if config:
                if config.is_calendar_date_working(current):
                    working_days += 1
            else:
                weekday = current.weekday()
                if weekday < 6:
                    working_days += 1
            current += datetime.timedelta(days=1)
        return working_days

    def _compute_period_info(self, compute_type, year, month, date_from, date_to):
        if compute_type == 'month':
            df, dt = self._get_month_period(year, month)
            config = self._get_working_days_config(year, month)
            if config:
                working_days = config.working_days
                holiday_lines = config.holiday_line_ids
            elif df and dt:
                working_days = self._get_fallback_working_days_count(df, dt)
                holiday_lines = self.env['hr.working.days.config.holiday']
            else:
                working_days = 0
                holiday_lines = self.env['hr.working.days.config.holiday']
            return {
                'date_from': df,
                'date_to': dt,
                'working_days_config_id': config.id if config else False,
                'working_days': working_days,
                'public_holiday_count': len(holiday_lines),
                'public_holiday_line_ids': [(6, 0, holiday_lines.ids)],
            }
        else:
            df = fields.Date.to_date(date_from)
            dt = fields.Date.to_date(date_to)
            if not df or not dt or df > dt:
                return {
                    'working_days_config_id': False,
                    'working_days': 0,
                    'public_holiday_count': 0,
                    'public_holiday_line_ids': [(6, 0, [])],
                }
            working_days = self._get_working_days_for_period(df, dt)
            holiday_lines = self._get_holidays_for_period(df, dt)
            config = False
            if df.year == dt.year and df.month == dt.month:
                config = self._get_working_days_config(df.year, str(df.month))
            return {
                'working_days_config_id': config.id if config else False,
                'working_days': working_days,
                'public_holiday_count': len(holiday_lines),
                'public_holiday_line_ids': [(6, 0, holiday_lines.ids)],
            }

    @api.onchange('compute_type', 'year', 'month', 'date_from', 'date_to')
    def _onchange_period_fields(self):
        for wizard in self:
            if wizard.compute_type == 'month':
                df, dt = wizard._get_month_period(wizard.year, wizard.month)
                if df:
                    wizard.date_from = df
                if dt:
                    wizard.date_to = dt
            info = wizard._compute_period_info(
                wizard.compute_type,
                wizard.year,
                wizard.month,
                wizard.date_from,
                wizard.date_to,
            )
            wizard.working_days_config_id = info['working_days_config_id']
            wizard.working_days = info['working_days']
            wizard.public_holiday_count = info['public_holiday_count']
            wizard.public_holiday_line_ids = info['public_holiday_line_ids']

    def action_compute_salary(self):
        self.ensure_one()

        if self.compute_type == 'month':
            if not self.year or not self.month:
                raise UserError(_("Please select a Year and Month."))
            date_from, date_to = self._get_month_period(self.year, self.month)
            config = self._get_working_days_config(self.year, self.month)
            if not config:
                raise UserError(_(
                    "Please create a Working Days Configuration for %s %s before computing salary."
                ) % (dict(MONTH_SELECTION).get(self.month, ''), self.year))
            config._sync_public_holidays_for_month()
            working_days = config.working_days
            period_label = date_from.strftime('%B %Y')
        else:
            date_from = fields.Date.to_date(self.date_from)
            date_to = fields.Date.to_date(self.date_to)
            if not date_from or not date_to:
                raise UserError(_("Please select a valid Date From and Date To."))
            if date_from > date_to:
                raise UserError(_("Date From must be before Date To."))
            working_days = self._get_working_days_for_period(date_from, date_to)
            period_label = '%s – %s' % (
                date_from.strftime('%d %b %Y'), date_to.strftime('%d %b %Y'))

        self.date_from = date_from
        self.date_to = date_to
        self.working_days = working_days
        self.env.company.working_days_in_month = working_days

        active_ids = self._context.get('active_ids')
        if active_ids:
            employees = self.env['hr.employee'].browse(active_ids).exists()
        else:
            employees = self.env['hr.employee'].search([])

        if not employees:
            raise UserError(_("No employees found to process."))

        payslips = self.env['hr.payslip']
        for employee in employees:
            existing_slip = self.env['hr.payslip'].search([
                ('employee_id', '=', employee.id),
                ('date_from', '=', date_from),
                ('date_to', '=', date_to),
                ('state', 'in', ['draft', 'verify']),
            ], limit=1)
            if existing_slip:
                existing_slip.action_prepare_micra_worked_days()
                payslips |= existing_slip
                continue

            if self.env['hr.payslip'].search_count([
                ('employee_id', '=', employee.id),
                ('date_from', '=', date_from),
                ('date_to', '=', date_to),
                ('state', '!=', 'cancel'),
            ]):
                if active_ids and len(active_ids) == 1:
                    raise UserError(_(
                        "A payslip already exists for %s in this period. "
                        "Please cancel or delete the old one first."
                    ) % employee.name)
                continue

            contract = self.env['hr.version'].search([
                ('employee_id', '=', employee.id),
            ], limit=1)
            if not contract:
                if active_ids and len(active_ids) == 1:
                    raise UserError(_(
                        "No Contract found for %s. "
                        "Please create a Contract (hr.version) first."
                    ) % employee.name)
                continue

            struct = contract.struct_id or self.env.ref('micra_payroll.structure_base').sudo()
            payslip = self.env['hr.payslip'].create({
                'employee_id': employee.id,
                'name': _('Salary Slip of %s for %s') % (employee.name, period_label),
                'date_from': date_from,
                'date_to': date_to,
                'contract_id': contract.id,
                'struct_id': struct.id,
            })
            payslips |= payslip
            payslip.action_prepare_micra_worked_days()

        if payslips:
            payslips.action_compute_sheet()

        if not payslips:
            raise UserError(_(
                "No payslips were generated. "
                "Please ensure your employees have a Contract (hr.version) "
                "created under the Payroll tab."
            ))

        action = self.env.ref('micra_payroll.hr_payslip_action').read()[0]
        action.update({
            'name': _('Draft Payslips to Review'),
            'target': 'current',
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],
            'view_id': False,
            'domain': [('date_from', '=', date_from), ('date_to', '=', date_to)],
            'context': {},
        })
        return action
