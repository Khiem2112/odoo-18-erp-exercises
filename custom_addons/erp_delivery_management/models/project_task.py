from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


class ProjectTask(models.Model):
    _inherit = "project.task"
    _check_company_auto = True

    is_erp_delivery_task = fields.Boolean(
        related="project_id.is_erp_project", store=True, readonly=True, index=True
    )
    project_line_id = fields.Many2one(
        "erp.project.line",
        string="ERP Project Line",
        index=True,
        ondelete="set null",
        check_company=True,
    )
    is_mandatory_for_golive = fields.Boolean(
        string="Mandatory for Go-live", index=True, default=False
    )
    risk_level = fields.Selection(
        [
            ("low", "Low"),
            ("medium", "Medium"),
            ("high", "High"),
            ("critical", "Critical"),
        ],
        string="Risk Level",
        index=True,
    )
    risk_status = fields.Selection(
        [("open", "Open"), ("mitigated", "Mitigated"), ("resolved", "Resolved")],
        string="Risk Status",
        index=True,
    )
    progress_weight = fields.Float(string="Progress Weight", default=1.0)
    acceptance_state = fields.Selection(
        [("draft", "Draft"), ("accepted", "Accepted"), ("rejected", "Rejected")],
        string="Acceptance State",
        default="draft",
        required=True,
        index=True,
        tracking=True,
    )
    can_manage_acceptance = fields.Boolean(
        compute="_compute_can_manage_acceptance",
        string="Can Manage Acceptance",
    )

    @api.depends_context("uid")
    @api.depends("project_id.user_id")
    def _compute_can_manage_acceptance(self):
        is_manager = self.env.user.has_group(
            "erp_delivery_management.group_erp_delivery_manager"
        )
        for task in self:
            task.can_manage_acceptance = is_manager or (
                task.project_id and task.project_id.user_id == self.env.user
            )

    @api.onchange("risk_level")
    def _onchange_risk_level(self):
        if self.risk_level and not self.risk_status:
            self.risk_status = "open"
        elif not self.risk_level:
            self.risk_status = False

    @api.constrains("project_id", "project_line_id")
    def _check_project_line_project(self):
        for task in self:
            if task.project_line_id and task.project_line_id.project_id != task.project_id:
                raise ValidationError(
                    _("The ERP project line must belong to the task's project.")
                )

    @api.constrains("progress_weight")
    def _check_progress_weight(self):
        if any(task.progress_weight < 0 for task in self):
            raise ValidationError(_("Task progress weight cannot be negative."))

    def _check_acceptance_permission(self):
        is_manager = self.env.user.has_group(
            "erp_delivery_management.group_erp_delivery_manager"
        )
        for task in self:
            if not task.is_erp_delivery_task:
                continue
            is_pm = task.project_id and task.project_id.user_id == self.env.user
            if not (is_manager or is_pm):
                raise AccessError(
                    _("Only an ERP Delivery Manager or the Project Manager can accept or reject tasks.")
                )

    def action_accept(self):
        self._check_acceptance_permission()
        return self.write({
            "acceptance_state": "accepted",
            "state": "1_done",
        })

    def action_reject(self):
        self._check_acceptance_permission()
        return self.write({
            "acceptance_state": "rejected",
            "state": "02_changes_requested",
        })

    def action_reset_acceptance(self):
        self._check_acceptance_permission()
        return self.write({
            "acceptance_state": "draft",
        })

    def write(self, vals):
        if "acceptance_state" in vals:
            to_check = self.filtered(
                lambda t: t.is_erp_delivery_task and t.acceptance_state != vals["acceptance_state"]
            )
            if to_check:
                to_check._check_acceptance_permission()
        return super().write(vals)

