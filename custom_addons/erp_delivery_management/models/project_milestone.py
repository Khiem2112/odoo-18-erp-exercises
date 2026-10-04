from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ProjectMilestone(models.Model):
    _inherit = "project.milestone"
    _check_company_auto = True

    company_id = fields.Many2one(
        "res.company",
        related="project_id.company_id",
        store=True,
        readonly=True,
        index=True,
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
    is_erp_delivery_milestone = fields.Boolean(
        related="project_id.is_erp_project", store=True, readonly=True, index=True
    )

    @api.onchange("risk_level")
    def _onchange_risk_level(self):
        if self.risk_level and not self.risk_status:
            self.risk_status = "open"
        elif not self.risk_level:
            self.risk_status = False

    @api.constrains("project_id", "project_line_id")
    def _check_project_line_project(self):
        for milestone in self:
            if (
                milestone.project_line_id
                and milestone.project_line_id.project_id != milestone.project_id
            ):
                raise ValidationError(
                    _("The ERP project line must belong to the milestone's project.")
                )
