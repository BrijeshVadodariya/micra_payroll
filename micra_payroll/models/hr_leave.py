# -*- coding: utf-8 -*-
from datetime import datetime, date, timedelta
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class HrLeave(models.Model):
    _inherit = 'hr.leave'

    has_leave_balance = fields.Boolean(compute="_compute_has_leave_balance")

    @api.depends('employee_id', 'holiday_status_id')
    def _compute_has_leave_balance(self):
        for rec in self:
            if not rec.employee_id:
                rec.has_leave_balance = True
                continue
            if rec.holiday_status_id:
                req_alloc = getattr(rec.holiday_status_id, 'requires_allocation', True)
                if isinstance(req_alloc, str):
                    req_alloc = (req_alloc == 'yes')
                if not req_alloc or getattr(rec.holiday_status_id, 'unpaid', False):
                    rec.has_leave_balance = True
                    continue
            summary = self.get_employee_leave_summary(rec.employee_id)
            rec.has_leave_balance = summary.get("remaining_total", 0.0) > 0

    @api.constrains('employee_id', 'request_date_from', 'number_of_days', 'state', 'holiday_status_id')
    def _check_monthly_accrual_credit(self):
        for rec in self:
            is_employee_leave = True
            if hasattr(rec, 'holiday_type'):
                is_employee_leave = rec.holiday_type == 'employee'

            if not is_employee_leave or not rec.employee_id or rec.state == 'refuse':
                continue

            # Only enforce leave credit check if the Time Off Type requires allocation
            if rec.holiday_status_id:
                req_alloc = getattr(rec.holiday_status_id, 'requires_allocation', True)
                if isinstance(req_alloc, str):
                    req_alloc = (req_alloc == 'yes')
                # If requires_allocation is unchecked (or it is an unpaid leave), do not check credit
                if not req_alloc or getattr(rec.holiday_status_id, 'unpaid', False):
                    continue

            summary = self.get_employee_leave_summary(rec.employee_id)
            available = summary.get('available_total', 0.0)

            start_of_cycle = self.get_cycle_start_date(rec.employee_id)
            if not start_of_cycle:
                continue

            other_domain = [
                ('employee_id', '=', rec.employee_id.id),
                ('state', 'in', ['confirm', 'validate1', 'validate']),
                ('id', '!=', rec.id),
                ('request_date_from', '>=', fields.Date.to_string(start_of_cycle)),
            ]
            if hasattr(self.env['hr.leave.type'], 'unpaid'):
                other_domain.append(('holiday_status_id.unpaid', '=', False))
            if hasattr(self.env['hr.leave.type'], 'requires_allocation'):
                other_domain.append(('holiday_status_id.requires_allocation', '=', True))

            other_leaves = self.search(other_domain)

            consumed_by_others = sum(other_leaves.mapped(lambda l: self.get_leave_days_value(l)))
            remaining_for_this = available - consumed_by_others

            if rec.number_of_days > remaining_for_this:
                raise UserError(_("You have no credit of leave please contact hr for allocation. (Available: %s, Consumed: %s)") % (round(available, 1), round(consumed_by_others, 1)))

    @api.model
    def get_employee_leave_summary(self, employee):
        summary = {
            "available_total": 0.0,
            "consumed_total": 0.0,
            "remaining_total": 0.0,
            "service_months": 0,
        }

        if not employee:
            return summary

        employee_sudo = employee.sudo()

        join_date_raw = self.get_employee_join_date(employee_sudo)
        has_join_date = bool(join_date_raw)
        if not join_date_raw:
            join_date_raw = employee_sudo.create_date or fields.Date.today()

        join_date = self.to_date(join_date_raw)
        today = self.to_date(fields.Date.context_today(self))
        total_months = (today.year - join_date.year) * 12 + (today.month - join_date.month)

        eligible = False
        if hasattr(employee_sudo, 'employment_status'):
            eligible = employee_sudo.employment_status in ['no_bond', 'in_bond']

        has_manual = hasattr(employee_sudo, 'manual_paid_leaves')
        if has_manual:
            manual_leaves = float(getattr(employee_sudo, 'manual_paid_leaves', 0.0) or 0.0)
            future_months = max(0, 12 - today.month)
            accrued_total = max(0.0, manual_leaves - future_months)
        else:
            accrued_total = 0.0
            if eligible and has_join_date:
                accrued_total = float(max(total_months % 12, 0))
                if accrued_total == 0 and total_months >= 12:
                    accrued_total = 12.0

        allocated_manual = 0.0
        if "hr.leave.allocation" in self.env:
            today_date = fields.Date.today()
            domain = [
                ("employee_id", "=", employee_sudo.id),
                ("state", "=", "validate"),
                "&",
                    "|", ("date_from", "=", False), ("date_from", "<=", today_date),
                    "|", ("date_to", "=", False), ("date_to", ">=", today_date),
            ]
            allocations = self.env["hr.leave.allocation"].sudo().search(domain)
            allocated_manual = sum(allocations.mapped("number_of_days"))

        available_total = accrued_total + allocated_manual

        start_of_cycle = self.get_cycle_start_date(employee_sudo)
        if not start_of_cycle:
            start_of_cycle = join_date

        leave_domain = [
            ("employee_id", "=", employee_sudo.id),
            ("state", "in", ["validate1", "validate"]),
            ("holiday_status_id.unpaid", "=", False),
            ("request_date_from", ">=", fields.Date.to_string(start_of_cycle)),
        ]
        if hasattr(self.env["hr.leave.type"], "requires_allocation"):
            leave_domain.append(("holiday_status_id.requires_allocation", "=", True))
        leave_records = self.sudo().search(leave_domain)

        consumed_total = 0.0
        already_deducted_from_manual = 0.0
        for leave in leave_records:
            consumed_total += self.get_leave_days_value(leave)
            if leave.state == 'validate':
                get_uncovered = getattr(leave, '_hrms_get_uncovered_days', None)
                if get_uncovered:
                    already_deducted_from_manual += get_uncovered()

        remaining_total = max(available_total - consumed_total, 0.0)

        unpaid_leave_records = self.sudo().search([
            ("employee_id", "=", employee_sudo.id),
            ("state", "in", ["validate1", "validate"]),
            ("holiday_status_id.unpaid", "=", True),
            ("request_date_from", ">=", fields.Date.to_string(start_of_cycle)),
        ])
        consumed_unpaid_total = sum(self.get_leave_days_value(leave) for leave in unpaid_leave_records)

        summary.update({
            "accrued_total": round(accrued_total, 2),
            "allocated_manual": round(allocated_manual, 2),
            "available_total": round(available_total, 2),
            "consumed_total": round(consumed_total, 2),
            "consumed_unpaid_total": round(consumed_unpaid_total, 2),
            "remaining_total": round(remaining_total, 2),
            "service_months": int(total_months),
        })
        return summary

    @api.model
    def get_employee_leaves(self, employee):
        result = []
        if not employee:
            return result

        records = self.search([
            ("employee_id", "=", employee.id),
            ("state", "in", ["confirm", "validate1", "validate"]),
        ], order="request_date_from desc, id desc", limit=20)

        service = self.env["micra.dashboard.service"]
        for rec in records:
            result.append({
                "id": rec.id,
                "name": rec.name or "",
                "holiday_status": rec.holiday_status_id.name if rec.holiday_status_id else "",
                "date_from": service._format_datetime_or_date(rec.request_date_from or rec.date_from),
                "date_to": service._format_datetime_or_date(rec.request_date_to or rec.date_to),
            })
        return result

    def get_cycle_start_date(self, employee):
        join_date_raw = self.get_employee_join_date(employee)
        if not join_date_raw:
            join_date_raw = employee.create_date or fields.Date.today()

        join_date = self.to_date(join_date_raw)
        if not join_date:
            return None
        today = self.to_date(fields.Date.context_today(self))
        total_months = (today.year - join_date.year) * 12 + (today.month - join_date.month)

        available_total = float(max(total_months % 12, 0))
        years_completed = total_months // 12
        if available_total == 0 and total_months >= 12:
            years_completed -= 1

        return self.safe_make_date(join_date.year + years_completed, join_date.month, join_date.day)

    def get_employee_join_date(self, employee):
        for field_name in ["contract_date_start", "first_contract_date", "joining_date", "date_join", "join_date"]:
            if field_name in employee._fields and employee[field_name]:
                return employee[field_name]
        return False

    def to_date(self, value):
        if not value:
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            try:
                return fields.Date.from_string(value)
            except Exception:
                return None
        return None

    def safe_make_date(self, year, month, day):
        try:
            return date(year, month, day)
        except ValueError:
            if month == 2 and day == 29:
                return date(year, 2, 28)
            return None

    def get_leave_days_value(self, leave):
        for field_name in ["number_of_days_display", "number_of_days"]:
            if field_name in leave._fields:
                try:
                    return float(leave[field_name] or 0.0)
                except Exception:
                    continue
        return 0.0

    def _micra_get_leave_dates(self, period_start=False, period_end=False):
        self.ensure_one()
        period_start = fields.Date.to_date(period_start) if period_start else False
        period_end = fields.Date.to_date(period_end) if period_end else False
        leave_dates = set()
        if not self.request_date_from or not self.request_date_to:
            return leave_dates

        start_date = max(self.request_date_from, period_start) if period_start else self.request_date_from
        end_date = min(self.request_date_to, period_end) if period_end else self.request_date_to
        current = start_date
        while current <= end_date:
            leave_dates.add(current)
            current += timedelta(days=1)
        return leave_dates

    def _micra_duration_days(self):
        self.ensure_one()
        if self.request_unit_hours and self.request_date_from == self.request_date_to:
            return self.number_of_days
        if (
            self.request_date_from and
            self.request_date_to and
            not self.request_unit_half and
            (not self.request_unit_hours or self.request_date_from != self.request_date_to)
        ):
            return float(len(self._micra_get_leave_dates()))
        return self.number_of_days or 0.0
