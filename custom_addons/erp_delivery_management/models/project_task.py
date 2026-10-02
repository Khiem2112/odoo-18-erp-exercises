from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


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
        default="low",
        index=True,
    )
    risk_status = fields.Selection(
        [("open", "Open"), ("mitigated", "Mitigated"), ("resolved", "Resolved")],
        default="open",
        required=True,
        index=True,
    )
    progress_weight = fields.Float(default=1.0)
    acceptance_state = fields.Selection(
        [("draft", "Draft"), ("accepted", "Accepted"), ("rejected", "Rejected")],
        default="draft",
        required=True,
        index=True,
    )

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

