# -*- coding: utf-8 -*-
import calendar
from collections import defaultdict
import datetime
from datetime import timedelta
import logging
import pytz

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools.date_utils import sum_intervals
from odoo.tools.float_utils import float_compare
from odoo.tools.intervals import Intervals

_logger = logging.getLogger(__name__)


class HrAttendanceBreakLine(models.Model):
    _name = 'hr.attendance.break.line'
    _description = 'Attendance Break Line'

    attendance_id = fields.Many2one('hr.attendance', string='Attendance', required=True, ondelete='cascade')
    break_in = fields.Datetime(string='Break In', required=True, default=fields.Datetime.now)
    break_out = fields.Datetime(string='Break Out')
    duration = fields.Float(string='Duration (Hours)', compute='_compute_duration', store=True)
    duration_display = fields.Char(string='Duration', compute='_compute_duration', store=True)

    @api.depends('break_in', 'break_out')
    def _compute_duration(self):
        for rec in self:
            if rec.break_in and rec.break_out:
                delta = rec.break_out - rec.break_in
                rec.duration = delta.total_seconds() / 3600.0

                seconds = int(delta.total_seconds())
                h = seconds // 3600
                m = (seconds % 3600) // 60
                rec.duration_display = f"{h}h {m}m"
            else:
                rec.duration = 0.0
                rec.duration_display = "0h 0m"


class HrAttendance(models.Model):
    _inherit = 'hr.attendance'

    is_late = fields.Boolean(string="Is Late", compute="_compute_is_late", store=True)
    late_duration = fields.Float(string="Late Hours", compute="_compute_is_late", store=True)
    late_duration_display = fields.Char(string="Late Time", compute="_compute_is_late", store=True)

    break_line_ids = fields.One2many('hr.attendance.break.line', 'attendance_id', string='Breaks')
    is_on_break = fields.Boolean(string='Is On Break', compute='_compute_is_on_break', store=True)

    raw_worked_time = fields.Float(string='Raw Worked Time', compute='_compute_times', store=True)
    total_break_time = fields.Float(string='Total Break Time', compute='_compute_times', store=True)

    raw_worked_time_display = fields.Char(string='Raw Worked Time Display', compute='_compute_times', store=True)
    total_break_time_display = fields.Char(string='Total Break Time Display', compute='_compute_times', store=True)
    worked_time_display = fields.Char(string='Net Worked Time Display', compute='_compute_times', store=True)

    productive_hours = fields.Float(string="Productive Hours", compute="_compute_productive_time", store=True)
    productive_time_display = fields.Char(string="Productive Time Display", compute="_compute_productive_time", store=True)

    @api.constrains('check_in', 'employee_id')
    def _check_leave_overlap(self):
        for att in self:
            if not att.check_in or not att.employee_id:
                continue

            check_in_date = fields.Datetime.context_timestamp(self, att.check_in).date()

            leaves = self.env['hr.leave'].sudo().search([
                ('employee_id', '=', att.employee_id.id),
                ('state', '=', 'validate'),
                ('request_date_from', '<=', check_in_date),
                ('request_date_to', '>=', check_in_date),
            ])

            for leave in leaves:
                if getattr(leave, 'request_unit_half', False) or getattr(leave, 'request_unit_hours', False):
                    continue

                raise ValidationError(_("You cannot check in because you have an approved full-day leave on %s.") % check_in_date.strftime('%d-%m-%Y'))

    @api.constrains('check_in', 'employee_id')
    def _check_holiday_check_in(self):
        for att in self:
            if not att.check_in or not att.employee_id:
                continue

            check_in_date = fields.Datetime.context_timestamp(self, att.check_in).date()

            company = att.employee_id.company_id or self.env.company
            config = self.env['hr.working.days.config'].sudo().search([
                ('year', '=', check_in_date.year),
                ('month', '=', str(check_in_date.month)),
                ('company_ids', '=', company.id),
            ], limit=1)

            if config:
                day_type, label = config.get_date_day_type(check_in_date)
                if day_type in ('holiday', 'sunday', 'saturdayOff'):
                    if day_type == 'holiday':
                        raise ValidationError(_("Today is a holiday (%s). No login/check-in is allowed!") % label)
                    else:
                        raise ValidationError(_("Today is a %s. No login/check-in is allowed!") % label)
            else:
                user_tz = self.env.user.tz or 'UTC'
                try:
                    tz = pytz.timezone(user_tz)
                except Exception:
                    tz = pytz.UTC

                local_start = tz.localize(datetime.datetime.combine(check_in_date, datetime.time.min))
                utc_start = local_start.astimezone(pytz.utc).replace(tzinfo=None)
                local_end = tz.localize(datetime.datetime.combine(check_in_date, datetime.time.max))
                utc_end = local_end.astimezone(pytz.utc).replace(tzinfo=None)

                domain = [
                    ('date_from', '<=', utc_end),
                    ('date_to', '>=', utc_start),
                    ('resource_id', '=', False),
                ]
                if company:
                    domain += ['|', ('calendar_id', '=', False), '|', ('calendar_id.company_id', '=', False), ('calendar_id.company_id', '=', company.id)]

                leave = self.env['resource.calendar.leaves'].sudo().search(domain, limit=1)
                if leave:
                    raise ValidationError(_("Today is a holiday (%s). No login/check-in is allowed!") % (leave.name or 'Public Holiday'))

                weekday = calendar.weekday(check_in_date.year, check_in_date.month, check_in_date.day)
                if weekday == 6:
                    raise ValidationError(_("Today is a Sunday. No login/check-in is allowed!"))

    @api.depends('break_line_ids.break_in', 'break_line_ids.break_out')
    def _compute_is_on_break(self):
        for rec in self:
            rec.is_on_break = any(not b.break_out for b in rec.break_line_ids)

    @api.depends('check_in', 'check_out', 'break_line_ids.duration')
    def _compute_times(self):
        for rec in self:
            raw_worked = 0.0
            if rec.check_in:
                end_time = rec.check_out or fields.Datetime.now()
                delta = end_time - rec.check_in
                raw_worked = delta.total_seconds() / 3600.0

            rec.raw_worked_time = max(raw_worked, 0.0)

            total_break = sum(b.duration for b in rec.break_line_ids)
            rec.total_break_time = total_break

            net_worked = max(rec.raw_worked_time - rec.total_break_time, 0.0)

            def format_time(hours):
                seconds = int(hours * 3600)
                h = seconds // 3600
                m = (seconds % 3600) // 60
                return f"{h}h {m}m"

            rec.raw_worked_time_display = format_time(rec.raw_worked_time)
            rec.total_break_time_display = format_time(rec.total_break_time)
            rec.worked_time_display = format_time(net_worked)

    def action_break_in(self):
        for rec in self:
            if rec.is_on_break:
                raise UserError(_('Already on break.'))
            if not rec.check_in or rec.check_out:
                raise UserError(_('Must be checked in to take a break.'))

            self.env['hr.attendance.break.line'].create({
                'attendance_id': rec.id,
                'break_in': fields.Datetime.now()
            })

    def action_break_out(self):
        for rec in self:
            if not rec.is_on_break:
                raise UserError(_('Not on break.'))

            open_breaks = rec.break_line_ids.filtered(lambda b: not b.break_out)
            if open_breaks:
                open_breaks.write({'break_out': fields.Datetime.now()})

    @api.model
    def auto_checkout(self):
        """Automatically check out all employees who are currently checked in.
        
        - Closes any active break lines for each open attendance.
        - Stops any running task timers for the employee in project.task.
        - Sets check_out time:
          * If check_in is from a past date: sets to scheduled shift end (19:00) on that date.
          * If check_in is from today:
            - If current local time >= shift end: sets to scheduled shift end (19:00).
            - If current local time < shift end (e.g. manual trigger): sets to current time.
        """
        _logger.info("Starting auto_checkout for open attendances...")
        open_attendances = self.filtered(lambda a: not a.check_out) if self else self.sudo().search([('check_out', '=', False)])
        if not open_attendances:
            _logger.info("Auto checkout: No open attendances found.")
            return True

        now_utc = fields.Datetime.now()
        checked_out_count = 0

        for att in open_attendances:
            if not att.check_in or not att.employee_id:
                continue

            # Determine employee timezone
            tz_name = (
                att.employee_id.tz
                or att.employee_id.user_id.tz
                or self.env.user.tz
                or 'UTC'
            )
            try:
                tz = pytz.timezone(tz_name)
            except Exception:
                tz = pytz.UTC

            # Convert check_in and now to employee local time
            check_in_local = pytz.utc.localize(att.check_in).astimezone(tz)
            now_local = pytz.utc.localize(now_utc).astimezone(tz)

            check_in_date = check_in_local.date()
            today_date = now_local.date()

            # Determine scheduled shift end time (from calendar or fallback to 19:00 / 7:00 PM)
            calendar_id = att.employee_id.resource_calendar_id or att.employee_id.company_id.resource_calendar_id
            weekday_str = str(check_in_local.weekday())
            day_attendances = (
                calendar_id.attendance_ids.filtered(lambda a: a.dayofweek == weekday_str)
                if calendar_id else False
            )
            max_hour = max(day_attendances.mapped('hour_to')) if day_attendances else 0.0
            end_hour_float = max_hour if max_hour > 0 else 19.0

            end_hour = int(end_hour_float)
            end_minute = int(round((end_hour_float - end_hour) * 60))
            if end_minute >= 60:
                end_hour += 1
                end_minute = 0

            target_checkout_local = check_in_local.replace(
                hour=end_hour, minute=end_minute, second=0, microsecond=0
            )
            if target_checkout_local <= check_in_local:
                target_checkout_local = check_in_local + timedelta(hours=1)

            if check_in_date < today_date:
                # Past day attendance: check out at shift end on that day
                checkout_local = target_checkout_local
            else:
                # Today's attendance:
                if now_local >= target_checkout_local:
                    checkout_local = target_checkout_local
                else:
                    checkout_local = now_local

            # Convert checkout local to UTC naive datetime
            checkout_utc = checkout_local.astimezone(pytz.utc).replace(tzinfo=None)

            # Ensure check_out is never earlier than check_in
            if checkout_utc < att.check_in:
                checkout_utc = att.check_in + timedelta(seconds=1)

            # 1. Close any open break lines
            open_breaks = att.break_line_ids.filtered(lambda b: not b.break_out)
            if open_breaks:
                for b in open_breaks:
                    b_out = max(checkout_utc, b.break_in)
                    b.write({'break_out': b_out})

            # 2. Stop running task timers for this employee if project.task exists
            if 'project.task' in self.env:
                try:
                    self.env['project.task'].sudo()._auto_stop_running_timer_for_employee(
                        att.employee_id, stop_time=checkout_utc
                    )
                except Exception as e:
                    _logger.warning("Error stopping timer for employee %s during auto checkout: %s", att.employee_id.name, e)

            # 3. Write check_out to attendance
            att.sudo().write({'check_out': checkout_utc})
            checked_out_count += 1
            _logger.info("Auto checkout completed for employee %s (Attendance ID: %s, Check-out: %s)",
                         att.employee_id.name, att.id, checkout_utc)

        _logger.info("Auto checkout finished. Total attendances checked out: %d", checked_out_count)
        return True

    @api.model
    def _cron_auto_check_out(self):
        """Override standard Odoo 19 auto check-out cron to ensure employees are checked out."""
        try:
            super()._cron_auto_check_out()
        except Exception:
            pass
        return self.auto_checkout()

    @api.depends('check_in', 'employee_id', 'employee_id.resource_calendar_id.late_time')
    def _compute_is_late(self):
        for rec in self:
            rec.is_late = False
            rec.late_duration = 0.0
            rec.late_duration_display = ""

            if rec.check_in and rec.employee_id:
                tz_name = rec.employee_id.tz or self.env.user.tz or 'UTC'
                tz = pytz.timezone(tz_name)

                check_in_local = pytz.utc.localize(rec.check_in).astimezone(tz)
                day_start_local = check_in_local.replace(hour=0, minute=0, second=0, microsecond=0)

                day_start_utc = day_start_local.astimezone(pytz.utc).replace(tzinfo=None)

                earlier_attendance = self.env['hr.attendance'].sudo().search([
                    ('employee_id', '=', rec.employee_id.id),
                    ('check_in', '>=', fields.Datetime.to_string(day_start_utc)),
                    ('check_in', '<', fields.Datetime.to_string(rec.check_in)),
                    ('id', '!=', rec.id)
                ], limit=1)

                if earlier_attendance:
                    continue

                calendar = rec.employee_id.resource_calendar_id or rec.employee_id.company_id.resource_calendar_id
                late_val = calendar.late_time if calendar and calendar.late_time else 9.583333
                late_hour = int(late_val)
                late_minute = int(round((late_val - late_hour) * 60))
                if late_minute >= 60:
                    late_hour += 1
                    late_minute = 0

                threshold_local = check_in_local.replace(hour=late_hour, minute=late_minute, second=0, microsecond=0)
                check_in_for_compare = check_in_local.replace(second=0, microsecond=0)

                if check_in_for_compare > threshold_local:
                    rec.is_late = True
                    diff = check_in_for_compare - threshold_local
                    seconds = diff.total_seconds()
                    rec.late_duration = seconds / 3600.0

                    h = int(seconds // 3600)
                    m = int((seconds % 3600) // 60)

                    display = []
                    if h > 0:
                        display.append(f"{h}h")
                    if m > 0 or h > 0:
                        display.append(f"{m}m")
                    rec.late_duration_display = " ".join(display)

    @api.depends('check_in', 'check_out')
    def _compute_productive_time(self):
        for rec in self:
            rec.productive_hours = 0.0
            rec.productive_time_display = "0h 0m"
            if 'account.analytic.line' in self.env and 'attendance_id' in self.env['account.analytic.line']._fields:
                if rec.id:
                    lines = self.env['account.analytic.line'].sudo().search([('attendance_id', '=', rec.id)])
                    total = sum(lines.mapped('unit_amount'))
                    rec.productive_hours = total
                    h = int(total)
                    m = int(round((total - h) * 60))
                    rec.productive_time_display = f"{h}h {m}m"


class AccountAnalyticLine(models.Model):
    _inherit = 'account.analytic.line'

    attendance_id = fields.Many2one('hr.attendance', string='Attendance')


class HrAttendanceOvertimeRule(models.Model):
    _inherit = 'hr.attendance.overtime.rule'

    def _get_expected_hours_from_contract(self, date, version, period='day'):
        expected_hours = super()._get_expected_hours_from_contract(date, version, period=period)
        calendar = version.resource_calendar_id or version.company_id.resource_calendar_id
        if calendar and calendar.break_time:
            if period == 'day' and calendar.hours_per_day:
                expected_hours = min(expected_hours, calendar.hours_per_day)
            elif period == 'week' and calendar.hours_per_week:
                expected_hours = min(expected_hours, calendar.hours_per_week)
        return expected_hours

    def _get_daterange_overtime_undertime_intervals_for_quantity_rule(self, start, stop, attendance_intervals, schedule):
        self.ensure_one()
        context_expected_duration = 'hr_attendance_expected_duration' in self.env.context
        expected_duration = self.env.context.get('hr_attendance_expected_duration', self.expected_hours)
        attendances_interval_without_lunch = []
        intervals_attendance_by_attendance = defaultdict(Intervals)
        attendances = self.env['hr.attendance']
        for (a_start, a_stop, attendance) in attendance_intervals:
            attendances += attendance
            intervals_attendance_by_attendance[attendance] = (Intervals([(a_start, a_stop, self.env['resource.calendar'])]) - (schedule['lunch'] - schedule['leave'])) &\
                Intervals([(start, stop, self.env['resource.calendar'])])
            attendances_interval_without_lunch.extend(intervals_attendance_by_attendance[attendance]._items)

        employee = attendances.employee_id
        calendar = employee.resource_calendar_id or employee.company_id.resource_calendar_id
        if self.expected_hours_from_contract and not context_expected_duration:
            if employee.version_id.is_flexible:
                expected_duration = self._get_expected_hours_from_contract(start.date(), employee.version_id, period=self.quantity_period)
                if calendar and calendar.break_time and calendar.hours_per_day:
                    expected_duration = min(expected_duration, calendar.hours_per_day)
            else:
                period_schedule = (schedule['work'] - schedule['leave']) & Intervals([(start, stop, self.env['resource.calendar'])])
                raw_schedule_hours = sum_intervals(period_schedule)
                if calendar and calendar.break_time and raw_schedule_hours > 0:
                    if self.quantity_period == 'day' and calendar.hours_per_day:
                        expected_duration = min(raw_schedule_hours, calendar.hours_per_day)
                    elif self.quantity_period == 'week' and calendar.hours_per_week:
                        expected_duration = min(raw_schedule_hours, calendar.hours_per_week)
                    else:
                        expected_duration = max(0.0, raw_schedule_hours - calendar.break_time)
                else:
                    expected_duration = raw_schedule_hours

        overtime_amount = sum_intervals(Intervals(attendances_interval_without_lunch)) - expected_duration
        company = self.company_id or employee.company_id
        if company.absence_management and float_compare(overtime_amount, -self.employee_tolerance, 5) == -1:
            if not intervals_attendance_by_attendance:
                return {}, {}
            last_attendance = sorted(intervals_attendance_by_attendance.keys(), key=lambda att: att.check_out)[-1]
            return {}, {last_attendance: [(overtime_amount, self)]}

        if float_compare(overtime_amount, self.employer_tolerance, 5) != 1:
            return {}, {}

        overtime_intervals = defaultdict(list)
        remaining_duration = expected_duration
        remanining_overtime_amount = overtime_amount
        for attendance in attendances.sorted('check_in'):
            for a_start, a_stop, _cal in intervals_attendance_by_attendance[attendance]:
                interval_duration = (a_stop - a_start).total_seconds() / 3600
                if remaining_duration >= interval_duration:
                    remaining_duration -= interval_duration
                    continue
                interval_overtime_duration = interval_duration
                if remaining_duration != 0:
                    interval_overtime_duration = interval_duration - remaining_duration
                new_start = a_stop - timedelta(hours=interval_overtime_duration)
                remaining_duration = 0
                overtime_intervals[attendance].append((new_start, a_stop, self))
                remanining_overtime_amount = remanining_overtime_amount - interval_overtime_duration
                if remanining_overtime_amount <= 0:
                    return overtime_intervals, {}
        return overtime_intervals, {}

