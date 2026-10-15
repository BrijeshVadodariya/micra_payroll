from datetime import timedelta
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class ProjectSprint(models.Model):
    _name = "project.sprint"
    _description = "Project Sprint"
    _order = "start_date desc, id desc"

    name = fields.Char(
        string="Sprint Name",
        compute="_compute_name",
        store=True,
        readonly=False,
    )

    department_id = fields.Many2one(
        "hr.department",
        string="Department",
        required=True,
        default=lambda self: self._default_department_id(),
    )

    start_date = fields.Date(
        string="Start Date",
        required=True,
        default=lambda self: self._default_start_date(),
        help="Sprint starting Monday",
    )

    end_date = fields.Date(
        string="End Date",
        required=True,
        default=lambda self: self._default_end_date(),
        help="Sprint ending Friday",
    )

    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("active", "Active"),
            ("done", "Completed"),
        ],
        string="Status",
        default="draft",
        required=True,
        tracking=True,
    )

    task_ids = fields.One2many(
        "project.task",
        "sprint_id",
        string="Tasks",
    )

    color = fields.Integer(string="Color Index", default=0)

    is_expired = fields.Boolean(
        string="Is Expired",
        compute="_compute_is_expired",
    )

    start_day_name = fields.Char(
        string="Start Day Name",
        compute="_compute_start_day_name",
        store=True,
    )

    @api.depends("start_date")
    def _compute_start_day_name(self):
        for record in self:
            if record.start_date:
                record.start_day_name = record.start_date.strftime("%A")
            else:
                record.start_day_name = ""

    @api.depends("end_date")
    def _compute_is_expired(self):
        today = fields.Date.context_today(self)
        for record in self:
            is_expired = record.end_date < today if record.end_date else False
            record.is_expired = is_expired
            # Auto-complete the sprint if it's active and expired
            if is_expired and record.state == 'active':
                record.sudo().action_complete()

    def _default_employee_id(self):
        return self.env["hr.employee"].sudo().search(
            [("user_id", "=", self.env.user.id)],
            limit=1,
        )

    def _default_department_id(self):
        employee = self._default_employee_id()
        return employee.department_id.id if employee else False

    def _default_start_date(self):
        today = fields.Date.context_today(self)
        return today - timedelta(days=today.weekday())

    def _default_end_date(self):
        start = self._default_start_date()
        return start + timedelta(days=4) if start else False

    @api.onchange("start_date")
    def _onchange_start_date(self):
        if self.start_date:
            self.end_date = self.start_date + timedelta(days=4)

    @api.depends("department_id", "start_date")
    def _compute_name(self):
        for record in self:
            dept_name = record.department_id.name or "No Department"
            if record.start_date:
                date_str = record.start_date.strftime("%d-%m-%Y")
            else:
                date_str = "No Date"
            record.name = f"Sprint - {dept_name} ({date_str})"

    @api.constrains("start_date")
    def _check_start_date_monday(self):
        for record in self:
            if record.start_date and record.start_date.weekday() != 0:
                raise ValidationError(_("Sprint start date must be a Monday!"))

    def write(self, vals):
        res = super().write(vals)
        if "end_date" in vals:
            for record in self:
                record.task_ids.write({"date_deadline": vals["end_date"]})
        return res

    def action_start(self):
        self.ensure_one()
        self.write({"state": "active"})
        # Update deadlines of tasks in the sprint to match end_date
        if self.end_date:
            self.task_ids.write({"date_deadline": self.end_date})

    def _pull_back_tasks_from_next_sprint(self):
        self.ensure_one()
        next_start = self.start_date + timedelta(days=7)
        next_sprint = self.search(
            [
                ("department_id", "=", self.department_id.id),
                ("start_date", "=", next_start),
            ],
            limit=1,
        )
        if next_sprint:
            # Find and delete any tasks in the next sprint that were copied from this sprint
            copied_tasks = next_sprint.task_ids.filtered(
                lambda t: t.sprint_copy_source_id and t.sprint_copy_source_id.sprint_id == self
            )
            if copied_tasks:
                copied_tasks.unlink()

        # Clear carried forward status of tasks in this sprint
        self.task_ids.write({
            "is_carried_forward": False,
        })

    def action_reset_draft(self):
        self.ensure_one()
        if self.is_expired:
            raise UserError(_("You cannot reset an expired sprint to draft."))
        was_done = self.state == 'done'
        self.write({"state": "draft"})
        if was_done:
            self._pull_back_tasks_from_next_sprint()

    def action_reset_active(self):
        self.ensure_one()
        if self.is_expired:
            raise UserError(_("You cannot reset an expired sprint to active."))
        was_done = self.state == 'done'
        self.write({"state": "active"})
        if was_done:
            self._pull_back_tasks_from_next_sprint()

    @api.model
    def _cron_auto_complete_sprints(self):
        today = fields.Date.context_today(self)
        expired_sprints = self.search([
            ('state', '=', 'active'),
            ('end_date', '<', today)
        ])
        for sprint in expired_sprints:
            sprint.action_complete()

    def action_complete(self):
        self.ensure_one()
        self.write({"state": "done"})

        # Find uncompleted tasks in this sprint
        uncompleted_tasks = self.task_ids.filtered(
            lambda t: not t.stage_id.fold
            and t.stage_id.name.lower() != "completed"
        )

        if uncompleted_tasks:
            # Determine the start of the next week (Monday + 7 days)
            next_start = self.start_date + timedelta(days=7)

            # Find or create a draft/active sprint for the next week
            next_sprint = self.search(
                [
                    ("department_id", "=", self.department_id.id),
                    ("start_date", "=", next_start),
                ],
                limit=1,
            )

            if not next_sprint:
                next_sprint = self.create(
                    {
                        "department_id": self.department_id.id,
                        "start_date": next_start,
                        "state": "draft",
                    }
                )

            # Keep original tasks in the current sprint and mark them as carried forward (incomplete)
            uncompleted_tasks.write({
                "is_carried_forward": True,
            })
            # Create copies of the uncompleted tasks in the next sprint
            for task in uncompleted_tasks:
                task.copy(default={
                    "name": task.name,
                    "sprint_id": next_sprint.id,
                    "is_carried_forward": False,
                    "sprint_copy_source_id": task.id,
                })

    def action_view_tasks(self):
        self.ensure_one()
        kanban_view = self.env.ref("micra_payroll.view_task_kanban_sprint", raise_if_not_found=False)
        kanban_view_id = kanban_view.id if kanban_view else False

        return {
            "name": _("Sprint Board - %s") % self.name,
            "type": "ir.actions.act_window",
            "res_model": "project.task",
            "view_mode": "kanban,list,form",
            "views": [
                (kanban_view_id, "kanban") if kanban_view_id else (False, "kanban"),
                (False, "list"),
                (False, "form"),
            ],
            "domain": [("sprint_id", "=", self.id)],
            "context": {
                "default_sprint_id": self.id,
                "group_by": "project_id",
            },
        }

    def action_open_sprint_board(self):
        self.ensure_one()
        # Save and return the action to open the task kanban board of this sprint
        return self.action_view_tasks()
