from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


def _has_dept_manager_group(env):
    return env.user.has_group("micra_payroll.group_project_department_manager")


class ResUsers(models.Model):
    _inherit = "res.users"

    project_department_id = fields.Many2one(
        "hr.department",
        string="Project Department",
        compute="_compute_project_department_id",
        compute_sudo=True,
        store=False,
    )

    project_role_custom = fields.Selection(
        [
            ("none", "No Access"),
            ("user", "User"),
            ("manager", "Project Manager"),
            ("admin", "Administrator"),
        ],
        string="Project Custom Role",
        compute="_compute_project_role_custom",
        inverse="_inverse_project_role_custom",
        store=False,
    )

    def _compute_project_role_custom(self):
        group_user = self.env.ref("project.group_project_user", raise_if_not_found=False)
        group_admin = self.env.ref("project.group_project_manager", raise_if_not_found=False)
        group_manager = self.env.ref("micra_payroll.group_project_department_manager", raise_if_not_found=False)

        for user in self:
            if group_admin and group_admin in user.groups_id:
                user.project_role_custom = "admin"
            elif group_manager and group_manager in user.groups_id:
                user.project_role_custom = "manager"
            elif group_user and group_user in user.groups_id:
                user.project_role_custom = "user"
            else:
                user.project_role_custom = "none"

    def _inverse_project_role_custom(self):
        group_user = self.env.ref("project.group_project_user", raise_if_not_found=False)
        group_admin = self.env.ref("project.group_project_manager", raise_if_not_found=False)
        group_manager = self.env.ref("micra_payroll.group_project_department_manager", raise_if_not_found=False)

        for user in self:
            remove_groups = []
            if group_user:
                remove_groups.append(group_user.id)
            if group_admin:
                remove_groups.append(group_admin.id)
            if group_manager:
                remove_groups.append(group_manager.id)

            vals = [(3, gid) for gid in remove_groups]

            if user.project_role_custom == "user" and group_user:
                vals.append((4, group_user.id))
            elif user.project_role_custom == "manager":
                if group_user:
                    vals.append((4, group_user.id))
                if group_manager:
                    vals.append((4, group_manager.id))
            elif user.project_role_custom == "admin":
                if group_admin:
                    vals.append((4, group_admin.id))

            user.sudo().write({"groups_id": vals})

    def _compute_project_department_id(self):
        employees = self.env["hr.employee"].sudo().search([("user_id", "in", self.ids)])
        emp_map = {emp.user_id.id: emp.department_id.id for emp in employees}
        for user in self:
            user.project_department_id = emp_map.get(user.id, False)


class ProjectProject(models.Model):
    _inherit = 'project.project'

    allowed_user_ids = fields.Many2many(
        "res.users",
        "project_allowed_user_rel",
        "project_id",
        "user_id",
        string="Assignees",
        domain="[('company_ids', 'in', allowed_company_ids), ('share', '=', False)]",
        help="Only these users should access the project.",
    )

    total_timesheet_hours = fields.Float(
        string="Total Time Spent (Hours)",
        compute="_compute_total_timesheet_hours",
        store=False,
    )

    total_timesheet_display = fields.Char(
        string="Total Time Spent",
        compute="_compute_total_timesheet_hours",
        store=False,
    )

    department_id = fields.Many2one(
        "hr.department",
        string="Department",
        index=True,
        default=lambda self: self._default_department_id(),
    )

    def _default_department_id(self):
        return self._get_current_user_department().id if self._get_current_user_department() else False

    def _get_current_user_employee(self):
        return self.env['hr.employee'].sudo().search(
            [('user_id', '=', self.env.user.id)],
            limit=1,
        )

    def _get_current_user_department(self):
        employee = self._get_current_user_employee()
        return employee.department_id if employee else False

    @api.constrains("allowed_user_ids")
    def _check_allowed_users(self):
        for record in self:
            if not record.allowed_user_ids:
                raise ValidationError(
                    "Please select employee for particular project."
                )

    def _sync_allowed_users_followers(self):
        for project in self:
            allowed_partners = project.allowed_user_ids.mapped("partner_id")
            current_partners = project.message_partner_ids

            remove_partners = current_partners - allowed_partners
            if remove_partners:
                project.message_unsubscribe(partner_ids=remove_partners.ids)

            add_partners = allowed_partners - current_partners
            if add_partners:
                project.message_subscribe(partner_ids=add_partners.ids)

    @api.depends('task_ids.timesheet_ids.unit_amount')
    def _compute_total_timesheet_hours(self):
        for project in self:
            total_hours = sum(project.task_ids.mapped('timesheet_ids.unit_amount')) or 0.0
            project.total_timesheet_hours = total_hours

            total_seconds = int(round(total_hours * 3600))
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60

            project.total_timesheet_display = "%02d:%02d:%02d" % (hours, minutes, seconds)

    def _ensure_analytic_account_for_projects(self):
        AnalyticAccount = self.env['account.analytic.account'].sudo()
        for project in self:
            if not project.account_id:
                analytic = AnalyticAccount.create({
                    'name': project.name,
                    'company_id': project.company_id.id if project.company_id else False,
                })
                project.sudo().write({'account_id': analytic.id})

    def _create_default_stages_for_projects(self):
        stage_data = [
            {"name": "Unassigned", "sequence": 1, "fold": False},
            {"name": "Open", "sequence": 2, "fold": False},
            {"name": "In Progress", "sequence": 3, "fold": False},
            {"name": "On Hold", "sequence": 4, "fold": False},
            {"name": "QA", "sequence": 5, "fold": False},
            {"name": "Completed", "sequence": 6, "fold": False},
        ]

        TaskStage = self.env["project.task.type"].sudo()

        for project in self:
            for stage in stage_data:
                existing_stage = TaskStage.search([
                    ("name", "=", stage["name"]),
                    ("project_ids", "in", project.id),
                ], limit=1)

                if existing_stage:
                    existing_stage.write({
                        "sequence": stage["sequence"],
                        "fold": False,
                    })
                    continue

                common_stage = TaskStage.search([
                    ("name", "=", stage["name"]),
                ], limit=1)

                if common_stage:
                    common_stage.write({
                        "project_ids": [(4, project.id)],
                        "sequence": stage["sequence"],
                        "fold": False,
                    })
                else:
                    TaskStage.create({
                        "name": stage["name"],
                        "sequence": stage["sequence"],
                        "fold": False,
                        "project_ids": [(4, project.id)],
                    })

    @api.model_create_multi
    def create(self, vals_list):
        is_department_manager = (
            _has_dept_manager_group(self.env)
            and not self.env.user.has_group("project.group_project_manager")
        )
        user_department = self._get_current_user_department()

        if is_department_manager and not user_department:
            raise ValidationError(
                _("Current user does not have an employee department assigned.")
            )

        for vals in vals_list:
            if "privacy_visibility" in self._fields:
                vals["privacy_visibility"] = "followers"

            if is_department_manager:
                vals["department_id"] = user_department.id
            elif not vals.get("department_id") and user_department:
                vals["department_id"] = user_department.id

        projects = super().create(vals_list)

        # Sync allowed users to project followers
        projects._sync_allowed_users_followers()

        # Create analytic account with sudo if missing
        projects._ensure_analytic_account_for_projects()

        # Create default task stages with sudo
        projects._create_default_stages_for_projects()

        return projects

    def write(self, vals):
        if "privacy_visibility" in self._fields:
            vals["privacy_visibility"] = "followers"

        is_department_manager = (
            _has_dept_manager_group(self.env)
            and not self.env.user.has_group("project.group_project_manager")
        )
        if is_department_manager:
            user_department = self._get_current_user_department()
            if not user_department:
                raise ValidationError(
                    _("Current user does not have an employee department assigned.")
                )

            if "department_id" in vals and vals["department_id"] != user_department.id:
                raise ValidationError(
                    _("You can only manage projects of your own department.")
                )

        res = super().write(vals)

        if "allowed_user_ids" in vals or "privacy_visibility" in vals:
            self._sync_allowed_users_followers()

        return res

    def unlink(self):
        if _has_dept_manager_group(self.env) and not self.env.user.has_group("project.group_project_manager"):
            raise ValidationError(_("Deletion is not allowed."))
        return super().unlink()