from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


class ErpQualityGate(models.Model):
    _name = "erp.quality.gate"
    _description = "ERP Delivery Quality Gate Evaluation"
    _order = "evaluated_at desc, id desc"
    _check_company_auto = True

    name = fields.Char(required=True, copy=False, readonly=True, default="New", index=True)
    project_id = fields.Many2one(
        "project.project",
        required=True,
        index=True,
        ondelete="cascade",
        check_company=True,
        domain=[("is_erp_project", "=", True)],
        readonly=True,
    )
    company_id = fields.Many2one(
        "res.company",
        related="project_id.company_id",
        store=True,
        readonly=True,
        index=True,
    )
    state = fields.Selection(
        [("passed", "Passed"), ("failed", "Failed")],
        required=True,
        readonly=True,
        index=True,
    )
    score = fields.Float(readonly=True)
    threshold = fields.Float(readonly=True)
    task_score = fields.Float(readonly=True)
    risk_score = fields.Float(readonly=True)
    line_score = fields.Float(readonly=True)
    checklist_score = fields.Float(readonly=True)
    evaluator_id = fields.Many2one("res.users", required=True, readonly=True, index=True)
    evaluated_at = fields.Datetime(required=True, readonly=True, index=True)
    blocker_snapshot = fields.Text(readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        raise AccessError(_("Quality Gate snapshots can only be created by evaluation."))

    @api.model_create_multi
    def _create_snapshot(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                company = self.env["res.company"].browse(vals.get("company_id"))
                if not company and vals.get("project_id"):
                    company = self.env["project.project"].browse(
                        vals["project_id"]
                    ).company_id
                vals["name"] = (
                    self.env["ir.sequence"]
                    .with_company(company or self.env.company)
                    .next_by_code("erp.delivery.quality.gate")
                    or "New"
                )
        return super().create(vals_list)

    @api.constrains("project_id")
    def _check_erp_project(self):
        if any(gate.project_id and not gate.project_id.is_erp_project for gate in self):
            raise ValidationError(_("Quality Gate evaluations require an ERP project."))

