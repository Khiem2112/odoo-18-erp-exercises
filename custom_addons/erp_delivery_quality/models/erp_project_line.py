from collections import defaultdict

from odoo import _, api, fields, models


class ErpProjectLine(models.Model):
    _inherit = "erp.project.line"

    milestone_ids = fields.One2many(
        "project.milestone", "project_line_id", string="Milestones"
    )
    quality_check_ids = fields.One2many(
        "erp.quality.check", "project_line_id", string="Quality Checklist"
    )
    quality_threshold = fields.Float(
        related="project_id.company_id.erp_quality_threshold", readonly=True
    )
    quality_task_score = fields.Float(
        compute="_compute_quality_metrics", store=True, readonly=True
    )
    quality_risk_score = fields.Float(
        compute="_compute_quality_metrics", store=True, readonly=True
    )
    quality_acceptance_score = fields.Float(
        compute="_compute_quality_metrics", store=True, readonly=True
    )
    quality_checklist_score = fields.Float(
        compute="_compute_quality_metrics", store=True, readonly=True
    )
    quality_score = fields.Float(
        compute="_compute_quality_metrics",
        store=True,
        readonly=True,
        index=True,
        digits=(5, 2),
    )
    quality_system_result = fields.Selection(
        [("passed", "Passed"), ("failed", "Failed")],
        compute="_compute_quality_metrics",
        store=True,
        readonly=True,
        index=True,
    )
    quality_blocker_summary = fields.Text(
        compute="_compute_quality_metrics", store=True, readonly=True
    )

    @api.depends(
        "state",
        "project_id.company_id.erp_quality_threshold",
        "task_ids.active",
        "task_ids.state",
        "task_ids.acceptance_state",
        "task_ids.progress_weight",
        "task_ids.is_mandatory_for_golive",
        "task_ids.risk_level",
        "task_ids.risk_status",
        "milestone_ids.is_reached",
        "milestone_ids.is_mandatory_for_golive",
        "milestone_ids.risk_level",
        "milestone_ids.risk_status",
        "quality_check_ids.weight",
        "quality_check_ids.mandatory",
        "quality_check_ids.passed",
    )
    def _compute_quality_metrics(self):
        task_weight = defaultdict(float)
        completed_task_weight = defaultdict(float)
        risk_penalty = defaultdict(float)
        checklist_weight = defaultdict(float)
        passed_checklist_weight = defaultdict(float)
        blockers = defaultdict(list)
        line_ids = self.ids

        if line_ids:
            task_model = self.env["project.task"].with_context(active_test=False)
            active_task_domain = [
                ("project_line_id", "in", line_ids),
                ("active", "=", True),
                ("state", "!=", "1_canceled"),
                ("progress_weight", ">", 0),
            ]
            for line, weight in task_model._read_group(
                active_task_domain,
                ["project_line_id"],
                ["progress_weight:sum"],
            ):
                task_weight[line.id] = weight or 0.0
            for line, weight in task_model._read_group(
                active_task_domain
                + [("state", "=", "1_done"), ("acceptance_state", "=", "accepted")],
                ["project_line_id"],
                ["progress_weight:sum"],
            ):
                completed_task_weight[line.id] = weight or 0.0

            for model_name in ("project.task", "project.milestone"):
                risk_model = self.env[model_name].with_context(active_test=False)
                for line, level, count in risk_model._read_group(
                    [
                        ("project_line_id", "in", line_ids),
                        ("risk_status", "=", "open"),
                        ("risk_level", "in", ["high", "critical"]),
                    ],
                    ["project_line_id", "risk_level"],
                    ["__count"],
                ):
                    risk_penalty[line.id] += count * (
                        10.0 if level == "critical" else 4.0
                    )

            check_model = self.env["erp.quality.check"]
            for line, weight in check_model._read_group(
                [("project_line_id", "in", line_ids)],
                ["project_line_id"],
                ["weight:sum"],
            ):
                checklist_weight[line.id] = weight or 0.0
            for line, weight in check_model._read_group(
                [("project_line_id", "in", line_ids), ("passed", "=", True)],
                ["project_line_id"],
                ["weight:sum"],
            ):
                passed_checklist_weight[line.id] = weight or 0.0

            incomplete_tasks = task_model.search(
                [
                    ("project_line_id", "in", line_ids),
                    ("is_mandatory_for_golive", "=", True),
                    "|",
                    ("state", "!=", "1_done"),
                    ("acceptance_state", "!=", "accepted"),
                ]
            )
            for task in incomplete_tasks:
                blockers[task.project_line_id.id].append(
                    _("Mandatory task is incomplete or unaccepted: %s")
                    % task.display_name
                )

            incomplete_milestones = self.env["project.milestone"].search(
                [
                    ("project_line_id", "in", line_ids),
                    ("is_mandatory_for_golive", "=", True),
                    ("is_reached", "=", False),
                ]
            )
            for milestone in incomplete_milestones:
                blockers[milestone.project_line_id.id].append(
                    _("Mandatory milestone is incomplete: %s")
                    % milestone.display_name
                )

            for model_name, label in (
                ("project.task", _("task")),
                ("project.milestone", _("milestone")),
            ):
                records = self.env[model_name].with_context(active_test=False).search(
                    [
                        ("project_line_id", "in", line_ids),
                        ("risk_level", "=", "critical"),
                        ("risk_status", "=", "open"),
                    ]
                )
                for record in records:
                    blockers[record.project_line_id.id].append(
                        _("Open Critical risk on %(kind)s: %(name)s")
                        % {"kind": label, "name": record.display_name}
                    )

            mandatory_checks = check_model.search(
                [
                    ("project_line_id", "in", line_ids),
                    ("mandatory", "=", True),
                    ("passed", "=", False),
                ]
            )
            for check in mandatory_checks:
                blockers[check.project_line_id.id].append(
                    _("Mandatory quality check has not passed: %s")
                    % check.display_name
                )

        for line in self:
            if line.state == "cancelled":
                line.quality_task_score = 0.0
                line.quality_risk_score = 0.0
                line.quality_acceptance_score = 0.0
                line.quality_checklist_score = 0.0
                line.quality_score = 0.0
                line.quality_system_result = "failed"
                line.quality_blocker_summary = _(
                    "Cancelled lines are excluded from Quality Gate evaluation."
                )
                continue

            total_task_weight = task_weight[line.id]
            task_score = (
                completed_task_weight[line.id] / total_task_weight * 50.0
                if total_task_weight
                else 0.0
            )
            risk_score = max(0.0, 20.0 - risk_penalty[line.id])
            acceptance_score = 20.0 if line.state == "accepted" else 0.0
            total_check_weight = checklist_weight[line.id]
            checklist_score = (
                passed_checklist_weight[line.id] / total_check_weight * 10.0
                if total_check_weight
                else 0.0
            )

            line_blockers = blockers[line.id]
            if line.state != "accepted":
                line_blockers.insert(0, _("The project line has not been accepted."))

            score = min(
                100.0,
                max(0.0, task_score + risk_score + acceptance_score + checklist_score),
            )
            threshold = line.project_id.company_id.erp_quality_threshold
            if score < threshold:
                line_blockers.append(
                    _("Line quality score %(score).2f is below threshold %(threshold).2f.")
                    % {"score": score, "threshold": threshold}
                )

            line.quality_task_score = min(50.0, max(0.0, task_score))
            line.quality_risk_score = min(20.0, max(0.0, risk_score))
            line.quality_acceptance_score = min(20.0, max(0.0, acceptance_score))
            line.quality_checklist_score = min(10.0, max(0.0, checklist_score))
            line.quality_score = score
            line.quality_system_result = "failed" if line_blockers else "passed"
            line.quality_blocker_summary = "\n".join(line_blockers)

    def action_view_quality_details(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Quality Score Details - %s") % self.display_name,
            "res_model": "erp.project.line",
            "res_id": self.id,
            "view_mode": "form",
            "views": [
                (
                    self.env.ref(
                        "erp_delivery_quality.view_erp_project_line_quality_detail"
                    ).id,
                    "form",
                )
            ],
            "target": "new",
        }
