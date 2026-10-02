from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ErpSolution(models.Model):
    _name = "erp.solution"
    _description = "ERP Solution"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "code, name"

    code = fields.Char(required=True, index=True, tracking=True)
    name = fields.Char(required=True, index=True, translate=True, tracking=True)
    short_description = fields.Text(translate=True)
    description = fields.Html(translate=True)
    solution_group = fields.Selection(
        [
            ("core", "Core ERP"),
            ("supply_chain", "Supply Chain"),
            ("finance", "Finance"),
            ("human_resources", "Human Resources"),
            ("custom", "Custom Development"),
        ],
        required=True,
        default="core",
        index=True,
    )
    active = fields.Boolean(default=True, index=True)
    standard_effort = fields.Float(default=0.0)
    effort_uom = fields.Selection(
        [("hour", "Hour"), ("man_day", "Man-day")],
        required=True,
        default="hour",
    )
    service_currency_id = fields.Many2one(
        "res.currency",
        required=True,
        default=lambda self: self.env.company.currency_id,
    )
    service_price = fields.Monetary(currency_field="service_currency_id", default=0.0)
    internal_cost_currency_id = fields.Many2one(
        "res.currency",
        string="Internal Cost Currency",
        company_dependent=True,
        default=lambda self: self.env.company.currency_id,
        groups="erp_delivery_management.group_erp_delivery_manager",
    )
    internal_cost = fields.Float(
        string="Internal Cost",
        company_dependent=True,
        digits="Product Price",
        default=0.0,
        groups="erp_delivery_management.group_erp_delivery_manager",
    )
    image_1920 = fields.Image(max_width=1920, max_height=1920)
    document = fields.Binary(attachment=True)
    document_filename = fields.Char()

    _sql_constraints = [
        ("code_unique", "UNIQUE(code)", "The ERP solution code must be unique.")
    ]

    @api.constrains("standard_effort", "service_price", "internal_cost")
    def _check_non_negative_values(self):
        for solution in self:
            if solution.standard_effort < 0:
                raise ValidationError(_("Standard effort cannot be negative."))
            if solution.service_price < 0:
                raise ValidationError(_("Service price cannot be negative."))
            if solution.internal_cost < 0:
                raise ValidationError(_("Internal cost cannot be negative."))

