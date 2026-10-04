from collections import defaultdict
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


ERP_DELIVERY_STATES = [
    ("draft", "Draft"),
    ("analysis", "Analysis"),
    ("development", "Development"),
    ("uat", "UAT"),
    ("ready", "Ready for Go-live"),
    ("live", "Live"),
    ("completed", "Completed"),
    ("cancelled", "Cancelled"),
]

ALLOWED_TRANSITIONS = {
    "draft": {"analysis", "cancelled"},
    "analysis": {"development", "cancelled"},
    "development": {"uat", "cancelled"},
    "uat": {"development", "ready", "cancelled"},
    "ready": {"live", "cancelled"},
    "live": {"completed"},
    "completed": set(),
    "cancelled": {"draft"},
}


class ProjectProject(models.Model):
    _inherit = "project.project"
    _check_company_auto = True

    is_erp_project = fields.Boolean(string="ERP Delivery Project", index=True, default=False)
    code = fields.Char(string="ERP Project Code", copy=False, readonly=True, index=True)
    team_member_ids = fields.Many2many(
        "res.users",
        "erp_project_team_user_rel",
        "project_id",
        "user_id",
        string="ERP Delivery Team",
        domain=[("share", "=", False)],
    )
    date_golive_planned = fields.Date(
        string="Planned Go-live", index=True, tracking=True
    )
    date_golive_actual = fields.Date(
        string="Actual Go-live", copy=False, readonly=True, tracking=True
    )
    duration_days = fields.Integer(
        string="Duration (Days)",
        compute="_compute_duration_days",
        inverse="_inverse_duration_days",
        store=True,
        readonly=False,
    )
    contract_currency_id = fields.Many2one(
        "res.currency",
        string="Contract Currency",
        default=lambda self: self.env.company.currency_id,
        groups="erp_delivery_management.group_erp_delivery_consultant",
    )
    contract_value = fields.Monetary(
        currency_field="contract_currency_id",
        tracking=True,
        groups="erp_delivery_management.group_erp_delivery_consultant",
    )
    internal_notes = fields.Text(
        groups="erp_delivery_management.group_erp_delivery_consultant"
    )
    delivery_state = fields.Selection(
        ERP_DELIVERY_STATES,
        required=True,
        default="draft",
        copy=False,
        tracking=True,
        index=True,
    )
    cancellation_reason = fields.Text(copy=False, tracking=True)
    line_ids = fields.One2many("erp.project.line", "project_id", string="ERP Solutions")
    solution_count = fields.Integer(
        compute="_compute_line_aggregates", store=True, string="Solution Count"
    )
    total_expected_effort = fields.Float(
        compute="_compute_line_aggregates", store=True, string="Expected Effort"
    )
    total_actual_effort = fields.Float(
        compute="_compute_line_aggregates", store=True, string="Actual Effort"
    )
    mandatory_task_count = fields.Integer(
        compute="_compute_task_aggregates", store=True
    )
    mandatory_task_done_count = fields.Integer(
        compute="_compute_task_aggregates", store=True
    )
    progress_percentage = fields.Float(
        compute="_compute_task_aggregates",
        store=True,
        digits=(5, 2),
        index=True,
    )
    health_state = fields.Selection(
        [("green", "Green"), ("amber", "Amber"), ("red", "Red")],
        compute="_compute_health_state",
        store=True,
        index=True,
        default="green",
    )
    # Primary customer relation is inherited via partner_id (Many2one to res.partner) from project.project.
    # customer_ref_code is a stored related field for reporting aggregates and indexed fast search.
    customer_ref_code = fields.Char(
        related="partner_id.ref_code", store=True, readonly=True, index=True
    )

    _sql_constraints = [
        (
            "erp_delivery_code_unique",
            "UNIQUE(code)",
            "The ERP project code must be unique.",
        )
    ]

    @api.depends("date_start", "date_golive_planned")
    def _compute_duration_days(self):
        for project in self:
            if project.date_start and project.date_golive_planned:
                project.duration_days = (
                    project.date_golive_planned - project.date_start
                ).days
            else:
                project.duration_days = 0

    def _inverse_duration_days(self):
        for project in self:
            if project.duration_days < 0:
                raise ValidationError(_("Project duration cannot be negative."))
            if project.date_start:
                project.date_golive_planned = project.date_start + timedelta(
                    days=project.duration_days
                )
            elif project.duration_days:
                raise ValidationError(
                    _("A start date is required before entering project duration.")
                )

    @api.depends(
        "line_ids",
        "line_ids.state",
        "line_ids.expected_effort",
        "line_ids.actual_effort",
    )
    def _compute_line_aggregates(self):
        values = {}
        if self.ids:
            rows = self.env["erp.project.line"]._read_group(
                [("project_id", "in", self.ids), ("state", "!=", "cancelled")],
                ["project_id"],
                ["__count", "expected_effort:sum", "actual_effort:sum"],
            )
            values = {
                project.id: (count, expected or 0.0, actual or 0.0)
                for project, count, expected, actual in rows
            }
        for project in self:
            count, expected, actual = values.get(project.id, (0, 0.0, 0.0))
            project.solution_count = count
            project.total_expected_effort = expected
            project.total_actual_effort = actual

    @api.depends(
        "task_ids",
        "task_ids.state",
        "task_ids.acceptance_state",
        "task_ids.progress_weight",
        "task_ids.is_mandatory_for_golive",
    )
    def _compute_task_aggregates(self):
        mandatory = defaultdict(int)
        mandatory_done = defaultdict(int)
        total_weight = defaultdict(float)
        done_weight = defaultdict(float)
        if self.ids:
            Task = self.env["project.task"]
            for project, count in Task._read_group(
                [("project_id", "in", self.ids), ("is_mandatory_for_golive", "=", True)],
                ["project_id"],
                ["__count"],
            ):
                mandatory[project.id] = count
            for project, count in Task._read_group(
                [
                    ("project_id", "in", self.ids),
                    ("is_mandatory_for_golive", "=", True),
                    ("state", "=", "1_done"),
                    ("acceptance_state", "=", "accepted"),
                ],
                ["project_id"],
                ["__count"],
            ):
                mandatory_done[project.id] = count
            for project, weight in Task._read_group(
                [("project_id", "in", self.ids), ("state", "!=", "1_canceled")],
                ["project_id"],
                ["progress_weight:sum"],
            ):
                total_weight[project.id] = weight or 0.0
            for project, weight in Task._read_group(
                [("project_id", "in", self.ids), ("state", "=", "1_done")],
                ["project_id"],
                ["progress_weight:sum"],
            ):
                done_weight[project.id] = weight or 0.0
        for project in self:
            project.mandatory_task_count = mandatory[project.id]
            project.mandatory_task_done_count = mandatory_done[project.id]
            denominator = total_weight[project.id]
            progress = done_weight[project.id] / denominator * 100.0 if denominator else 0.0
            project.progress_percentage = min(100.0, max(0.0, progress))

    @api.depends(
        "date_start",
        "date_golive_planned",
        "progress_percentage",
        "mandatory_task_count",
        "mandatory_task_done_count",
        "task_ids.state",
        "task_ids.date_deadline",
        "task_ids.is_mandatory_for_golive",
        "task_ids.risk_level",
        "task_ids.risk_status",
        "milestone_ids.is_reached",
        "milestone_ids.deadline",
        "milestone_ids.is_mandatory_for_golive",
        "milestone_ids.risk_level",
        "milestone_ids.risk_status",
    )
    def _compute_health_state(self):
        project_ids = self.ids
        red_risk_ids = set()
        high_risk_ids = set()
        overdue_ids = set()
        incomplete_milestone_ids = set()
        if project_ids:
            Task = self.env["project.task"]
            Milestone = self.env["project.milestone"]
            today = fields.Date.context_today(self)
            now = fields.Datetime.now()

            def grouped_project_ids(model, domain):
                return {
                    project.id
                    for project, _count in model._read_group(
                        [("project_id", "in", project_ids)] + domain,
                        ["project_id"],
                        ["__count"],
                    )
                }

            red_risk_ids = grouped_project_ids(
                Task, [("risk_level", "=", "critical"), ("risk_status", "=", "open")]
            ) | grouped_project_ids(
                Milestone,
                [("risk_level", "=", "critical"), ("risk_status", "=", "open")],
            )
            high_risk_ids = grouped_project_ids(
                Task, [("risk_level", "=", "high"), ("risk_status", "=", "open")]
            ) | grouped_project_ids(
                Milestone,
                [("risk_level", "=", "high"), ("risk_status", "=", "open")],
            )
            overdue_ids = grouped_project_ids(
                Task,
                [
                    ("is_mandatory_for_golive", "=", True),
                    ("state", "!=", "1_done"),
                    ("date_deadline", "<", now),
                ],
            ) | grouped_project_ids(
                Milestone,
                [
                    ("is_mandatory_for_golive", "=", True),
                    ("is_reached", "=", False),
                    ("deadline", "<", today),
                ],
            )
            incomplete_milestone_ids = grouped_project_ids(
                Milestone,
                [("is_mandatory_for_golive", "=", True), ("is_reached", "=", False)],
            )

        today = fields.Date.context_today(self)
        for project in self:
            if not project.is_erp_project:
                project.health_state = "green"
                continue
            planned_progress = 0.0
            if project.date_start and project.date_golive_planned:
                total_days = (project.date_golive_planned - project.date_start).days
                if total_days <= 0:
                    planned_progress = 100.0 if today >= project.date_golive_planned else 0.0
                else:
                    elapsed = (today - project.date_start).days
                    planned_progress = min(100.0, max(0.0, elapsed / total_days * 100.0))
            gap = planned_progress - project.progress_percentage
            mandatory_incomplete = (
                project.mandatory_task_count != project.mandatory_task_done_count
                or project.id in incomplete_milestone_ids
            )
            past_golive_incomplete = bool(
                project.date_golive_planned
                and project.date_golive_planned < today
                and mandatory_incomplete
            )
            if project.id in red_risk_ids or gap > 20.0 or past_golive_incomplete:
                project.health_state = "red"
            elif project.id in high_risk_ids or 10.0 <= gap <= 20.0 or project.id in overdue_ids:
                project.health_state = "amber"
            else:
                project.health_state = "green"

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("is_erp_project"):
                if vals.get("delivery_state", "draft") != "draft":
                    raise ValidationError(_("A new ERP project must start in Draft."))
                if vals.get("date_golive_actual"):
                    raise ValidationError(_("Actual Go-live is set only by the Go-live action."))
                self._validate_duration_payload(vals)
                company = self.env["res.company"].browse(vals.get("company_id")) or self.env.company
                vals.setdefault("contract_currency_id", company.currency_id.id)
                sequence_date = fields.Date.to_date(vals.get("date_start")) or fields.Date.context_today(self)
                vals["code"] = (
                    self.env["ir.sequence"]
                    .with_company(company)
                    .next_by_code("erp.delivery.project", sequence_date=sequence_date)
                )
                vals.setdefault("allow_milestones", True)
        return super().create(vals_list)

    def write(self, vals):
        erp_projects = self.filtered("is_erp_project")
        becoming_erp = self.filtered(
            lambda project: vals.get("is_erp_project") and not project.is_erp_project
        )
        protected_projects = erp_projects | becoming_erp
        if "is_erp_project" in vals:
            if not self.env.user.has_group(
                "erp_delivery_management.group_erp_delivery_manager"
            ):
                raise AccessError(_("Only an ERP Delivery Manager can change the ERP project marker."))
            if not vals["is_erp_project"] and erp_projects:
                raise ValidationError(_("An ERP project cannot be converted into a regular project."))
            if becoming_erp:
                raise ValidationError(
                    _("Create a new ERP delivery project instead of converting an existing project.")
                )
        if protected_projects:
            protected_projects._validate_duration_payload(vals)
            if "code" in vals:
                raise ValidationError(_("The ERP project code is generated automatically and cannot be changed."))
            if "date_golive_actual" in vals:
                raise AccessError(_("Actual Go-live is controlled by the Go-live action."))
            if "delivery_state" in vals:
                target = vals["delivery_state"]
                for project in erp_projects:
                    project._validate_delivery_transition(target, vals)
        result = super().write(vals)
        return result

    def copy(self, default=None):
        default = dict(default or {})
        default.update(
            {
                "code": False,
                "delivery_state": "draft",
                "date_golive_actual": False,
                "cancellation_reason": False,
            }
        )
        return super().copy(default)

    # Clear customer when changing project company if partner belongs to previous company
    @api.onchange("company_id")
    def _onchange_company_id(self):
        if self.partner_id and self.partner_id.company_id != self.company_id:
            self.partner_id = False

    def _validate_duration_payload(self, vals):
        if "duration_days" not in vals or "date_golive_planned" not in vals:
            return
        duration = vals.get("duration_days") or 0
        planned = fields.Date.to_date(vals.get("date_golive_planned"))
        for project in self or self.browse():
            start = fields.Date.to_date(vals.get("date_start")) or project.date_start
            if start and planned and planned != start + timedelta(days=duration):
                raise ValidationError(
                    _("Duration and planned Go-live date are inconsistent.")
                )
        if not self:
            start = fields.Date.to_date(vals.get("date_start"))
            if start and planned and planned != start + timedelta(days=duration):
                raise ValidationError(
                    _("Duration and planned Go-live date are inconsistent.")
                )

    def _validate_delivery_transition(self, target, vals=None):
        self.ensure_one()
        if target == self.delivery_state:
            return
        if target not in ALLOWED_TRANSITIONS.get(self.delivery_state, set()):
            raise ValidationError(
                _("Transition from %(source)s to %(target)s is not allowed.")
                % {"source": self.delivery_state, "target": target}
            )
        is_manager = self.env.user.has_group(
            "erp_delivery_management.group_erp_delivery_manager"
        )
        manager_targets = {"ready", "live", "cancelled"}
        if self.delivery_state == "cancelled" or target in manager_targets:
            if not is_manager:
                raise AccessError(_("Only an ERP Delivery Manager can perform this transition."))
        elif not is_manager and self.user_id != self.env.user:
            raise AccessError(_("Only the Project Manager or a Delivery Manager can change phase."))
        if target == "cancelled":
            reason = (vals or {}).get("cancellation_reason") or self.cancellation_reason
            if not reason:
                raise ValidationError(_("A cancellation reason is required."))
        if target == "ready":
            blockers = self._get_ready_blockers()
            if blockers:
                raise ValidationError(
                    _("The project is not ready for Go-live:\n%s") % "\n".join(blockers)
                )

    @api.constrains(
        "is_erp_project",
        "code",
        "company_id",
        "partner_id",
        "user_id",
        "team_member_ids",
        "date_start",
        "date_golive_planned",
        "date_golive_actual",
        "contract_currency_id",
        "contract_value",
        "delivery_state",
        "cancellation_reason",
    )
    def _check_erp_project_data(self):
        for project in self.filtered("is_erp_project"):
            if not project.code:
                raise ValidationError(_("An ERP project code is required."))
            if not project.company_id:
                raise ValidationError(_("An ERP project must belong to a company."))
            if not project.contract_currency_id:
                raise ValidationError(_("An ERP project contract currency is required."))
            if not project.partner_id:
                raise ValidationError(_("An ERP project customer is required."))
            if project.partner_id and not project.partner_id.is_erp_customer:
                raise ValidationError(_("The project customer must be marked as an ERP customer."))
            if project.partner_id and project.partner_id.company_id != project.company_id:
                raise ValidationError(_("The ERP customer must belong to the project company."))
            if project.user_id and project.company_id not in project.user_id.company_ids:
                raise ValidationError(_("The Project Manager must have access to the project company."))
            invalid_members = project.team_member_ids.filtered(
                lambda user: project.company_id not in user.company_ids
            )
            if invalid_members:
                raise ValidationError(_("Every team member must have access to the project company."))
            if (
                project.date_start
                and project.date_golive_planned
                and project.date_golive_planned < project.date_start
            ):
                raise ValidationError(_("Planned Go-live cannot precede the start date."))
            if (
                project.date_start
                and project.date_golive_actual
                and project.date_golive_actual < project.date_start
            ):
                raise ValidationError(_("Actual Go-live cannot precede the start date."))
            if project.contract_value < 0:
                raise ValidationError(_("Contract value cannot be negative."))
            if project.delivery_state == "cancelled" and not project.cancellation_reason:
                raise ValidationError(_("A cancellation reason is required."))

    def _get_ready_blockers(self):
        self.ensure_one()
        blockers = []
        if not self.partner_id:
            blockers.append(_("Customer is required."))
        if not self.user_id:
            blockers.append(_("Project Manager is required."))
        if not self.date_golive_planned:
            blockers.append(_("Planned Go-live date is required."))
        if self.date_start and self.date_golive_planned and self.date_golive_planned < self.date_start:
            blockers.append(_("Planned Go-live cannot precede the start date."))
        if not self.line_ids.filtered(lambda line: line.state != "cancelled"):
            blockers.append(_("At least one active ERP solution line is required."))
        incomplete_tasks = self.env["project.task"].with_context(active_test=False).search(
            [
                ("project_id", "=", self.id),
                ("is_mandatory_for_golive", "=", True),
                "|",
                ("state", "!=", "1_done"),
                ("acceptance_state", "!=", "accepted"),
            ]
        )
        if incomplete_tasks:
            blockers.append(
                _("Mandatory tasks are incomplete or unaccepted: %s")
                % ", ".join(incomplete_tasks.mapped("name"))
            )
        incomplete_milestones = self.env["project.milestone"].search(
            [
                ("project_id", "=", self.id),
                ("is_mandatory_for_golive", "=", True),
                ("is_reached", "=", False),
            ]
        )
        if incomplete_milestones:
            blockers.append(
                _("Mandatory milestones are incomplete: %s")
                % ", ".join(incomplete_milestones.mapped("name"))
            )
        critical_tasks = self.env["project.task"].with_context(active_test=False).search(
            [
                ("project_id", "=", self.id),
                ("risk_level", "=", "critical"),
                ("risk_status", "=", "open"),
            ]
        )
        critical_milestones = self.env["project.milestone"].search(
            [
                ("project_id", "=", self.id),
                ("risk_level", "=", "critical"),
                ("risk_status", "=", "open"),
            ]
        )
        if critical_tasks or critical_milestones:
            blockers.append(_("All open Critical risks must be resolved."))
        return blockers

    def _get_go_live_blockers(self):
        self.ensure_one()
        return self._get_ready_blockers()

    def _check_go_live_conditions(self):
        self.ensure_one()
        return self._get_go_live_blockers()

    def action_go_live(self):
        if not self.env.user.has_group(
            "erp_delivery_management.group_erp_delivery_manager"
        ):
            raise AccessError(_("Only an ERP Delivery Manager can approve Go-live."))
        all_blockers = []
        for project in self:
            if not project.is_erp_project or project.delivery_state != "ready":
                all_blockers.append(_("%s must be an ERP project in Ready state.") % project.display_name)
                continue
            all_blockers.extend(
                _("%(project)s: %(blocker)s")
                % {"project": project.display_name, "blocker": blocker}
                for blocker in project._check_go_live_conditions()
            )
        if all_blockers:
            raise UserError(_("Go-live is blocked:\n%s") % "\n".join(all_blockers))
        today = fields.Date.context_today(self)
        for project in self:
            project._validate_delivery_transition("live")
        super(ProjectProject, self).write(
            {"delivery_state": "live", "date_golive_actual": today}
        )
        for project in self:
            project.message_post(body=_("ERP project went live on %s.") % today)
        return True

    def action_start_analysis(self):
        return self.write({"delivery_state": "analysis"})

    def action_start_development(self):
        return self.write({"delivery_state": "development"})

    def action_start_uat(self):
        return self.write({"delivery_state": "uat"})

    def action_mark_ready(self):
        return self.write({"delivery_state": "ready"})

    def action_complete(self):
        return self.write({"delivery_state": "completed"})

    def action_cancel_delivery(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Cancel ERP Project"),
            "res_model": "erp.project.cancel.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_project_id": self.id,
            },
        }

    def action_cancel_with_reason(self, reason):
        self.ensure_one()
        return self.write(
            {
                "cancellation_reason": reason,
                "delivery_state": "cancelled",
            }
        )

    def action_restore_delivery(self):
        return self.write({"delivery_state": "draft", "cancellation_reason": False})

    @api.model
    def _cron_recompute_erp_health(self):
        domain = [
            ("is_erp_project", "=", True),
            ("delivery_state", "not in", ["completed", "cancelled"]),
        ]
        last_id = 0
        while True:
            projects = self.search(
                domain + [("id", ">", last_id)], order="id", limit=1000
            )
            if not projects:
                break
            projects._compute_health_state()
            last_id = projects[-1].id
        return True

