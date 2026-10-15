# -*- coding: utf-8 -*-

from datetime import timedelta, date, datetime
import pytz

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class HRMSDashboardService(models.AbstractModel):
    _name = "micra.dashboard.service"
    _description = "HRMS Dashboard Service"

    @api.model
    def get_dashboard_data(self):
        employee = self._get_current_employee()
        attendance = self._get_dashboard_attendance(employee)
        active_task = self._get_active_task(employee)

        tasks = self._get_user_tasks()
        stats = self._get_user_stats(tasks)
        holidays = self._get_upcoming_holidays()
        events = self._get_upcoming_events()
        
        # Calling centralized logic in hr.leave
        leave_model = self.env["hr.leave"]
        leaves = leave_model.get_employee_leaves(employee)
        leave_summary = leave_model.get_employee_leave_summary(employee)
        
        month_attendance = self._get_month_attendance_stats(employee)
        birthdays = self._get_upcoming_birthdays()
        work_anniversaries = self._get_upcoming_work_anniversaries()

        return {
            "server_time": fields.Datetime.to_string(fields.Datetime.now()),
            "company": self._serialize_company(),
            "employee": self._serialize_employee(employee),
            "attendance": self._serialize_attendance(attendance),
            "timer": self._serialize_timer(active_task),
            "tasks": tasks,
            "projects": self._get_user_projects(),
            "stats": stats,
            "holidays": holidays,
            "events": events,
            "leaves": leaves,
            "leave_summary": leave_summary,
            "month_attendance": month_attendance,
            "birthdays": birthdays,
            "work_anniversaries": work_anniversaries,
        }

    @api.model
    def get_task_candidates(self):
        return self._get_user_tasks()

    @api.model
    def action_attendance_toggle(self):
        employee = self._get_current_employee()
        if not employee:
            raise UserError(_("No employee linked to the current user."))

        if hasattr(employee, "_attendance_action_change"):
            employee._attendance_action_change()
        elif hasattr(employee, "attendance_action_change"):
            employee.attendance_action_change()
        else:
            raise UserError(_("Attendance action method was not found on hr.employee."))

        return self.get_dashboard_data()

    @api.model
    def action_break_toggle(self):
        employee = self._get_current_employee()
        if not employee:
            raise UserError(_("No employee linked to the current user."))

        attendance = self._get_open_attendance(employee)
        if not attendance or not self._attendance_checked_in(attendance):
            raise UserError(_("Please check in first to use break."))

        if self._attendance_is_on_break(attendance):
            self._attendance_break_out(attendance)
        else:
            self._attendance_break_in(attendance)

        return self.get_dashboard_data()

    @api.model
    def action_timer(self, task_id=False, timer_action=False):
        if not timer_action:
            raise UserError(_("No timer action received."))

        employee = self._get_current_employee()
        task = self.env["project.task"].browse(int(task_id)) if task_id else self.env["project.task"]

        if timer_action == "start":
            if not self._is_employee_checked_in(employee):
                raise UserError(_("Please check in first to start task timer."))
            if self._is_employee_on_break(employee):
                raise UserError(_("Please break out first to start task timer."))
            if not task or not task.exists():
                raise UserError(_("Please select a valid task."))
            self._timer_start(task)

        elif timer_action == "pause":
            task = self._get_running_task(employee)
            if not task:
                raise UserError(_("No running task found."))
            self._timer_pause(task)

        elif timer_action == "resume":
            if self._is_employee_on_break(employee):
                raise UserError(_("Please break out first to resume task timer."))
            task = self._get_paused_task(employee)
            if not task:
                raise UserError(_("No paused task found."))
            self._timer_resume(task)

        elif timer_action == "stop":
            task = self._get_active_task(employee)
            if not task:
                raise UserError(_("No active task found."))
            self._timer_stop(task)

        elif timer_action == "cancel":
            task = self._get_active_task(employee)
            if not task:
                raise UserError(_("No active task found."))
            self._timer_cancel(task)

        else:
            raise UserError(_("Unsupported timer action: %s") % timer_action)

        return self.get_dashboard_data()

    # ---------------------------------------------------------
    # Employee / Company
    # ---------------------------------------------------------

    def _get_current_employee(self):
        return self.env["hr.employee"].sudo().search(
            [
                ("user_id", "=", self.env.user.id),
                "|",
                ("company_id", "=", False),
                ("company_id", "=", self.env.company.id),
            ],
            limit=1,
        )

    def _serialize_company(self):
        company = self.env.company
        return {
            "id": company.id,
            "name": company.name or "",
            "logo_url": f"/web/image?model=res.company&id={company.id}&field=logo",
        }

    def _serialize_employee(self, employee):
        return {
            "id": employee.id if employee else False,
            "name": employee.name if employee else "",
            "department": employee.department_id.name if employee and employee.department_id else "",
            "user_id": employee.user_id.id if employee and employee.user_id else self.env.user.id,
        }

    # ---------------------------------------------------------
    # Attendance helpers
    # ---------------------------------------------------------

    def _get_open_attendance(self, employee):
        if not employee:
            return self.env["hr.attendance"]

        return self.env["hr.attendance"].sudo().search(
            [
                ("employee_id", "=", employee.id),
                ("check_in", "!=", False),
                ("check_out", "=", False),
            ],
            order="check_in desc, id desc",
            limit=1,
        )

    def _get_latest_today_attendance(self, employee):
        if not employee:
            return self.env["hr.attendance"]

        today_start, today_end = self._get_day_bounds()

        return self.env["hr.attendance"].sudo().search(
            [
                ("employee_id", "=", employee.id),
                ("check_in", ">=", today_start),
                ("check_in", "<=", today_end),
            ],
            order="check_in desc, id desc",
            limit=1,
        )

    def _get_dashboard_attendance(self, employee):
        attendance = self._get_open_attendance(employee)
        if attendance:
            return attendance
        return self._get_latest_today_attendance(employee)

    def _get_day_bounds(self):
        now_utc = fields.Datetime.now()
        tz_name = self.env.user.tz or "UTC"
        timezone = pytz.timezone(tz_name)

        utc_aware = pytz.utc.localize(fields.Datetime.from_string(now_utc))
        local_now = utc_aware.astimezone(timezone)

        start_local = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_local = start_local + timedelta(days=1) - timedelta(seconds=1)

        start_utc = start_local.astimezone(pytz.utc).replace(tzinfo=None)
        end_utc = end_local.astimezone(pytz.utc).replace(tzinfo=None)

        return fields.Datetime.to_string(start_utc), fields.Datetime.to_string(end_utc)

    def _attendance_checked_in(self, attendance):
        return bool(attendance and attendance.check_in and not attendance.check_out)

    def _get_open_break_line(self, attendance):
        if not attendance or "break_line_ids" not in attendance._fields:
            return self.env["hr.attendance.break.line"]
        return attendance.break_line_ids.filtered(lambda b: not b.break_out)[:1]

    def _get_latest_break_line(self, attendance):
        if not attendance or "break_line_ids" not in attendance._fields:
            return self.env["hr.attendance.break.line"]
        return attendance.break_line_ids.sorted(
            key=lambda b: b.break_in or fields.Datetime.now(),
            reverse=True
        )[:1]

    def _attendance_is_on_break(self, attendance):
        if not attendance:
            return False

        if "is_on_break" in attendance._fields:
            return bool(attendance.is_on_break)

        open_break = self._get_open_break_line(attendance)
        return bool(open_break)

    def _attendance_current_break_start(self, attendance):
        open_break = self._get_open_break_line(attendance)
        return open_break.break_in if open_break and open_break.break_in else False

    def _attendance_total_break_seconds(self, attendance):
        if not attendance:
            return 0

        if "break_line_ids" in attendance._fields:
            now_dt = fields.Datetime.now()
            total_seconds = 0
            for line in attendance.break_line_ids:
                if line.break_in:
                    end_dt = line.break_out or now_dt
                    total_seconds += max(int((end_dt - line.break_in).total_seconds()), 0)
            return total_seconds

        if "total_break_hours" in attendance._fields:
            return int(round((attendance.total_break_hours or 0.0) * 3600))

        return 0

    def _attendance_current_break_seconds(self, attendance):
        if not attendance:
            return 0

        if "current_break_seconds" in attendance._fields:
            return int(attendance.current_break_seconds or 0)

        open_break = self._get_open_break_line(attendance)
        if open_break and open_break.break_in:
            now_dt = fields.Datetime.now()
            return max(int((now_dt - open_break.break_in).total_seconds()), 0)

        return 0

    def _attendance_break_seconds(self, attendance):
        if not attendance:
            return 0

        return self._attendance_total_break_seconds(attendance)

    def _attendance_overall_seconds(self, attendance):
        if not attendance or not attendance.check_in:
            return 0

        end_dt = attendance.check_out or fields.Datetime.now()
        return max(int((end_dt - attendance.check_in).total_seconds()), 0)

    def _attendance_working_seconds(self, attendance):
        if not attendance:
            return 0

        overall_seconds = self._attendance_overall_seconds(attendance)
        break_seconds = self._attendance_break_seconds(attendance)
        return max(overall_seconds - break_seconds, 0)

    def _attendance_productive_seconds(self, attendance):
        if not attendance:
            return 0

        analytic_model = self.env["account.analytic.line"].sudo()

        if "attendance_id" in analytic_model._fields:
            lines = analytic_model.search([
                ("attendance_id", "=", attendance.id),
            ])
            total_hours = sum(lines.mapped("unit_amount")) or 0.0
            return int(round(total_hours * 3600))

        if "productive_hours" in attendance._fields:
            return int(round(float(attendance.productive_hours or 0.0) * 3600))

        return 0

    def _attendance_break_in(self, attendance):
        if not attendance:
            raise UserError(_("No active attendance found."))

        if hasattr(attendance, "action_break_in"):
            attendance.sudo().action_break_in()
        else:
            raise UserError(_("Break In method was not found on hr.attendance."))

    def _attendance_break_out(self, attendance):
        if not attendance:
            raise UserError(_("No active attendance found."))

        if hasattr(attendance, "action_break_out"):
            attendance.sudo().action_break_out()
        else:
            raise UserError(_("Break Out method was not found on hr.attendance."))

    def _is_employee_checked_in(self, employee):
        attendance = self._get_open_attendance(employee)
        return self._attendance_checked_in(attendance)

    def _is_employee_on_break(self, employee):
        attendance = self._get_open_attendance(employee)
        return self._attendance_is_on_break(attendance)

    # ---------------------------------------------------------
    # Task helpers
    # ---------------------------------------------------------

    def _get_user_tasks_domain(self):
        return [
            ("user_ids", "in", [self.env.user.id]),
            ("active", "=", True),
            ("project_id", "!=", False),
        ]

    def _get_user_tasks(self):
        tasks = self.env["project.task"].sudo().search(
            self._get_user_tasks_domain(),
            order="project_id asc, priority desc, date_deadline asc, id desc",
            limit=200,
        )

        result = []
        for task in tasks:
            result.append({
                "id": task.id,
                "name": task.name or "",
                "project_id": task.project_id.id if task.project_id else False,
                "project_name": task.project_id.name if task.project_id else "",
                "stage_name": task.stage_id.name if task.stage_id else "",
                "deadline": self._format_datetime_or_date(task.date_deadline),
            })
        return result

    def _get_user_projects(self):
        user_id = self.env.user.id
        domain = [
            ("active", "=", True),
            "|", "|",
            ("user_id", "=", user_id),
            ("allowed_user_ids", "in", [user_id]),
            ("task_ids.user_ids", "in", [user_id]),
        ]
        projects = self.env["project.project"].sudo().search(domain)
        result = []
        for p in projects:
            result.append({
                "id": p.id,
                "name": p.name or "Unnamed Project",
            })
        return result

    @api.model
    def create_project_task(self, project_id, task_name):
        if not project_id or not task_name:
            return False
        task = self.env["project.task"].sudo().create({
            "name": task_name.strip(),
            "project_id": int(project_id),
            "user_ids": [(4, self.env.user.id)],
        })
        return {
            "id": task.id,
            "name": task.name,
            "project_id": task.project_id.id,
            "project_name": task.project_id.name,
        }

    def _get_running_task(self, employee):
        domain = [("timer_running", "=", True)]
        task_model = self.env["project.task"]

        if employee and "timer_employee_id" in task_model._fields:
            domain.append(("timer_employee_id", "=", employee.id))
        elif "timer_user_id" in task_model._fields:
            domain.append(("timer_user_id", "=", self.env.user.id))

        return task_model.sudo().search(domain, limit=1)

    def _get_paused_task(self, employee):
        domain = [("timer_paused", "=", True)]
        task_model = self.env["project.task"]

        if employee and "timer_employee_id" in task_model._fields:
            domain.append(("timer_employee_id", "=", employee.id))
        elif "timer_user_id" in task_model._fields:
            domain.append(("timer_user_id", "=", self.env.user.id))

        return task_model.sudo().search(domain, limit=1)

    def _get_active_task(self, employee):
        task = self._get_running_task(employee)
        if task:
            return task
        return self._get_paused_task(employee)

    def _timer_start(self, task):
        employee = self._get_current_employee()
        now = fields.Datetime.now()

        active = self._get_active_task(employee)
        if active and active.id != task.id:
            raise UserError(_("Another task timer is already active. Please stop it first."))

        vals = {}
        if "timer_running" in task._fields:
            vals["timer_running"] = True
        if "timer_paused" in task._fields:
            vals["timer_paused"] = False
        if "timer_start" in task._fields:
            vals["timer_start"] = now
        if "timer_stop" in task._fields:
            vals["timer_stop"] = False
        if "timer_pause_time" in task._fields:
            vals["timer_pause_time"] = False
        if "timer_total_paused_seconds" in task._fields:
            vals["timer_total_paused_seconds"] = 0
        if "timer_user_id" in task._fields:
            vals["timer_user_id"] = self.env.user.id
        if employee and "timer_employee_id" in task._fields:
            vals["timer_employee_id"] = employee.id

        task.sudo().write(vals)

    def _timer_pause(self, task):
        vals = {}
        if "timer_running" in task._fields:
            vals["timer_running"] = False
        if "timer_paused" in task._fields:
            vals["timer_paused"] = True
        if "timer_pause_time" in task._fields:
            vals["timer_pause_time"] = fields.Datetime.now()
        task.sudo().write(vals)

    def _timer_resume(self, task):
        vals = {}
        pause_time = getattr(task, "timer_pause_time", False)
        if pause_time and "timer_total_paused_seconds" in task._fields:
            delta = fields.Datetime.from_string(fields.Datetime.now()) - fields.Datetime.from_string(pause_time)
            existing = int(getattr(task, "timer_total_paused_seconds", 0) or 0)
            vals["timer_total_paused_seconds"] = existing + max(int(delta.total_seconds()), 0)

        if "timer_running" in task._fields:
            vals["timer_running"] = True
        if "timer_paused" in task._fields:
            vals["timer_paused"] = False
        if "timer_pause_time" in task._fields:
            vals["timer_pause_time"] = False

        task.sudo().write(vals)

    def _timer_stop(self, task):
        pause_dt = getattr(task, "timer_pause_time", False)
        is_paused = bool(getattr(task, "timer_paused", False))
        stop_dt = fields.Datetime.now()

        vals = {}
        if "timer_running" in task._fields:
            vals["timer_running"] = False
        if "timer_paused" in task._fields:
            vals["timer_paused"] = False
        if "timer_stop" in task._fields:
            vals["timer_stop"] = stop_dt

        total_paused_seconds = int(getattr(task, "timer_total_paused_seconds", 0) or 0)
        if is_paused and pause_dt:
            extra_pause = fields.Datetime.from_string(stop_dt) - fields.Datetime.from_string(pause_dt)
            total_paused_seconds += max(int(extra_pause.total_seconds()), 0)

        if "timer_pause_time" in task._fields:
            vals["timer_pause_time"] = False
        if "timer_total_paused_seconds" in task._fields:
            vals["timer_total_paused_seconds"] = total_paused_seconds

        task.sudo().write(vals)

        worked_seconds = self._task_timer_seconds(task)
        if worked_seconds > 0:
            employee = self._get_current_employee()
            attendance = self._get_open_attendance(employee)
            self._create_timesheet_for_task(task, worked_seconds, attendance=attendance)

        reset_vals = {}
        if "timer_running" in task._fields:
            reset_vals["timer_running"] = False
        if "timer_paused" in task._fields:
            reset_vals["timer_paused"] = False
        if "timer_start" in task._fields:
            reset_vals["timer_start"] = False
        if "timer_stop" in task._fields:
            reset_vals["timer_stop"] = False
        if "timer_pause_time" in task._fields:
            reset_vals["timer_pause_time"] = False
        if "timer_total_paused_seconds" in task._fields:
            reset_vals["timer_total_paused_seconds"] = 0

        task.sudo().write(reset_vals)

    def _timer_cancel(self, task):
        vals = {}
        if "timer_running" in task._fields:
            vals["timer_running"] = False
        if "timer_paused" in task._fields:
            vals["timer_paused"] = False
        if "timer_start" in task._fields:
            vals["timer_start"] = False
        if "timer_stop" in task._fields:
            vals["timer_stop"] = False
        if "timer_pause_time" in task._fields:
            vals["timer_pause_time"] = False
        if "timer_total_paused_seconds" in task._fields:
            vals["timer_total_paused_seconds"] = 0

        task.sudo().write(vals)

    def _task_timer_seconds(self, task):
        if not task or not getattr(task, "timer_start", False):
            return 0

        start_dt = fields.Datetime.from_string(task.timer_start)
        paused_seconds = int(getattr(task, "timer_total_paused_seconds", 0) or 0)

        if getattr(task, "timer_running", False):
            end_dt = fields.Datetime.from_string(fields.Datetime.now())
        elif getattr(task, "timer_paused", False) and getattr(task, "timer_pause_time", False):
            end_dt = fields.Datetime.from_string(task.timer_pause_time)
        elif getattr(task, "timer_stop", False):
            end_dt = fields.Datetime.from_string(task.timer_stop)
        else:
            end_dt = fields.Datetime.from_string(fields.Datetime.now())

        total_seconds = max(int((end_dt - start_dt).total_seconds()), 0)
        return max(total_seconds - paused_seconds, 0)

    def _create_timesheet_for_task(self, task, worked_seconds, attendance=False):
        if "account.analytic.line" not in self.env:
            return

        if not task or not task.exists():
            return

        hours = float(worked_seconds) / 3600.0
        if hours <= 0:
            return

        project = task.project_id
        employee = self._get_current_employee()

        account = False
        if "analytic_account_id" in task._fields and task.analytic_account_id:
            account = task.analytic_account_id
        elif project and "analytic_account_id" in project._fields and project.analytic_account_id:
            account = project.analytic_account_id
        elif project and "account_id" in project._fields and project.account_id:
            account = project.account_id

        if not project:
            raise UserError(_("Selected task has no project, so timesheet cannot be created."))

        if not account:
            raise UserError(_(
                "No analytic account was found on this task/project. "
                "Please enable Timesheets on the project or link an analytic account first."
            ))

        line_vals = {
            "name": task.name or _("Task Timesheet"),
            "date": fields.Date.context_today(self),
            "unit_amount": round(hours, 4),
            "project_id": project.id,
            "task_id": task.id,
            "account_id": account.id,
        }

        aal_model = self.env["account.analytic.line"]

        if "attendance_id" in aal_model._fields and attendance:
            line_vals["attendance_id"] = attendance.id

        if employee:
            if "employee_id" in aal_model._fields:
                line_vals["employee_id"] = employee.id
            if "user_id" in aal_model._fields:
                line_vals["user_id"] = employee.user_id.id or self.env.user.id
        else:
            if "user_id" in aal_model._fields:
                line_vals["user_id"] = self.env.user.id

        aal_model.sudo().create(line_vals)

    # ---------------------------------------------------------
    # Serialization
    # ---------------------------------------------------------

    def _serialize_attendance(self, attendance):
        overall_seconds = self._attendance_overall_seconds(attendance)
        break_seconds = self._attendance_break_seconds(attendance)
        current_break_seconds = self._attendance_current_break_seconds(attendance)
        working_seconds = self._attendance_working_seconds(attendance)

        current_break_start = self._attendance_current_break_start(attendance)
        latest_break = self._get_latest_break_line(attendance)
        open_break = self._get_open_break_line(attendance)

        latest_break_in = False
        latest_break_out = False

        if open_break:
            latest_break_in = open_break.break_in
            latest_break_out = False
        elif latest_break:
            latest_break_in = latest_break.break_in
            latest_break_out = latest_break.break_out

        productive_seconds = self._attendance_productive_seconds(attendance)

        is_late = False
        if attendance:
            is_late = bool(attendance.is_late)
            if not is_late and attendance.check_in:
                emp = attendance.employee_id or self._get_current_employee()
                cal = emp.resource_calendar_id or emp.company_id.resource_calendar_id if emp else False
                late_val = cal.late_time if cal and cal.late_time else 9.583333
                late_h = int(late_val)
                late_m = int(round((late_val - late_h) * 60))
                if late_m >= 60:
                    late_h += 1
                    late_m = 0
                tz_name = self.env.user.tz or "UTC"
                timezone = pytz.timezone(tz_name)
                check_in_local = pytz.utc.localize(attendance.check_in).astimezone(timezone)
                if check_in_local.hour > late_h or (check_in_local.hour == late_h and check_in_local.minute > late_m):
                    is_late = True

        return {
            "id": attendance.id if attendance else False,
            "checked_in": self._attendance_checked_in(attendance),
            "is_on_break": self._attendance_is_on_break(attendance),
            "action": "check_out" if self._attendance_checked_in(attendance) else "check_in",
            "is_late": is_late,

            "check_in": self._format_datetime_or_date(attendance.check_in) if attendance and attendance.check_in else "-",
            "check_out": self._format_datetime_or_date(attendance.check_out) if attendance and attendance.check_out else "-",

            "check_in_raw": fields.Datetime.to_string(attendance.check_in) if attendance and attendance.check_in else False,
            "check_out_raw": fields.Datetime.to_string(attendance.check_out) if attendance and attendance.check_out else False,

            "current_break_start_raw": fields.Datetime.to_string(current_break_start) if current_break_start else False,
            "last_break_in_raw": fields.Datetime.to_string(latest_break_in) if latest_break_in else False,
            "last_break_out_raw": fields.Datetime.to_string(latest_break_out) if latest_break_out else False,

            "break_in_display": self._format_datetime_or_date(latest_break_in) if latest_break_in else "-",
            "break_out_display": self._format_datetime_or_date(latest_break_out) if latest_break_out else "-",

            "overall_seconds": overall_seconds,
            "worked_seconds": working_seconds,
            "break_seconds": break_seconds,
            "current_break_seconds": current_break_seconds,

            "overall_time_display": self._seconds_to_hhmmss(overall_seconds),
            "worked_time_display": self._seconds_to_hhmmss(working_seconds),
            "total_break_time_display": self._seconds_to_hhmmss(break_seconds),
            "current_break_time_display": self._seconds_to_hhmmss(current_break_seconds),

            "productive_seconds": productive_seconds,
            "productive_hours": round(productive_seconds / 3600.0, 4),
            "productive_time_display": self._seconds_to_hhmmss(productive_seconds),
        }

    def _serialize_timer(self, task):
        if not task:
            return {
                "task_id": False,
                "task_name": "",
                "project_id": False,
                "project_name": "",
                "running": False,
                "paused": False,
                "display": "00:00:00",
                "seconds": 0,
                "timer_start_raw": False,
                "timer_stop_raw": False,
                "timer_pause_time_raw": False,
                "paused_seconds": 0,
            }

        seconds = self._task_timer_seconds(task)

        return {
            "task_id": task.id,
            "task_name": task.name or "",
            "project_id": task.project_id.id if task.project_id else False,
            "project_name": task.project_id.name if task.project_id else "",
            "running": bool(getattr(task, "timer_running", False)),
            "paused": bool(getattr(task, "timer_paused", False)),
            "display": self._seconds_to_hhmmss(seconds),
            "seconds": seconds,
            "timer_start_raw": fields.Datetime.to_string(getattr(task, "timer_start", False)) if getattr(task, "timer_start", False) else False,
            "timer_stop_raw": fields.Datetime.to_string(getattr(task, "timer_stop", False)) if getattr(task, "timer_stop", False) else False,
            "timer_pause_time_raw": fields.Datetime.to_string(getattr(task, "timer_pause_time", False)) if getattr(task, "timer_pause_time", False) else False,
            "paused_seconds": int(getattr(task, "timer_total_paused_seconds", 0) or 0),
        }

    # ---------------------------------------------------------
    # Monthly attendance / stats
    # ---------------------------------------------------------

    def _get_month_attendance_stats(self, employee):
        if not employee:
            return {
                "working_days": 0,
                "working_hours": 0,
                "worked_days": 0,
                "worked_hours": 0,
                "worked_hours_display": "0h 0m",
            }

        now = fields.Datetime.now()
        user_now = fields.Datetime.context_timestamp(self, now)
        start_local = user_now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        if start_local.month == 12:
            next_month = start_local.replace(year=start_local.year + 1, month=1)
        else:
            next_month = start_local.replace(month=start_local.month + 1)

        end_local = next_month - timedelta(seconds=1)

        start_utc = fields.Datetime.to_string(
            start_local.astimezone(pytz.utc).replace(tzinfo=None)
        ) if getattr(start_local, "tzinfo", None) else fields.Datetime.to_string(start_local)

        end_utc = fields.Datetime.to_string(
            end_local.astimezone(pytz.utc).replace(tzinfo=None)
        ) if getattr(end_local, "tzinfo", None) else fields.Datetime.to_string(end_local)

        company = employee.company_id or self.env.company
        year = user_now.year
        month_str = str(user_now.month)
        
        # 1. Try to find the custom Working Days Configuration record
        working_days_config = False
        if "hr.working.days.config" in self.env:
            domain = [
                ("year", "=", int(year)),
                ("month", "=", str(month_str)),
            ]
            if company:
                domain.append(("company_ids", "in", [company.id]))
            working_days_config = self.env["hr.working.days.config"].sudo().search(domain, limit=1)
            if not working_days_config:
                working_days_config = self.env["hr.working.days.config"].sudo().search([
                    ("year", "=", int(year)),
                    ("month", "=", str(month_str)),
                ], limit=1)

        if working_days_config:
            working_days = working_days_config.working_days
            daily_hours = employee.resource_calendar_id.hours_per_day if (employee.resource_calendar_id and employee.resource_calendar_id.hours_per_day) else 8.0
            working_hours = float(working_days) * daily_hours
        else:
            # 2. Fallback to resource calendar or company default config
            working_days = 22
            if hasattr(company, 'working_days_in_month') and company.working_days_in_month:
                working_days = company.working_days_in_month
            
            working_hours = float(working_days) * 8.0

            if employee.resource_calendar_id:
                try:
                    resource = employee.resource_id
                    work_intervals = employee.resource_calendar_id._work_intervals_batch(
                        start_local.replace(tzinfo=None),
                        end_local.replace(tzinfo=None),
                        resources=resource or self.env['resource.resource'],
                    )
                    res_id = resource.id if resource else False
                    if res_id and res_id in work_intervals:
                        intervals = work_intervals[res_id]
                    else:
                        intervals = next(iter(work_intervals.values())) if work_intervals else []
                    
                    if intervals:
                        working_hours = sum((item[1] - item[0]).total_seconds() / 3600.0 for item in intervals)
                        dates = {item[0].date() for item in intervals}
                        working_days = len(dates)
                except Exception:
                    pass

        attendances = self.env["hr.attendance"].sudo().search([
            ("employee_id", "=", employee.id),
            ("check_in", ">=", start_utc),
            ("check_in", "<=", end_utc),
        ])

        user_tz = employee.tz or employee.resource_calendar_id.tz or self.env.user.tz or 'Asia/Calcutta'
        self_tz = self.with_context(tz=user_tz)

        worked_dates = set()
        worked_seconds = 0
        day_earliest_checkin = {}
        for att in attendances:
            if not att.check_in:
                continue
            check_in_local = fields.Datetime.context_timestamp(self_tz, att.check_in)
            d = check_in_local.date()
            if d not in day_earliest_checkin or check_in_local < day_earliest_checkin[d]:
                day_earliest_checkin[d] = check_in_local
            
            worked_dates.add(d)
            worked_seconds += self._attendance_working_seconds(att)

        worked_days = len(worked_dates)
        late_days = 0
        cal = employee.resource_calendar_id or employee.company_id.resource_calendar_id if employee else False
        late_val = cal.late_time if cal and cal.late_time else 9.583333
        late_h = int(late_val)
        late_m = int(round((late_val - late_h) * 60))
        if late_m >= 60:
            late_h += 1
            late_m = 0

        for d, first_check_in in day_earliest_checkin.items():
            if first_check_in.hour > late_h or (first_check_in.hour == late_h and first_check_in.minute > late_m):
                late_days += 1

        worked_hours = round(worked_seconds / 3600.0, 2)

        h = int(worked_seconds // 3600)
        m = int((worked_seconds % 3600) // 60)
        worked_hours_display = f"{h}h {m}m"

        return {
            "working_days": int(working_days),
            "working_hours": round(float(working_hours), 2),
            "worked_days": int(worked_days),
            "worked_hours": worked_hours,
            "worked_hours_display": worked_hours_display,
            "late_days": employee.current_month_late_days if 'current_month_late_days' in employee._fields else late_days,
            "tickets_remaining": employee.current_month_tickets if 'current_month_tickets' in employee._fields else 4,
            "ticket_violations": employee.current_month_ticket_violations if 'current_month_ticket_violations' in employee._fields else 0,
            "unrevoked_ticket_violations": employee.current_month_unrevoked_ticket_violations if 'current_month_unrevoked_ticket_violations' in employee._fields else 0,
            "compensation_days": employee.current_month_compensation_days if 'current_month_compensation_days' in employee._fields else 0,
        }

    def _get_user_stats(self, task_rows):
        overdue_count = 0
        pending_count = len(task_rows)
        # ✅ FIX: Always use date for comparison, never datetime
        today = self._to_date(fields.Date.context_today(self))

        task_ids = [row["id"] for row in task_rows]
        tasks = self.env["project.task"].sudo().browse(task_ids)

        for task in tasks:
            try:
                if task.date_deadline:
                    # ✅ FIX: Normalize deadline to date before comparison
                    deadline = self._to_date(task.date_deadline)
                    if deadline and deadline < today:
                        overdue_count += 1
            except Exception:
                continue

        timesheet_today = "00:00:00"
        if "account.analytic.line" in self.env:
            employee = self._get_current_employee()
            if employee:
                lines = self.env["account.analytic.line"].sudo().search([
                    ("employee_id", "=", employee.id),
                    ("date", "=", today),
                ])
                total_hours = sum(lines.mapped("unit_amount"))
                timesheet_today = self._seconds_to_hhmmss(int(total_hours * 3600))

        return {
            "pending_tasks": pending_count,
            "overdue_tasks": overdue_count,
            "timesheet_today": timesheet_today,
        }

    def _get_upcoming_holidays(self):
        result = []

        if "resource.calendar.leaves" not in self.env:
            return result

        now = fields.Datetime.now()

        domain = [
            ("resource_id", "=", False),
            "|",
            ("date_from", ">=", now),
            ("date_to", ">=", now),
        ]
        if "company_id" in self.env["resource.calendar.leaves"]._fields:
            domain.append("|")
            domain.append(("company_id", "=", False))
            domain.append(("company_id", "=", self.env.company.id))

        records = self.env["resource.calendar.leaves"].sudo().search(
            domain,
            order="date_from asc",
            limit=20,
        )

        for rec in records:
            if not rec.date_from or not rec.date_to:
                continue

            date_from = rec.date_from
            date_to = rec.date_to

            duration_days = self._get_date_range_duration_days(date_from, date_to)

            result.append({
                "id": rec.id,
                "name": rec.name or "",
                "date_from": self._format_datetime_or_date(date_from),
                "date_to": self._format_datetime_or_date(date_to),
                "date_from_display": self._format_short_date(date_from),
                "date_to_display": self._format_short_date(date_to),
                "date_range_display": self._format_date_range(date_from, date_to),
                "duration_days": duration_days,
                "duration_label": _("%s day(s)") % duration_days if duration_days else "",
            })

        return result

    def _get_upcoming_events(self):
        result = []

        if "calendar.event" not in self.env:
            return result

        now = fields.Datetime.now()

        domain = [("start", ">=", now)]
        if "res_model" in self.env["calendar.event"]._fields:
            domain.append(("res_model", "!=", "hr.leave"))

        records = self.env["calendar.event"].sudo().search(
            domain,
            order="start asc",
            limit=30,
        )

        for rec in records:
            start = rec.start

            result.append({
                "id": rec.id,
                "name": rec.name or "",
                "start": self._format_datetime_or_date(start),
                "location": rec.location or "",
            })

        return result





    def _get_employee_base_domain(self):
        return [
            ("active", "=", True),
            "|",
            ("company_id", "=", False),
            ("company_id", "=", self.env.company.id),
        ]

    def _safe_make_date(self, year, month, day):
        """Safely create a date, handling Feb 29 on non-leap years."""
        try:
            return date(year, month, day)
        except ValueError:
            if month == 2 and day == 29:
                return date(year, 2, 28)
            return None

    def _get_next_occurrence(self, base_date):
        base_date = self._to_date(base_date)
        if not base_date:
            return None

        today = self._to_date(fields.Date.context_today(self))
        if not today:
            return

        next_date = self._safe_make_date(today.year, base_date.month, base_date.day)
        if not next_date:
            return None

        if next_date < today:
            next_date = self._safe_make_date(today.year + 1, base_date.month, base_date.day)

        if not next_date:
            return None

        return next_date

    def _to_date(self, value):
        """✅ Always returns a date object or None. Handles datetime, date, string."""
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







    def _get_upcoming_birthdays(self):
        result = []
        if "hr.employee" not in self.env:
            return result

        today = self._to_date(fields.Date.context_today(self))
        if not today:
            return result

        employees = self.env["hr.employee"].sudo().search(
            self._get_employee_base_domain(), order="name asc"
        )

        rows = []
        for emp in employees:
            try:
                # ✅ FIX: wrap each employee to prevent one bad record crashing all
                if "birthday" not in emp._fields or not emp.birthday:
                    continue

                birth_date = self._to_date(emp.birthday)
                if not birth_date:
                    continue

                next_birthday = self._get_next_occurrence(birth_date)
                if not next_birthday:
                    continue

                days_left = (next_birthday - today).days
                if days_left < 0 or days_left > 30:
                    continue

                rows.append({
                    "id": emp.id,
                    "name": emp.name or "",
                    "department": emp.department_id.name if emp.department_id else "",
                    "job_title": emp.job_title or "",
                    "next_date": self._format_date_only(next_birthday),
                    "days_left": days_left,
                })
            except Exception:
                continue  # ✅ Skip any employee that causes an error

        rows.sort(key=lambda x: (x["days_left"], x["name"]))
        return rows[:20]

    def _get_employee_join_date(self, employee):
        if not employee:
            return None
        if 'joining_date' in employee._fields and employee.joining_date:
            return employee.joining_date
        if 'contract_date_start' in employee._fields:
            return employee.contract_date_start
        return None

    def _get_upcoming_work_anniversaries(self):
        result = []
        if "hr.employee" not in self.env:
            return result

        today = self._to_date(fields.Date.context_today(self))
        if not today:
            return result

        employees = self.env["hr.employee"].sudo().search(
            self._get_employee_base_domain(),
            order="name asc"
        )

        rows = []
        for emp in employees:
            try:
                # ✅ FIX: wrap each employee to prevent one bad record crashing all
                join_date = self._to_date(self._get_employee_join_date(emp))
                if not join_date:
                    continue

                next_anniversary = self._get_next_occurrence(join_date)
                if not next_anniversary:
                    continue

                days_left = (next_anniversary - today).days

                if days_left < 0 or days_left > 60:
                    continue

                years = next_anniversary.year - join_date.year
                if years < 1:
                    continue

                rows.append({
                    "id": emp.id,
                    "name": emp.name or "",
                    "department": emp.department_id.name if emp.department_id else "",
                    "job_title": emp.job_title or "",
                        "next_date": self._format_date_only(next_anniversary),
                    "days_left": days_left,
                    "years": years,
                })
            except Exception:
                continue

        rows.sort(key=lambda x: (x["days_left"], x["name"]))
        return rows[:20]

    def _format_datetime_or_date(self, value):
        if not value:
            return "-"
        if hasattr(value, "hour"):
            return fields.Datetime.to_string(value)
        value = self._to_date(value)
        if not value:
            return "-"
        return value.strftime("%Y-%m-%d")

    def _format_date_only(self, value):
        if not value:
            return "-"
        if isinstance(value, str):
            return value
        value = self._to_date(value)
        if not value:
            return "-"
        return value.strftime("%Y-%m-%d")

    def _to_user_date(self, value):
        if not value:
            return False
        if hasattr(value, "hour"):
            return fields.Datetime.context_timestamp(self, value).date()
        return self._to_date(value)

    def _format_short_date(self, value):
        user_date = self._to_user_date(value)
        if not user_date:
            return "-"
        return user_date.strftime("%d-%m-%Y")

    def _format_date_range(self, date_from, date_to):
        from_text = self._format_short_date(date_from)
        to_text = self._format_short_date(date_to)
        if from_text == "-" and to_text == "-":
            return "-"
        if from_text == to_text:
            return from_text
        return "%s to %s" % (from_text, to_text)

    def _get_date_range_duration_days(self, date_from, date_to):
        if not date_from or not date_to:
            return 0
        date_from = self._to_user_date(date_from)
        date_to = self._to_user_date(date_to)
        if not date_from or not date_to:
            return 0
        return (date_to - date_from).days + 1

    def _seconds_to_hhmmss(self, total_seconds):
        total_seconds = int(total_seconds or 0)
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        return "%02d:%02d:%02d" % (hours, minutes, seconds)