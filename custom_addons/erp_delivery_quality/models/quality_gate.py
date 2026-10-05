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
        string="System Result",
        required=True,
        readonly=True,
        index=True,
    )
    decision_state = fields.Selection(
        [
            ("pending", "Pending"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
        ],
        string="Manager Decision",
        required=True,
        readonly=True,
        default="pending",
        copy=False,
        index=True,
    )
    is_override = fields.Boolean(compute="_compute_is_override", store=True, readonly=True)
    is_stale = fields.Boolean(compute="_compute_is_stale", readonly=True)
    score = fields.Float(readonly=True)
    threshold = fields.Float(readonly=True)
    task_score = fields.Float(readonly=True)
    risk_score = fields.Float(readonly=True)
    line_score = fields.Float(string="Acceptance Score", readonly=True)
    checklist_score = fields.Float(readonly=True)
    quality_fingerprint_snapshot = fields.Char(readonly=True)
    evaluator_id = fields.Many2one("res.users", required=True, readonly=True, index=True)
    evaluated_at = fields.Datetime(required=True, readonly=True, index=True)
    decision_by_id = fields.Many2one("res.users", readonly=True, index=True)
    decided_at = fields.Datetime(readonly=True, index=True)
    decision_reason = fields.Text(readonly=True)
    blocker_snapshot = fields.Text(readonly=True)
    line_snapshot_ids = fields.One2many(
        "erp.quality.gate.line", "gate_id", string="Project Line Snapshots", readonly=True
    )

    @api.depends("state", "decision_state")
    def _compute_is_override(self):
        for gate in self:
            gate.is_override = gate.state == "failed" and gate.decision_state == "approved"

    @api.depends(
        "quality_fingerprint_snapshot",
        "threshold",
        "project_id.quality_fingerprint",
        "project_id.company_id.erp_quality_threshold",
    )
    def _compute_is_stale(self):
        for gate in self:
            gate.is_stale = bool(
                gate.project_id
                and (
                    gate.quality_fingerprint_snapshot
                    != gate.project_id.quality_fingerprint
                    or gate.threshold != gate.project_id.company_id.erp_quality_threshold
                )
            )

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

    def write(self, vals):
        raise AccessError(_("Quality Gate snapshots are immutable."))

    def unlink(self):
        raise AccessError(_("Quality Gate snapshots cannot be deleted."))

    @api.constrains("project_id")
    def _check_erp_project(self):
        if any(gate.project_id and not gate.project_id.is_erp_project for gate in self):
            raise ValidationError(_("Quality Gate evaluations require an ERP project."))

    @api.constrains(
        "state",
        "decision_state",
        "decision_reason",
        "decision_by_id",
        "decided_at",
    )
    def _check_decision_integrity(self):
        for gate in self:
            reason = (gate.decision_reason or "").strip()
            if gate.decision_state == "rejected" and not reason:
                raise ValidationError(_("A rejection reason is required."))
            if (
                gate.decision_state == "approved"
                and gate.state == "failed"
                and not reason
            ):
                raise ValidationError(
                    _("An override reason is required to approve a failed system result.")
                )
            if gate.decision_state != "pending" and (
                not gate.decision_by_id or not gate.decided_at
            ):
                raise ValidationError(
                    _("A decided Quality Gate must record the manager and decision time.")
                )

    def action_open_decision_wizard(self):
        self.ensure_one()
        if not self.env.user.has_group(
            "erp_delivery_management.group_erp_delivery_manager"
        ):
            raise AccessError(_("Only an ERP Delivery Manager can decide a Quality Gate."))
        decision = self.env.context.get("quality_gate_decision")
        if decision not in ("approved", "rejected"):
            raise ValidationError(_("A valid Quality Gate decision is required."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Approve Quality Gate")
            if decision == "approved"
            else _("Reject Quality Gate"),
            "res_model": "erp.quality.gate.decision.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_gate_id": self.id,
                "default_decision": decision,
            },
        }

    def _apply_decision(self, decision, reason=None):
        self.ensure_one()
        if not self.env.user.has_group(
            "erp_delivery_management.group_erp_delivery_manager"
        ):
            raise AccessError(_("Only an ERP Delivery Manager can decide a Quality Gate."))
        if decision not in ("approved", "rejected"):
            raise ValidationError(_("A valid Quality Gate decision is required."))
        if self.decision_state != "pending":
            raise ValidationError(_("Only a pending Quality Gate can be decided."))
        if self.project_id._get_latest_quality_gate() != self:
            raise ValidationError(_("Only the latest Quality Gate can be decided."))
        if self.is_stale:
            raise ValidationError(
                _("This Quality Gate is stale. Evaluate the project again before deciding.")
            )
        normalized_reason = (reason or "").strip()
        if decision == "rejected" and not normalized_reason:
            raise ValidationError(_("A rejection reason is required."))
        if decision == "approved" and self.state == "failed" and not normalized_reason:
            raise ValidationError(
                _("An override reason is required to approve a failed system result.")
            )
        super(ErpQualityGate, self).write(
            {
                "decision_state": decision,
                "decision_by_id": self.env.user.id,
                "decided_at": fields.Datetime.now(),
                "decision_reason": normalized_reason,
            }
        )
        return True


class ErpQualityGateLine(models.Model):
    _name = "erp.quality.gate.line"
    _description = "ERP Delivery Quality Gate Project Line Snapshot"
    _order = "id"
    _check_company_auto = True

    gate_id = fields.Many2one(
        "erp.quality.gate", required=True, index=True, ondelete="cascade", readonly=True
    )
    project_id = fields.Many2one(
        "project.project", related="gate_id.project_id", store=True, readonly=True, index=True
    )
    company_id = fields.Many2one(
        "res.company", related="gate_id.company_id", store=True, readonly=True, index=True
    )
    project_line_id = fields.Many2one(
        "erp.project.line", index=True, ondelete="set null", readonly=True, check_company=True
    )
    solution_name = fields.Char(required=True, readonly=True)
    consultant_name = fields.Char(readonly=True)
    state = fields.Selection(
        [("passed", "Passed"), ("failed", "Failed")],
        string="System Result",
        required=True,
        readonly=True,
        index=True,
    )
    score = fields.Float(readonly=True)
    task_score = fields.Float(readonly=True)
    risk_score = fields.Float(readonly=True)
    acceptance_score = fields.Float(readonly=True)
    checklist_score = fields.Float(readonly=True)
    blocker_snapshot = fields.Text(readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        raise AccessError(_("Quality Gate line snapshots can only be created by evaluation."))

    @api.model_create_multi
    def _create_snapshot(self, vals_list):
        return super().create(vals_list)

    def write(self, vals):
        raise AccessError(_("Quality Gate line snapshots are immutable."))

    def unlink(self):
        raise AccessError(_("Quality Gate line snapshots cannot be deleted."))
