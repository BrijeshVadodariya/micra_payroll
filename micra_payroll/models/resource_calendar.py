# -*- coding: utf-8 -*-
from collections import defaultdict
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ResourceCalendar(models.Model):
    _inherit = 'resource.calendar'

    late_time = fields.Float(
        string="Late Time",
        default=9.583333,
        help="Check-in time after which attendance is considered late (e.g. 09:35)."
    )
    break_time = fields.Float(
        string="Break Time",
        default=0.0,
        help="Daily break time in hours to deduct from working hours (e.g. 1.0 for 1 hour)."
    )
    bracktime = fields.Float(
        string="Break Time",
        compute="_compute_bracktime",
        inverse="_inverse_bracktime",
        search="_search_bracktime",
        help="Alias for break_time."
    )
    has_break_lines = fields.Boolean(
        string="Has Break Lines",
        compute="_compute_has_break_lines",
        help="Technical field indicating if any line in the working hours table is set to Break."
    )

    @api.depends('attendance_ids.day_period')
    def _compute_has_break_lines(self):
        for calendar in self:
            calendar.has_break_lines = any(
                att.day_period == 'lunch' and not getattr(att, 'display_type', False)
                for att in calendar.attendance_ids
            )

    @api.depends('break_time')
    def _compute_bracktime(self):
        for cal in self:
            cal.bracktime = cal.break_time

    def _inverse_bracktime(self):
        for cal in self:
            cal.break_time = cal.bracktime

    def _search_bracktime(self, operator, value):
        return [('break_time', operator, value)]

    @api.constrains('break_time')
    def _check_break_time(self):
        for calendar in self:
            if calendar.break_time < 0:
                raise ValidationError(_("Break time cannot be negative."))

    @api.onchange('break_time')
    def _onchange_break_time(self):
        self._compute_hours_per_day()

    @api.depends('attendance_ids.hour_from', 'attendance_ids.hour_to', 'attendance_ids.dayofweek', 'attendance_ids.day_period', 'break_time', 'two_weeks_calendar')
    def _compute_hours_per_day(self):
        for calendar in self:
            attendances = calendar.attendance_ids.filtered(lambda a: not getattr(a, 'display_type', False))
            if not attendances:
                calendar.hours_per_day = 0.0
                if hasattr(calendar, 'full_time_required_hours'):
                    calendar.full_time_required_hours = 0.0
                continue

            if calendar.two_weeks_calendar:
                day_groups = defaultdict(list)
                for att in attendances:
                    day_groups[(getattr(att, 'week_type', False), att.dayofweek)].append(att)

                total_net_hours = 0.0
                for (w_type, day), atts in day_groups.items():
                    work_atts = [a for a in atts if getattr(a, 'day_period', False) != 'lunch']
                    break_atts = [a for a in atts if getattr(a, 'day_period', False) == 'lunch']
                    work_hours = sum(a.hour_to - a.hour_from for a in work_atts)
                    explicit_break = sum(a.hour_to - a.hour_from for a in break_atts)
                    additional_break = max(0.0, (calendar.break_time or 0.0) - explicit_break)
                    total_net_hours += max(0.0, work_hours - additional_break)

                distinct_days = len(day_groups)
                calendar.hours_per_day = (total_net_hours / distinct_days) if distinct_days else 0.0
                if hasattr(calendar, 'full_time_required_hours'):
                    calendar.full_time_required_hours = total_net_hours / 2.0
            else:
                day_groups = defaultdict(list)
                for att in attendances:
                    day_groups[att.dayofweek].append(att)

                total_net_hours = 0.0
                for day, atts in day_groups.items():
                    work_atts = [a for a in atts if getattr(a, 'day_period', False) != 'lunch']
                    break_atts = [a for a in atts if getattr(a, 'day_period', False) == 'lunch']
                    work_hours = sum(a.hour_to - a.hour_from for a in work_atts)
                    explicit_break = sum(a.hour_to - a.hour_from for a in break_atts)
                    additional_break = max(0.0, (calendar.break_time or 0.0) - explicit_break)
                    total_net_hours += max(0.0, work_hours - additional_break)

                count = len(day_groups)
                calendar.hours_per_day = (total_net_hours / count) if count else 0.0
                if hasattr(calendar, 'full_time_required_hours'):
                    calendar.full_time_required_hours = total_net_hours

    def _get_hours_per_week(self):
        self.ensure_one()
        day_groups = defaultdict(list)
        attendances = self._get_global_attendances()
        break_lines = self.attendance_ids.filtered(lambda a: getattr(a, 'day_period', False) == 'lunch' and not getattr(a, 'display_type', False))
        explicit_break_by_day = defaultdict(float)
        for b in break_lines:
            key = (getattr(b, 'week_type', False), b.dayofweek) if self.two_weeks_calendar else b.dayofweek
            explicit_break_by_day[key] += b.hour_to - b.hour_from

        for att in attendances:
            key = (getattr(att, 'week_type', False), att.dayofweek) if self.two_weeks_calendar else att.dayofweek
            day_groups[key].append(att)
        total_net = 0.0
        for key, atts in day_groups.items():
            if getattr(self, 'duration_based', False):
                day_raw = sum(a.duration_hours for a in atts)
            else:
                day_raw = sum(a.hour_to - a.hour_from for a in atts)
            explicit_break = explicit_break_by_day.get(key, 0.0)
            additional_break = max(0.0, (self.break_time or 0.0) - explicit_break)
            total_net += max(0.0, day_raw - additional_break)
        return (total_net / 2.0) if self.two_weeks_calendar else total_net

    @api.depends('break_time')
    def _compute_hours_per_week(self):
        super()._compute_hours_per_week()

    def write(self, vals):
        res = super().write(vals)
        if 'break_time' in vals:
            self._compute_hours_per_day()
            self._compute_hours_per_week()
            employees = self.env['hr.employee'].search([('resource_calendar_id', 'in', self.ids)])
            attendances = self.env['hr.attendance'].search([
                ('employee_id', 'in', employees.ids),
                ('check_out', '!=', False)
            ])
            if attendances:
                attendances._update_overtime()
        return res

    def get_work_hours_count(self, start_dt, end_dt, compute_leaves=True, domain=None):
        if not self.break_time:
            return super().get_work_hours_count(start_dt, end_dt, compute_leaves=compute_leaves, domain=domain)
        try:
            resources = self.env['resource.resource']
            if compute_leaves:
                intervals = self._work_intervals_batch(start_dt, end_dt, resources=resources, domain=domain)[False]
            else:
                intervals = self._attendance_intervals_batch(start_dt, end_dt, resources=resources, domain=domain)[False]
            day_hours = defaultdict(float)
            for start, stop, meta in intervals:
                day_hours[start.date()] += (stop - start).total_seconds() / 3600.0
            return sum(max(0.0, h - self.break_time) for h in day_hours.values())
        except Exception:
            return super().get_work_hours_count(start_dt, end_dt, compute_leaves=compute_leaves, domain=domain)


class ResourceCalendarAttendance(models.Model):
    _inherit = 'resource.calendar.attendance'

    @api.depends('hour_from', 'hour_to', 'day_period', 'calendar_id.hours_per_day', 'calendar_id.break_time')
    def _compute_duration_days(self):
        for attendance in self:
            if attendance.day_period == 'lunch':
                attendance.duration_days = 0.0
                continue
            calendar = attendance.calendar_id
            if calendar and calendar.hours_per_day:
                break_time = calendar.break_time or 0.0
                day_attendances = calendar.attendance_ids.filtered(
                    lambda a: a.dayofweek == attendance.dayofweek and getattr(a, 'week_type', False) == getattr(attendance, 'week_type', False) and a.day_period != 'lunch'
                )
                break_attendances = calendar.attendance_ids.filtered(
                    lambda a: a.dayofweek == attendance.dayofweek and getattr(a, 'week_type', False) == getattr(attendance, 'week_type', False) and a.day_period == 'lunch'
                )
                explicit_break = sum(a.hour_to - a.hour_from for a in break_attendances)
                additional_break = max(0.0, break_time - explicit_break)

                if len(day_attendances) == 1:
                    net_hours = max(0.0, (attendance.hour_to - attendance.hour_from) - additional_break)
                elif day_attendances and additional_break:
                    total_day_hours = sum(a.hour_to - a.hour_from for a in day_attendances)
                    line_hours = attendance.hour_to - attendance.hour_from
                    share = (line_hours / total_day_hours) if total_day_hours else 0.0
                    net_hours = max(0.0, line_hours - (additional_break * share))
                else:
                    net_hours = max(0.0, attendance.hour_to - attendance.hour_from)

                attendance.duration_days = net_hours / calendar.hours_per_day
            else:
                attendance.duration_days = 1.0
