from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ErpProjectLine(models.Model):
    _name = "erp.project.line"
    _description = "ERP Project Solution Line"
    _order = "project_id, id"
    _check_company_auto = True

    project_id = fields.Many2one(
        "project.project",
        required=True,
        index=True,
        ondelete="cascade",
        check_company=True,
        domain=[("is_erp_project", "=", True)],
    )
    company_id = fields.Many2one(
        "res.company",
        related="project_id.company_id",
        store=True,
        readonly=True,
        index=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        related="project_id.contract_currency_id",
        store=True,
        readonly=True,
    )
    solution_id = fields.Many2one(
        "erp.solution",
        required=True,
        index=True,
        ondelete="restrict",
    )
    consultant_id = fields.Many2one(
        "res.users",
        index=True,
        domain=[("share", "=", False)],
    )
    expected_effort = fields.Float(default=0.0)
    actual_effort = fields.Float(default=0.0)
    sale_price = fields.Monetary(
        currency_field="currency_id",
        default=0.0,
        groups="erp_delivery_management.group_erp_delivery_consultant",
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("in_progress", "In Progress"),
            ("accepted", "Accepted"),
            ("cancelled", "Cancelled"),
        ],
        required=True,
        default="draft",
        index=True,
    )
    technical_notes = fields.Text(
        groups="erp_delivery_management.group_erp_delivery_consultant"
    )
    task_ids = fields.One2many("project.task", "project_line_id", string="Tasks")

    @api.depends("solution_id.code", "solution_id.name", "consultant_id.name")
    def _compute_display_name(self):
        for line in self:
            parts = []
            if line.solution_id.code:
                parts.append(f"[{line.solution_id.code}]")
            if line.solution_id.name:
                parts.append(line.solution_id.name)
            if line.consultant_id:
                parts.append(f"({line.consultant_id.name})")
            line.display_name = " ".join(parts) if parts else _("Line #%s") % line.id

    _sql_constraints = [
        (
            "project_solution_unique",
            "UNIQUE(project_id, solution_id)",
            "A solution can only be added once to an ERP project.",
        )
    ]

    @api.constrains("expected_effort", "actual_effort", "sale_price")
    def _check_non_negative_values(self):
        for line in self:
            if line.expected_effort < 0 or line.actual_effort < 0:
                raise ValidationError(_("Project line effort cannot be negative."))
            if line.sale_price < 0:
                raise ValidationError(_("Project line sale price cannot be negative."))

    @api.constrains("project_id", "consultant_id")
    def _check_consultant_company(self):
        for line in self:
            if (
                line.consultant_id
                and line.project_id.company_id
                and line.project_id.company_id not in line.consultant_id.company_ids
            ):
                raise ValidationError(
                    _("The consultant must have access to the project's company.")
                )

