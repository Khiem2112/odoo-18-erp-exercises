from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ErpQualityCheck(models.Model):
    _name = "erp.quality.check"
    _description = "ERP Delivery Quality Check"
    _order = "sequence, id"
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
    name = fields.Char(required=True, index=True)
    sequence = fields.Integer(default=10)
    weight = fields.Float(required=True, default=1.0)
    mandatory = fields.Boolean(default=False, index=True)
    passed = fields.Boolean(default=False, index=True)
    note = fields.Text()

    @api.constrains("weight")
    def _check_weight(self):
        if any(check.weight < 0 for check in self):
            raise ValidationError(_("Quality check weight cannot be negative."))

    @api.constrains("project_id")
    def _check_erp_project(self):
        if any(check.project_id and not check.project_id.is_erp_project for check in self):
            raise ValidationError(_("Quality checks can only belong to ERP projects."))

