from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


class ProjectProject(models.Model):
    _inherit = "project.project"

    quality_check_ids = fields.One2many(
        "erp.quality.check", "project_id", string="Quality Checklist"
    )
    quality_gate_ids = fields.One2many(
        "erp.quality.gate",
        "project_id",
        string="Quality Gate History",
        groups="erp_delivery_management.group_erp_delivery_consultant",
    )
    quality_task_score = fields.Float(compute="_compute_quality_score", store=True)
    quality_risk_score = fields.Float(compute="_compute_quality_score", store=True)
    quality_line_score = fields.Float(compute="_compute_quality_score", store=True)
    quality_checklist_score = fields.Float(compute="_compute_quality_score", store=True)
    quality_score = fields.Float(
        compute="_compute_quality_score", store=True, index=True, digits=(5, 2)
    )
    quality_threshold = fields.Float(
        related="company_id.erp_quality_threshold", readonly=True
    )
    quality_gate_count = fields.Integer(
        compute="_compute_quality_gate_count",
        groups="erp_delivery_management.group_erp_delivery_consultant",
    )

    @api.depends(
        "is_erp_project",
        "progress_percentage",
        "task_ids.risk_level",
        "task_ids.risk_status",
        "milestone_ids.risk_level",
        "milestone_ids.risk_status",
        "line_ids.state",
        "quality_check_ids.weight",
        "quality_check_ids.passed",
    )
    def _compute_quality_score(self):
        risk_penalty = defaultdict(float)
        active_lines = defaultdict(int)
        accepted_lines = defaultdict(int)
        checklist_weight = defaultdict(float)
        passed_checklist_weight = defaultdict(float)
        project_ids = self.ids
        if project_ids:
            for model_name in ("project.task", "project.milestone"):
                rows = self.env[model_name]._read_group(
                    [
                        ("project_id", "in", project_ids),
                        ("risk_status", "=", "open"),
                        ("risk_level", "in", ["high", "critical"]),
                    ],
                    ["project_id", "risk_level"],
                    ["__count"],
                )
                for project, level, count in rows:
                    risk_penalty[project.id] += count * (10.0 if level == "critical" else 4.0)
            for project, count in self.env["erp.project.line"]._read_group(
                [("project_id", "in", project_ids), ("state", "!=", "cancelled")],
                ["project_id"],
                ["__count"],
            ):
                active_lines[project.id] = count
            for project, count in self.env["erp.project.line"]._read_group(
                [("project_id", "in", project_ids), ("state", "=", "accepted")],
                ["project_id"],
                ["__count"],
            ):
                accepted_lines[project.id] = count
            for project, weight in self.env["erp.quality.check"]._read_group(
                [("project_id", "in", project_ids)],
                ["project_id"],
                ["weight:sum"],
            ):
                checklist_weight[project.id] = weight or 0.0
            for project, weight in self.env["erp.quality.check"]._read_group(
                [("project_id", "in", project_ids), ("passed", "=", True)],
                ["project_id"],
                ["weight:sum"],
            ):
                passed_checklist_weight[project.id] = weight or 0.0

        for project in self:
            if not project.is_erp_project:
                project.quality_task_score = 0.0
                project.quality_risk_score = 0.0
                project.quality_line_score = 0.0
                project.quality_checklist_score = 0.0
                project.quality_score = 0.0
                continue
            task_score = min(50.0, max(0.0, project.progress_percentage * 0.5))
            risk_score = max(0.0, 20.0 - risk_penalty[project.id])
            line_score = (
                accepted_lines[project.id] / active_lines[project.id] * 20.0
                if active_lines[project.id]
                else 0.0
            )
            total_check_weight = checklist_weight[project.id]
            checklist_score = (
                passed_checklist_weight[project.id] / total_check_weight * 10.0
                if total_check_weight
                else 0.0
            )
            project.quality_task_score = min(50.0, max(0.0, task_score))
            project.quality_risk_score = min(20.0, max(0.0, risk_score))
            project.quality_line_score = min(20.0, max(0.0, line_score))
            project.quality_checklist_score = min(10.0, max(0.0, checklist_score))
            project.quality_score = min(
                100.0,
                max(
                    0.0,
                    project.quality_task_score
                    + project.quality_risk_score
                    + project.quality_line_score
                    + project.quality_checklist_score,
                ),
            )

    @api.depends("quality_gate_ids")
    def _compute_quality_gate_count(self):
        counts = {}
        if self.ids:
            counts = {
                project.id: count
                for project, count in self.env["erp.quality.gate"]._read_group(
                    [("project_id", "in", self.ids)],
                    ["project_id"],
                    ["__count"],
                )
            }
        for project in self:
            project.quality_gate_count = counts.get(project.id, 0)

    def _get_go_live_blockers(self):
        self.ensure_one()
        blockers = super()._get_go_live_blockers()
        self._compute_quality_score()
        if self.quality_score < self.company_id.erp_quality_threshold:
            blockers.append(
                _("Quality score %(score).2f is below the %(threshold).2f threshold.")
                % {
                    "score": self.quality_score,
                    "threshold": self.company_id.erp_quality_threshold,
                }
            )
        failed_mandatory = self.quality_check_ids.filtered(
            lambda check: check.mandatory and not check.passed
        )
        if failed_mandatory:
            blockers.append(
                _("Mandatory quality checks have not passed: %s")
                % ", ".join(failed_mandatory.mapped("name"))
            )
        return blockers

    def action_evaluate_quality(self):
        if not self.env.user.has_group(
            "erp_delivery_management.group_erp_delivery_manager"
        ):
            raise AccessError(_("Only an ERP Delivery Manager can evaluate a Quality Gate."))
        Gate = self.env["erp.quality.gate"]
        now = fields.Datetime.now()
        gates = Gate
        for project in self:
            if not project.is_erp_project:
                raise ValidationError(_("Quality Gate evaluation requires an ERP project."))
            project._compute_quality_score()
            blockers = project._get_go_live_blockers()
            gates |= Gate._create_snapshot(
                {
                    "project_id": project.id,
                    "state": "failed" if blockers else "passed",
                    "score": project.quality_score,
                    "threshold": project.company_id.erp_quality_threshold,
                    "task_score": project.quality_task_score,
                    "risk_score": project.quality_risk_score,
                    "line_score": project.quality_line_score,
                    "checklist_score": project.quality_checklist_score,
                    "evaluator_id": self.env.user.id,
                    "evaluated_at": now,
                    "blocker_snapshot": "\n".join(blockers),
                }
            )
        if len(gates) == 1:
            return {
                "type": "ir.actions.act_window",
                "name": _("Quality Gate Evaluation"),
                "res_model": "erp.quality.gate",
                "res_id": gates.id,
                "view_mode": "form",
                "target": "current",
            }
        return True

    def action_view_quality_gates(self):
        self.ensure_one()
        if not self.env.user.has_group(
            "erp_delivery_management.group_erp_delivery_consultant"
        ):
            raise AccessError(_("Only ERP Delivery Consultants and Managers can view Quality Gates."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Quality Gate History"),
            "res_model": "erp.quality.gate",
            "view_mode": "list,form",
            "domain": [("project_id", "=", self.id)],
            "context": {"default_project_id": self.id},
        }

