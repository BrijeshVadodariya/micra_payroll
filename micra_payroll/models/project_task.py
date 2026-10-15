from datetime import timedelta
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class ProjectTask(models.Model):
    _inherit = 'project.task'

    department_id = fields.Many2one(
        'hr.department',
        string='Department',
        related='project_id.department_id',
        store=True,
        readonly=True,
        index=True,
    )

    sprint_id = fields.Many2one(
        'project.sprint',
        string='Sprint',
        ondelete='set null',
        index=True,
    )

    project_id = fields.Many2one(group_expand='_read_group_project_ids')

    sprint_department_id = fields.Many2one(
        'hr.department',
        related='sprint_id.department_id',
        string="Sprint Department",
        readonly=True,
    )

    user_ids = fields.Many2many(
        'res.users',
        default=lambda self: False,
    )

    project_allowed_user_ids = fields.Many2many(
        "res.users",
        related="project_id.allowed_user_ids",
        string="Project Allowed Users",
        readonly=True,
    )

    @api.onchange("project_id")
    def _onchange_project_id_limit_user_ids(self):
        for task in self:
            if task.project_id and task.project_allowed_user_ids:
                task.user_ids = task.user_ids.filtered(
                    lambda u: u in task.project_allowed_user_ids
                )

    @api.constrains("project_id", "user_ids")
    def _check_user_ids_in_project_allowed_users(self):
        for task in self:
            if not task.project_allowed_user_ids:
                continue

            invalid_users = task.user_ids - task.project_allowed_user_ids
            if invalid_users:
                raise ValidationError(
                    "You can assign only users selected in the project's Assignees field."
                )

    date_deadline = fields.Date(
        default=lambda self: self._default_date_deadline(),
    )

    task_start_date = fields.Date(
        string="Start Date",
        compute="_compute_task_start_date",
        store=True,
        readonly=False,
    )

    task_start_date_formatted = fields.Char(
        string="Start Date (Formatted)",
        compute="_compute_task_start_date_formatted",
    )

    is_carried_forward = fields.Boolean(
        string="Incomplete from Previous Sprint",
        default=False,
    )

    sprint_copy_source_id = fields.Many2one(
        'project.task',
        string="Sprint Copy Source",
        ondelete='set null',
        copy=False,
    )

    @api.depends('sprint_id', 'sprint_copy_source_id')
    def _compute_task_start_date(self):
        for task in self:
            if task.sprint_copy_source_id:
                task.task_start_date = task.sprint_copy_source_id.task_start_date
            elif task.sprint_id:
                task.task_start_date = task.sprint_id.start_date
            else:
                task.task_start_date = False

    @api.depends("task_start_date")
    def _compute_task_start_date_formatted(self):
        for task in self:
            if task.task_start_date:
                task.task_start_date_formatted = task.task_start_date.strftime("%d-%m-%Y")
            else:
                task.task_start_date_formatted = ""

    def _default_user_ids(self):
        return False

    def _default_date_deadline(self):
        sprint_id = self.env.context.get('default_sprint_id')
        if sprint_id:
            sprint = self.env['project.sprint'].browse(sprint_id)
            return sprint.end_date if sprint.exists() else False
        return False

    @api.onchange('project_id')
    def _onchange_project_id_assignees(self):
        pass

    date_deadline_formatted = fields.Char(
        string="Deadline (DD-MM-YYYY)",
        compute="_compute_date_deadline_formatted",
    )

    @api.depends("date_deadline")
    def _compute_date_deadline_formatted(self):
        for task in self:
            if task.date_deadline:
                task.date_deadline_formatted = task.date_deadline.strftime("%d-%m-%Y")
            else:
                task.date_deadline_formatted = ""

    completed_by_id = fields.Many2one(
        'res.users',
        string="Completed By",
        readonly=True,
        store=True,
        index=True,
    )

    completed_datetime = fields.Datetime(
        string="Completed Date & Time",
        readonly=True,
        store=True,
    )

    completed_datetime_formatted = fields.Char(
        string="Completed Date/Time",
        compute="_compute_completed_datetime_formatted",
    )

    @api.depends("completed_datetime")
    def _compute_completed_datetime_formatted(self):
        for task in self:
            if task.completed_datetime:
                local_dt = fields.Datetime.context_timestamp(task, task.completed_datetime)
                task.completed_datetime_formatted = local_dt.strftime("%d-%m-%Y %H:%M:%S")
            else:
                task.completed_datetime_formatted = ""

    existing_task_id = fields.Many2one(
        'project.task',
        string="Select Existing Task",
        store=False,
    )

    @api.onchange('existing_task_id')
    def _onchange_existing_task_id(self):
        if self.existing_task_id:
            self.name = self.existing_task_id.name
            self.project_id = self.existing_task_id.project_id
            self.user_ids = self.existing_task_id.user_ids
            if self.sprint_id:
                self.date_deadline = self.sprint_id.end_date
            else:
                self.date_deadline = self.existing_task_id.date_deadline

    priority_level = fields.Selection([
        ('1_high', 'High Priority'),
        ('2_medium', 'Medium Priority'),
        ('3_low', 'Low Priority')
    ], string='Priority Level', default='3_low')

    def action_toggle_priority_level(self):
        for task in self:
            if task.priority_level == '3_low' or not task.priority_level:
                task.priority_level = '2_medium'
            elif task.priority_level == '2_medium':
                task.priority_level = '1_high'
            else:
                task.priority_level = '3_low'

    timer_running = fields.Boolean(string="Timer Running", default=False)
    timer_paused = fields.Boolean(string="Timer Paused", default=False, copy=False)

    timer_start = fields.Datetime(string="Timer Start", readonly=True, copy=False)
    timer_pause_time = fields.Datetime(string="Paused At", readonly=True, copy=False)
    timer_stop = fields.Datetime(string="Timer Stop", readonly=True, copy=False)

    timer_total_paused_seconds = fields.Integer(
        string="Total Paused Seconds",
        default=0,
        readonly=True,
        copy=False,
    )

    timer_user_id = fields.Many2one('res.users', string="Started By", readonly=True, copy=False)
    timer_employee_id = fields.Many2one('hr.employee', string="Employee", readonly=True, copy=False)

    is_timer_allowed_user = fields.Boolean(
        string="Can Use Timer",
        compute="_compute_is_timer_allowed_user",
        store=False,
    )

    timer_display = fields.Char(
        string="Live Timer",
        compute="_compute_timer_display",
        store=False,
    )

    timer_duration = fields.Float(
        string="Current Duration",
        compute="_compute_timer_duration",
        store=False,
    )

    @api.model
    def get_my_running_timer(self):
        task = self.search([
            ('timer_user_id', '=', self.env.user.id),
            '|',
            ('timer_running', '=', True),
            ('timer_paused', '=', True),
        ], limit=1)

        if not task:
            return {
                'running': False,
                'paused': False,
                'task_id': False,
                'task_name': '',
                'timer_start': False,
                'timer_pause_time': False,
                'paused_seconds': 0,
            }

        return {
            'running': bool(task.timer_running),
            'paused': bool(task.timer_paused),
            'task_id': task.id,
            'task_name': task.display_name,
            'timer_start': fields.Datetime.to_string(task.timer_start) if task.timer_start else False,
            'timer_pause_time': fields.Datetime.to_string(task.timer_pause_time) if task.timer_pause_time else False,
            'paused_seconds': int(task.timer_total_paused_seconds or 0),
        }

    def _get_employee_from_user(self, user):
        employee = self.env['hr.employee'].sudo().search([('user_id', '=', user.id)], limit=1)
        if not employee:
            raise UserError(_("No employee is linked with the current user '%s'.") % user.name)
        return employee

    def _get_project_stage_by_name(self, project, stage_name):
        return self.env["project.task.type"].sudo().search([
            ("name", "=", stage_name),
            ("project_ids", "in", project.id),
        ], limit=1)

    def _set_stage_by_assignment(self):
        for task in self:
            if not task.project_id:
                continue

            unassigned_stage = task._get_project_stage_by_name(task.project_id, "Unassigned")
            open_stage = task._get_project_stage_by_name(task.project_id, "Open")

            if not unassigned_stage:
                continue

            if not task.user_ids:
                if task.stage_id.id != unassigned_stage.id:
                    task.stage_id = unassigned_stage.id
            else:
                if open_stage and task.stage_id.id == unassigned_stage.id:
                    task.stage_id = open_stage.id

    @api.onchange('user_ids', 'project_id')
    def _onchange_user_ids_move_stage(self):
        for task in self:
            if not task.project_id:
                continue

            unassigned_stage = task._get_project_stage_by_name(task.project_id, "Unassigned")
            open_stage = task._get_project_stage_by_name(task.project_id, "Open")

            if not task.user_ids:
                if unassigned_stage:
                    task.stage_id = unassigned_stage.id
            else:
                if open_stage and (
                    not task.stage_id or
                    (unassigned_stage and task.stage_id.id == unassigned_stage.id)
                ):
                    task.stage_id = open_stage.id

    @api.onchange('sprint_id')
    def _onchange_sprint_id(self):
        for task in self:
            if task.sprint_id:
                task.date_deadline = task.sprint_id.end_date
                current_start = task.task_start_date or (task._origin.sprint_id.start_date if task._origin and task._origin.sprint_id else False)
                if not current_start or (task.sprint_id.start_date and current_start and task.sprint_id.start_date < current_start):
                    task.task_start_date = task.sprint_id.start_date
                else:
                    task.task_start_date = current_start

    @api.model_create_multi
    def create(self, vals_list):
        created_records = self.env['project.task']
        new_vals_list = []
        for vals in vals_list:
            if vals.get('sprint_id'):
                sprint = self.env['project.sprint'].browse(vals['sprint_id'])
                if sprint:
                    vals['date_deadline'] = sprint.end_date
            if vals.get('stage_id'):
                stage = self.env['project.task.type'].browse(vals['stage_id'])
                if stage and (stage.fold or (stage.name and stage.name.lower() == 'completed')):
                    vals['completed_by_id'] = self.env.user.id
                    vals['completed_datetime'] = fields.Datetime.now()

            if vals.get('existing_task_id'):
                existing_task = self.browse(vals['existing_task_id'])
                sprint_id = vals.get('sprint_id') or self.env.context.get('default_sprint_id')
                write_vals = {
                    'sprint_id': sprint_id,
                }
                if sprint_id:
                    sprint = self.env['project.sprint'].browse(sprint_id)
                    if sprint:
                        write_vals['date_deadline'] = sprint.end_date
                if vals.get('user_ids'):
                    write_vals['user_ids'] = vals.get('user_ids')
                existing_task.write(write_vals)
                created_records += existing_task
            else:
                new_vals_list.append(vals)

        if new_vals_list:
            created_records += super().create(new_vals_list)

        created_records._set_stage_by_assignment()
        return created_records

    def write(self, vals):
        if 'sprint_id' in vals:
            sprint = self.env['project.sprint'].browse(vals['sprint_id']) if vals['sprint_id'] else False
            if sprint:
                vals['date_deadline'] = sprint.end_date
        if 'stage_id' in vals:
            if vals.get('stage_id'):
                stage = self.env['project.task.type'].browse(vals['stage_id'])
                if stage and (stage.fold or (stage.name and stage.name.lower() == 'completed')):
                    vals['completed_by_id'] = self.env.user.id
                    vals['completed_datetime'] = fields.Datetime.now()
                else:
                    vals['completed_by_id'] = False
                    vals['completed_datetime'] = False
            else:
                vals['completed_by_id'] = False
                vals['completed_datetime'] = False
        result = super().write(vals)

        if 'user_ids' in vals or 'project_id' in vals:
            self._set_stage_by_assignment()

        return result

    def unlink(self):
        is_dept_manager = self.env.user.has_group("micra_payroll.group_project_department_manager")
        if is_dept_manager and not self.env.user.has_group("project.group_project_manager"):
            raise ValidationError(_("Deletion is not allowed."))
        return super().unlink()

    def _get_open_attendance_for_user(self, user):
        employee = self.env['hr.employee'].sudo().search([('user_id', '=', user.id)], limit=1)
        if not employee:
            raise UserError(_("No employee is linked with the current user '%s'.") % user.name)

        attendance = self.env['hr.attendance'].search([
            ('employee_id', '=', employee.id),
            ('check_out', '=', False),
        ], limit=1, order='check_in desc')

        return employee, attendance

    def _check_user_can_start_timer_by_attendance(self):
        employee, attendance = self._get_open_attendance_for_user(self.env.user)

        if not attendance:
            raise UserError(_("Please first Check In to start timer."))

        if attendance.is_on_break:
            raise UserError(_("Please Break Out first to start timer."))

        return employee, attendance

    @api.depends('user_ids')
    def _compute_is_timer_allowed_user(self):
        current_user = self.env.user
        for task in self:
            task.is_timer_allowed_user = current_user in task.user_ids

    def _compute_effective_duration_seconds(self, ref_time=None):
        self.ensure_one()

        if not self.timer_start:
            return 0

        ref_time = fields.Datetime.to_datetime(ref_time) if ref_time else fields.Datetime.now()
        timer_start = fields.Datetime.to_datetime(self.timer_start)

        if not ref_time or not timer_start:
            return 0

        total_seconds = max(0, int((ref_time - timer_start).total_seconds()))
        total_seconds -= int(self.timer_total_paused_seconds or 0)

        if self.timer_paused and self.timer_pause_time:
            pause_time = fields.Datetime.to_datetime(self.timer_pause_time)
            if pause_time:
                current_pause_seconds = max(0, int((ref_time - pause_time).total_seconds()))
                total_seconds -= current_pause_seconds

        return max(0, total_seconds)

    @api.depends(
        'timer_running',
        'timer_paused',
        'timer_start',
        'timer_pause_time',
        'timer_total_paused_seconds',
    )
    def _compute_timer_display(self):
        now = fields.Datetime.now()
        for task in self:
            if (task.timer_running or task.timer_paused) and task.timer_start:
                total_seconds = task._compute_effective_duration_seconds(ref_time=now)
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                seconds = total_seconds % 60
                task.timer_display = "%02d:%02d:%02d" % (hours, minutes, seconds)
            else:
                task.timer_display = "00:00:00"

    @api.depends(
        'timer_running',
        'timer_paused',
        'timer_start',
        'timer_pause_time',
        'timer_total_paused_seconds',
    )
    def _compute_timer_duration(self):
        now = fields.Datetime.now()
        for task in self:
            if (task.timer_running or task.timer_paused) and task.timer_start:
                task.timer_duration = task._compute_effective_duration_seconds(ref_time=now) / 3600.0
            else:
                task.timer_duration = 0.0

    def _check_assigned_user(self):
        for task in self:
            if self.env.user not in task.user_ids:
                raise UserError(_("Only assigned users can use this timer."))

    def _check_stop_cancel_owner(self):
        for task in self:
            if (task.timer_running or task.timer_paused) and task.timer_user_id and task.timer_user_id != self.env.user:
                raise UserError(_("Only the user who started the timer can stop, pause, resume, or cancel it."))

    def _clear_timer_fields(self, stop_time=False):
        stop_time = fields.Datetime.to_datetime(stop_time) if stop_time else fields.Datetime.now()
        self.write({
            'timer_running': False,
            'timer_paused': False,
            'timer_start': False,
            'timer_pause_time': False,
            'timer_stop': stop_time,
            'timer_total_paused_seconds': 0,
            'timer_user_id': False,
            'timer_employee_id': False,
        })

    @api.model
    def _auto_pause_running_timer_for_employee(self, employee, pause_time=False):
        if not employee:
            return True

        pause_time = fields.Datetime.to_datetime(pause_time) if pause_time else fields.Datetime.now()

        if employee.user_id:
            domain = ['|',
                '&', ('timer_running', '=', True), ('timer_user_id', '=', employee.user_id.id),
                '&', ('timer_running', '=', True), ('timer_employee_id', '=', employee.id),
            ]
        else:
            domain = [
                ('timer_running', '=', True),
                ('timer_employee_id', '=', employee.id),
            ]

        running_tasks = self.search(domain)

        for task in running_tasks:
            task.write({
                'timer_running': False,
                'timer_paused': True,
                'timer_pause_time': pause_time,
                'timer_stop': False,
            })

        return True

    @api.model
    def _auto_stop_running_timer_for_employee(self, employee, stop_time=False):
        if not employee:
            return True

        stop_time = fields.Datetime.to_datetime(stop_time) if stop_time else fields.Datetime.now()
        AnalyticLine = self.env['account.analytic.line']

        if employee.user_id:
            domain = ['|',
                '&', ('timer_user_id', '=', employee.user_id.id),
                    '|', ('timer_running', '=', True), ('timer_paused', '=', True),
                '&', ('timer_employee_id', '=', employee.id),
                    '|', ('timer_running', '=', True), ('timer_paused', '=', True),
            ]
        else:
            domain = [
                ('timer_employee_id', '=', employee.id),
                '|', ('timer_running', '=', True), ('timer_paused', '=', True),
            ]

        timer_tasks = self.search(domain)

        for task in timer_tasks:
            if not task.timer_start:
                task._clear_timer_fields(stop_time=stop_time)
                continue

            duration_seconds = task._compute_effective_duration_seconds(ref_time=stop_time)
            duration_hours = duration_seconds / 3600.0

            if duration_hours > 0 and task.project_id and task.project_id.account_id:
                AnalyticLine.sudo().create({
                    'name': task.name or _('Task Timer Entry'),
                    'project_id': task.project_id.id,
                    'task_id': task.id,
                    'account_id': task.project_id.account_id.id,
                    'employee_id': task.timer_employee_id.id or employee.id,
                    'user_id': task.timer_user_id.id or (employee.user_id.id if employee.user_id else self.env.user.id),
                    'unit_amount': duration_hours,
                    'date': fields.Date.context_today(self),
                })

            task._clear_timer_fields(stop_time=stop_time)

        return True

    def action_start_timer(self):
        for task in self:
            task._check_assigned_user()

            if task.timer_running:
                raise UserError(_("Timer is already running for this task."))

            if task.timer_paused:
                raise UserError(_("This task timer is paused. Please use Resume Timer."))

            existing_task = self.search([
                ('timer_user_id', '=', self.env.user.id),
                ('id', '!=', task.id),
                '|',
                ('timer_running', '=', True),
                ('timer_paused', '=', True),
            ], limit=1)

            if existing_task:
                raise UserError(_(
                    "You already have a running or paused timer on task '%s'. Please stop, cancel, or resume that first."
                ) % existing_task.display_name)

            if not task.project_id:
                raise UserError(_("Please select a project on this task first."))

            employee, attendance = task._check_user_can_start_timer_by_attendance()

            task.write({
                'timer_running': True,
                'timer_paused': False,
                'timer_start': fields.Datetime.now(),
                'timer_pause_time': False,
                'timer_stop': False,
                'timer_total_paused_seconds': 0,
                'timer_user_id': self.env.user.id,
                'timer_employee_id': employee.id,
            })

        return True

    def action_pause_timer(self):
        for task in self:
            task._check_assigned_user()
            task._check_stop_cancel_owner()

            if not task.timer_running or not task.timer_start:
                raise UserError(_("No running timer found for this task."))

            task.write({
                'timer_running': False,
                'timer_paused': True,
                'timer_pause_time': fields.Datetime.now(),
                'timer_stop': False,
            })

        return True

    def action_resume_timer(self):
        for task in self:
            task._check_assigned_user()
            task._check_stop_cancel_owner()

            if not task.timer_paused:
                raise UserError(_("No paused timer found for this task."))

            employee, attendance = task._get_open_attendance_for_user(self.env.user)

            if not attendance:
                raise UserError(_("Please first Check In to resume timer."))

            if attendance.is_on_break:
                raise UserError(_("Please Break Out first to resume timer."))

            pause_time = fields.Datetime.to_datetime(task.timer_pause_time) if task.timer_pause_time else fields.Datetime.now()
            paused_seconds = max(0, int((fields.Datetime.now() - pause_time).total_seconds()))

            task.write({
                'timer_running': True,
                'timer_paused': False,
                'timer_pause_time': False,
                'timer_total_paused_seconds': int(task.timer_total_paused_seconds or 0) + paused_seconds,
                'timer_stop': False,
                'timer_employee_id': employee.id,
            })

        return True

    def action_stop_timer(self):
        AnalyticLine = self.env['account.analytic.line']

        for task in self:
            task._check_assigned_user()
            task._check_stop_cancel_owner()

            if (not task.timer_running and not task.timer_paused) or not task.timer_start:
                raise UserError(_("No running or paused timer found for this task."))

            if not task.project_id:
                raise UserError(_("Please select a project on this task first."))

            if not task.project_id.account_id:
                raise UserError(_(
                    "The project '%s' does not have an analytic account, so timesheet entry cannot be created."
                ) % task.project_id.display_name)

            stop_time = fields.Datetime.now()
            duration_seconds = task._compute_effective_duration_seconds(ref_time=stop_time)
            duration_hours = duration_seconds / 3600.0

            if duration_hours <= 0:
                raise UserError(_("Timer duration must be greater than zero."))

            employee = task.timer_employee_id or task._get_employee_from_user(self.env.user)

            AnalyticLine.sudo().create({
                'name': task.name or _('Task Timer Entry'),
                'project_id': task.project_id.id,
                'task_id': task.id,
                'account_id': task.project_id.account_id.id,
                'employee_id': employee.id,
                'user_id': task.timer_user_id.id or self.env.user.id,
                'unit_amount': duration_hours,
                'date': fields.Date.context_today(self),
            })

            task._clear_timer_fields(stop_time=stop_time)

        return True

    def action_cancel_timer(self):
        for task in self:
            task._check_assigned_user()
            task._check_stop_cancel_owner()

            if not task.timer_running and not task.timer_paused:
                raise UserError(_("No running or paused timer found to cancel."))

            task._clear_timer_fields(stop_time=fields.Datetime.now())

        return True

    @api.model
    def _read_group_project_ids(self, values, domain):
        try:
            with open('d:/odoo19/odoo-19.0/domain_log.txt', 'a') as f:
                f.write(f"DOMAIN: {domain}\n")
        except Exception:
            pass
        
        sprint_id = False
        for arg in domain:
            if isinstance(arg, (list, tuple)) and len(arg) == 3 and arg[0] == 'sprint_id' and arg[1] in ('=', 'in'):
                sprint_id = arg[2]
                break
        
        if sprint_id:
            if isinstance(sprint_id, (list, tuple)):
                sprint_id = sprint_id[0] if sprint_id else False
            
            sprint = self.env['project.sprint'].browse(sprint_id)
            if sprint.exists() and sprint.department_id:
                projects = self.env['project.project'].sudo().search([
                    ('department_id', '=', sprint.department_id.id),
                    ('name', 'not ilike', 'Internal'),
                    '|',
                    ('company_id', '=', self.env.company.id),
                    ('company_id', '=', False)
                ])
                return projects
        
        return values



