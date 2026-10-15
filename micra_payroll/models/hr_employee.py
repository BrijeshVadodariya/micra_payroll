# -*- coding: utf-8 -*-
import calendar
import datetime
import logging
import pytz
from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class HrEmployee(models.Model):
    """Inherit hr_employee for Payslip Counts, Wage, Monthly Attendance Stats, Late Attendance, Break State, and Face Recognition"""
    _inherit = 'hr.employee'

    slip_ids = fields.One2many(
        'hr.payslip',
        'employee_id',
        string='Payslips',
        readonly=True,
        help="Choose Payslip for Employee"
    )
    payslip_count = fields.Integer(
        compute='_compute_payslip_count',
        string='Payslip Count',
        help="Set Payslip Count"
    )
    wage = fields.Float(string="Monthly Wage", tracking=True)

    current_month_attended_days = fields.Float(
        string="Attended Days (This Month)",
        compute="_compute_current_month_attendance_stats"
    )
    current_month_paid_leave_days = fields.Float(
        string="Paid Leaves (This Month)",
        compute="_compute_current_month_attendance_stats"
    )
    current_month_unpaid_leave_days = fields.Float(
        string="Unpaid Leaves (This Month)",
        compute="_compute_current_month_attendance_stats"
    )
    current_month_payable_days = fields.Float(
        string="Salary Payable Days",
        compute="_compute_current_month_attendance_stats"
    )

    late_attendance_ids = fields.One2many(
        'hr.attendance', 'employee_id', 
        string="Late Attendances",
        domain=[('is_late', '=', True)]
    )
    joining_date = fields.Date(string="Joining Date")

    current_break_attendance_id = fields.Many2one(
        'hr.attendance', compute='_compute_current_break_attendance', string='Current Attendance'
    )
    current_attendance_break_state = fields.Selection([
        ('no_attendance', 'Not Checked In'),
        ('available', 'Available for Break'),
        ('on_break', 'On Break')
    ], compute='_compute_current_break_attendance', string='Break State')

    face_descriptor = fields.Text(string="Face Descriptor", help="JSON string of the 128-point face descriptor array")
    has_face_registered = fields.Boolean(string="Face Registered", compute="_compute_has_face_registered", store=True)
    registered_face_image = fields.Binary(string="Registered Face Image")
    enable_face_recognition = fields.Boolean(related='company_id.enable_face_recognition')

    @api.depends('face_descriptor')
    def _compute_has_face_registered(self):
        for employee in self:
            employee.has_face_registered = bool(employee.face_descriptor)

    def action_open_face_capture(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'micra_payroll.face_capture_client_action',
            'name': 'Capture Face for %s' % self.name,
            'params': {
                'employee_id': self.id,
                'employee_name': self.name,
            },
            'target': 'new',
        }

    def action_delete_face(self):
        self.ensure_one()
        self.write({
            'face_descriptor': False,
            'registered_face_image': False,
        })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Face Deleted',
                'message': 'Face recognition data for %s has been removed.' % self.name,
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }

    def _compute_current_break_attendance(self):
        for employee in self:
            attendance = self.env['hr.attendance'].search([
                ('employee_id', '=', employee.id),
                ('check_out', '=', False)
            ], limit=1)
            
            employee.current_break_attendance_id = attendance.id if attendance else False
            if not attendance:
                employee.current_attendance_break_state = 'no_attendance'
            elif attendance.is_on_break:
                employee.current_attendance_break_state = 'on_break'
            else:
                employee.current_attendance_break_state = 'available'

    def action_employee_break_in(self):
        self.ensure_one()
        if self.current_break_attendance_id:
            self.current_break_attendance_id.action_break_in()

    def action_employee_break_out(self):
        self.ensure_one()
        if self.current_break_attendance_id:
            self.current_break_attendance_id.action_break_out()

    def _compute_payslip_count(self):
        """Function to count Payslips"""
        payslip_data = self.env['hr.payslip'].sudo().read_group(
            [('employee_id', 'in', self.ids)],
            ['employee_id'], ['employee_id'])
        result = {}
        for data in payslip_data:
            emp_id = data['employee_id']
            if isinstance(emp_id, (list, tuple)):
                emp_id = emp_id[0]
            count = data.get('employee_id_count', data.get('__count', 0))
            result[emp_id] = count
        for employee in self:
            employee.payslip_count = result.get(employee.id, 0)

    @api.model_create_multi
    def create(self, vals_list):
        employees = super().create(vals_list)
        for emp in employees:
            if emp.wage and emp.version_id and not emp.version_id.wage:
                emp.version_id.wage = emp.wage
        return employees

    def write(self, vals):
        res = super().write(vals)
        if 'wage' in vals:
            for emp in self:
                if emp.version_id and emp.version_id.wage != vals['wage']:
                    emp.version_id.wage = vals['wage']
        return res

    def _compute_current_month_attendance_stats(self):
        today = fields.Date.context_today(self)
        start_local_date = today.replace(day=1)
        last_day = calendar.monthrange(today.year, today.month)[1]
        end_local_date = today.replace(day=last_day)

        user_tz = self.env.user.tz or 'UTC'
        try:
            tz = pytz.timezone(user_tz)
        except Exception:
            tz = pytz.UTC

        start_local_dt = tz.localize(datetime.datetime.combine(start_local_date, datetime.time.min))
        end_local_dt = tz.localize(datetime.datetime.combine(end_local_date, datetime.time.max))

        start_utc = start_local_dt.astimezone(pytz.utc).replace(tzinfo=None)
        end_utc = end_local_dt.astimezone(pytz.utc).replace(tzinfo=None)

        start_utc_str = fields.Datetime.to_string(start_utc)
        end_utc_str = fields.Datetime.to_string(end_utc)

        for emp in self:
            emp.current_month_attended_days = 0.0
            emp.current_month_paid_leave_days = 0.0
            emp.current_month_unpaid_leave_days = 0.0
            emp.current_month_payable_days = 0.0

            try:
                # Find attendances
                attendances = self.env["hr.attendance"].sudo().search([
                    ("employee_id", "=", emp.id),
                    ("check_in", ">=", start_utc_str),
                    ("check_in", "<=", end_utc_str),
                ])

                attended_dates = set()
                emp_timezone = emp.tz or emp.resource_calendar_id.tz or self.env.user.tz or 'Asia/Calcutta'
                emp_tz = self.with_context(tz=emp_timezone)

                for att in attendances:
                    if att.check_in:
                        local_in = fields.Datetime.context_timestamp(emp_tz, att.check_in)
                        d = local_in.date()
                        if start_local_date <= d <= end_local_date:
                            attended_dates.add(d)

                # Find leaves
                leaves = self.env['hr.leave'].sudo().search([
                    ('employee_id', '=', emp.id),
                    ('state', '=', 'validate'),
                    ('request_date_from', '<=', end_local_date),
                    ('request_date_to', '>=', start_local_date),
                ])

                paid_leave_dict = {}
                unpaid_leave_dict = {}
                for leave in leaves:
                    all_leave_dates = leave._micra_get_leave_dates() if hasattr(leave, '_micra_get_leave_dates') else []
                    if not all_leave_dates:
                        current = max(leave.request_date_from, start_local_date)
                        limit = min(leave.request_date_to, end_local_date)
                        while current <= limit:
                            all_leave_dates.append(current)
                            current += datetime.timedelta(days=1)

                    total_duration = leave.number_of_days
                    duration_per_date = total_duration / float(len(all_leave_dates)) if all_leave_dates else 1.0

                    for d in all_leave_dates:
                        if start_local_date <= d <= end_local_date:
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

                emp.current_month_attended_days = attended_days
                emp.current_month_paid_leave_days = paid_leave_days
                emp.current_month_unpaid_leave_days = unpaid_leave_days
                emp.current_month_payable_days = attended_days + paid_leave_days
            except Exception as e:
                _logger.error("Error in _compute_current_month_attendance_stats for emp %s: %s", emp.id, str(e), exc_info=True)


class HrEmployeePublic(models.Model):
    _inherit = 'hr.employee.public'

    wage = fields.Float(related='employee_id.wage', readonly=True)
    current_month_attended_days = fields.Float(related='employee_id.current_month_attended_days', readonly=True)
    current_month_paid_leave_days = fields.Float(related='employee_id.current_month_paid_leave_days', readonly=True)
    current_month_unpaid_leave_days = fields.Float(related='employee_id.current_month_unpaid_leave_days', readonly=True)
    current_month_payable_days = fields.Float(related='employee_id.current_month_payable_days', readonly=True)

    late_attendance_ids = fields.One2many(
        'hr.attendance', 'employee_id', 
        string="Late Attendances",
        domain=[('is_late', '=', True)]
    )
    joining_date = fields.Date(string="Joining Date")

    face_descriptor = fields.Text(readonly=True)
    has_face_registered = fields.Boolean(readonly=True)
    registered_face_image = fields.Binary(readonly=True)
