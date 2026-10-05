import hashlib
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
    quality_task_score = fields.Float(
        compute="_compute_quality_score", store=True, readonly=True
    )
    quality_risk_score = fields.Float(
        compute="_compute_quality_score", store=True, readonly=True
    )
    quality_line_score = fields.Float(
        string="Quality Acceptance Score",
        compute="_compute_quality_score",
        store=True,
        readonly=True,
    )
    quality_checklist_score = fields.Float(
        compute="_compute_quality_score", store=True, readonly=True
    )
    quality_score = fields.Float(
        compute="_compute_quality_score",
        store=True,
        readonly=True,
        index=True,
        digits=(5, 2),
    )
    quality_threshold = fields.Float(
        related="company_id.erp_quality_threshold", readonly=True
    )
    quality_system_result = fields.Selection(
        [("passed", "Passed"), ("failed", "Failed")],
        compute="_compute_quality_status",
        store=True,
        readonly=True,
        index=True,
    )
    quality_blocker_summary = fields.Text(
        compute="_compute_quality_status", store=True, readonly=True
    )
    quality_fingerprint = fields.Char(
        compute="_compute_quality_fingerprint",
        store=True,
        readonly=True,
        copy=False,
    )
    quality_approval_state = fields.Selection(
        [
            ("not_evaluated", "Not Evaluated"),
            ("pending", "Pending"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
            ("stale", "Re-evaluation Required"),
        ],
        compute="_compute_quality_approval_state",
        string="Quality Approval",
    )
    quality_gate_count = fields.Integer(
        compute="_compute_quality_gate_count",
        groups="erp_delivery_management.group_erp_delivery_consultant",
    )

    @api.depends(
        "is_erp_project",
        "line_ids.state",
        "line_ids.expected_effort",
        "line_ids.quality_task_score",
        "line_ids.quality_risk_score",
        "line_ids.quality_acceptance_score",
        "line_ids.quality_checklist_score",
        "line_ids.quality_score",
    )
    def _compute_quality_score(self):
        for project in self:
            active_lines = project.line_ids.filtered(lambda line: line.state != "cancelled")
            if not project.is_erp_project or not active_lines:
                project.quality_task_score = 0.0
                project.quality_risk_score = 0.0
                project.quality_line_score = 0.0
                project.quality_checklist_score = 0.0
                project.quality_score = 0.0
                continue

            total_effort = sum(active_lines.mapped("expected_effort"))
            if total_effort > 0:
                def weighted(field_name):
                    return sum(
                        line[field_name] * line.expected_effort for line in active_lines
                    ) / total_effort
            else:
                line_count = len(active_lines)

                def weighted(field_name):
                    return sum(active_lines.mapped(field_name)) / line_count

            project.quality_task_score = min(
                50.0, max(0.0, weighted("quality_task_score"))
            )
            project.quality_risk_score = min(
                20.0, max(0.0, weighted("quality_risk_score"))
            )
            project.quality_line_score = min(
                20.0, max(0.0, weighted("quality_acceptance_score"))
            )
            project.quality_checklist_score = min(
                10.0, max(0.0, weighted("quality_checklist_score"))
            )
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

    @api.depends(
        "is_erp_project",
        "company_id.erp_quality_threshold",
        "line_ids",
        "line_ids.solution_id",
        "line_ids.state",
        "line_ids.expected_effort",
        "task_ids",
        "task_ids.active",
        "task_ids.project_line_id",
        "task_ids.state",
        "task_ids.acceptance_state",
        "task_ids.progress_weight",
        "task_ids.is_mandatory_for_golive",
        "task_ids.risk_level",
        "task_ids.risk_status",
        "milestone_ids",
        "milestone_ids.project_line_id",
        "milestone_ids.is_reached",
        "milestone_ids.is_mandatory_for_golive",
        "milestone_ids.risk_level",
        "milestone_ids.risk_status",
        "quality_check_ids",
        "quality_check_ids.project_line_id",
        "quality_check_ids.weight",
        "quality_check_ids.mandatory",
        "quality_check_ids.passed",
    )
    def _compute_quality_fingerprint(self):
        line_values = defaultdict(list)
        task_values = defaultdict(list)
        milestone_values = defaultdict(list)
        check_values = defaultdict(list)
        project_ids = self.ids

        if project_ids:
            lines = self.env["erp.project.line"].search(
                [("project_id", "in", project_ids)]
            )
            for line in lines:
                line_values[line.project_id.id].append(
                    (
                        line.id,
                        line.solution_id.id,
                        line.state,
                        line.expected_effort,
                    )
                )

            tasks = self.env["project.task"].with_context(active_test=False).search(
                [("project_id", "in", project_ids)]
            )
            for task in tasks:
                task_values[task.project_id.id].append(
                    (
                        task.id,
                        task.active,
                        task.project_line_id.id,
                        task.state,
                        task.acceptance_state,
                        task.progress_weight,
                        task.is_mandatory_for_golive,
                        task.risk_level,
                        task.risk_status,
                    )
                )

            milestones = self.env["project.milestone"].search(
                [("project_id", "in", project_ids)]
            )
            for milestone in milestones:
                milestone_values[milestone.project_id.id].append(
                    (
                        milestone.id,
                        milestone.project_line_id.id,
                        milestone.is_reached,
                        milestone.is_mandatory_for_golive,
                        milestone.risk_level,
                        milestone.risk_status,
                    )
                )

            checks = self.env["erp.quality.check"].search(
                [("project_id", "in", project_ids)]
            )
            for check in checks:
                check_values[check.project_id.id].append(
                    (
                        check.id,
                        check.project_line_id.id,
                        check.weight,
                        check.mandatory,
                        check.passed,
                    )
                )

        for project in self:
            if not project.is_erp_project:
                project.quality_fingerprint = False
                continue
            payload = (
                "erp-delivery-quality-v2",
                project.company_id.erp_quality_threshold,
                tuple(sorted(line_values[project.id])),
                tuple(sorted(task_values[project.id])),
                tuple(sorted(milestone_values[project.id])),
                tuple(sorted(check_values[project.id])),
            )
            project.quality_fingerprint = hashlib.sha256(
                repr(payload).encode("utf-8")
            ).hexdigest()

    @api.depends(
        "is_erp_project",
        "quality_score",
        "company_id.erp_quality_threshold",
        "line_ids.state",
        "line_ids.quality_system_result",
        "line_ids.quality_blocker_summary",
        "task_ids.active",
        "task_ids.project_line_id",
        "task_ids.state",
        "task_ids.acceptance_state",
        "task_ids.is_mandatory_for_golive",
        "task_ids.risk_level",
        "task_ids.risk_status",
        "milestone_ids.project_line_id",
        "milestone_ids.is_reached",
        "milestone_ids.is_mandatory_for_golive",
        "milestone_ids.risk_level",
        "milestone_ids.risk_status",
        "quality_check_ids.project_line_id",
        "quality_check_ids.mandatory",
        "quality_check_ids.passed",
    )
    def _compute_quality_status(self):
        blockers_by_project = self._get_quality_blockers_map()
        for project in self:
            blockers = (
                blockers_by_project.get(project.id, [])
                if project.is_erp_project
                else []
            )
            project.quality_system_result = "failed" if blockers else "passed"
            project.quality_blocker_summary = "\n".join(blockers)

    @api.depends(
        "quality_gate_ids",
        "quality_gate_ids.decision_state",
        "quality_gate_ids.quality_fingerprint_snapshot",
        "quality_fingerprint",
        "company_id.erp_quality_threshold",
    )
    def _compute_quality_approval_state(self):
        latest_by_project = {}
        if self.ids:
            gates = self.env["erp.quality.gate"].search(
                [("project_id", "in", self.ids)],
                order="evaluated_at desc, id desc",
            )
            for gate in gates:
                latest_by_project.setdefault(gate.project_id.id, gate)
        for project in self:
            gate = latest_by_project.get(project.id)
            if not gate:
                project.quality_approval_state = "not_evaluated"
            elif gate.is_stale:
                project.quality_approval_state = "stale"
            else:
                project.quality_approval_state = gate.decision_state

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

    def _get_quality_blockers_map(self):
        projects = self.filtered("is_erp_project")
        blockers_by_project = defaultdict(list)
        project_ids = projects.ids
        if not project_ids:
            return blockers_by_project

        active_lines_by_project = defaultdict(lambda: self.env["erp.project.line"])
        active_lines = self.env["erp.project.line"].search(
            [
                ("project_id", "in", project_ids),
                ("state", "!=", "cancelled"),
            ],
            order="project_id, id",
        )
        for line in active_lines:
            active_lines_by_project[line.project_id.id] |= line

        for project in projects:
            project_lines = active_lines_by_project[project.id]
            if not project_lines:
                blockers_by_project[project.id].append(
                    _("At least one active ERP solution line is required.")
                )

        for line in active_lines.filtered(
            lambda candidate: candidate.quality_system_result == "failed"
        ):
            detail = line.quality_blocker_summary or _("Quality requirements are not met.")
            blockers_by_project[line.project_id.id].append(
                _("%(line)s: %(detail)s")
                % {
                    "line": line.display_name,
                    "detail": detail.replace("\n", "; "),
                }
            )

        incomplete_tasks = self.env["project.task"].with_context(active_test=False).search(
            [
                ("project_id", "in", project_ids),
                ("project_line_id", "=", False),
                ("is_mandatory_for_golive", "=", True),
                "|",
                ("state", "!=", "1_done"),
                ("acceptance_state", "!=", "accepted"),
            ],
            order="project_id, id",
        )
        incomplete_tasks_by_project = defaultdict(list)
        for task in incomplete_tasks:
            incomplete_tasks_by_project[task.project_id.id].append(task.name)
        for project_id, names in incomplete_tasks_by_project.items():
            blockers_by_project[project_id].append(
                _("Project-wide mandatory tasks are incomplete or unaccepted: %s")
                % ", ".join(names)
            )

        incomplete_milestones = self.env["project.milestone"].search(
            [
                ("project_id", "in", project_ids),
                ("project_line_id", "=", False),
                ("is_mandatory_for_golive", "=", True),
                ("is_reached", "=", False),
            ],
            order="project_id, id",
        )
        incomplete_milestones_by_project = defaultdict(list)
        for milestone in incomplete_milestones:
            incomplete_milestones_by_project[milestone.project_id.id].append(
                milestone.name
            )
        for project_id, names in incomplete_milestones_by_project.items():
            blockers_by_project[project_id].append(
                _("Project-wide mandatory milestones are incomplete: %s")
                % ", ".join(names)
            )

        critical_names_by_project = defaultdict(list)
        for model_name in ("project.task", "project.milestone"):
            critical_records = (
                self.env[model_name]
                .with_context(active_test=False)
                .search(
                    [
                        ("project_id", "in", project_ids),
                        ("project_line_id", "=", False),
                        ("risk_level", "=", "critical"),
                        ("risk_status", "=", "open"),
                    ],
                    order="project_id, id",
                )
            )
            for record in critical_records:
                critical_names_by_project[record.project_id.id].append(record.name)
        for project_id, names in critical_names_by_project.items():
            blockers_by_project[project_id].append(
                _("Project-wide Critical risks are still open: %s")
                % ", ".join(names)
            )

        failed_project_checks = self.env["erp.quality.check"].search(
            [
                ("project_id", "in", project_ids),
                ("project_line_id", "=", False),
                ("mandatory", "=", True),
                ("passed", "=", False),
            ],
            order="project_id, id",
        )
        failed_checks_by_project = defaultdict(list)
        for check in failed_project_checks:
            failed_checks_by_project[check.project_id.id].append(check.name)
        for project_id, names in failed_checks_by_project.items():
            blockers_by_project[project_id].append(
                _("Mandatory project quality checks have not passed: %s")
                % ", ".join(names)
            )

        for project in projects:
            if project.quality_score >= project.company_id.erp_quality_threshold:
                continue
            blockers_by_project[project.id].append(
                _("Project quality score %(score).2f is below threshold %(threshold).2f.")
                % {
                    "score": project.quality_score,
                    "threshold": project.company_id.erp_quality_threshold,
                }
            )
        return blockers_by_project

    def _get_quality_blockers(self):
        self.ensure_one()
        return self._get_quality_blockers_map().get(self.id, [])

    def _get_latest_quality_gate(self):
        self.ensure_one()
        return self.env["erp.quality.gate"].search(
            [("project_id", "=", self.id)],
            order="evaluated_at desc, id desc",
            limit=1,
        )

    def _get_go_live_blockers(self):
        self.ensure_one()
        blockers = super()._get_go_live_blockers()
        gate = self._get_latest_quality_gate()
        if not gate:
            blockers.append(_("Quality Gate has not been evaluated."))
        elif gate.is_stale:
            blockers.append(_("Quality Gate approval is stale; re-evaluation is required."))
        elif gate.decision_state != "approved":
            blockers.append(_("The latest Quality Gate must be approved by a Manager."))
        return blockers

    def action_evaluate_quality(self):
        if not self.env.user.has_group(
            "erp_delivery_management.group_erp_delivery_manager"
        ):
            raise AccessError(_("Only an ERP Delivery Manager can evaluate a Quality Gate."))
        gate_model = self.env["erp.quality.gate"]
        now = fields.Datetime.now()
        gates = gate_model
        if any(not project.is_erp_project for project in self):
            raise ValidationError(_("Quality Gate evaluation requires an ERP project."))
        blockers_by_project = self._get_quality_blockers_map()
        for project in self:
            active_lines = project.line_ids.filtered(lambda line: line.state != "cancelled")
            blockers = blockers_by_project.get(project.id, [])
            line_snapshot_values = []
            for line in active_lines:
                line_snapshot_values.append(
                    {
                        "project_line_id": line.id,
                        "solution_name": line.solution_id.display_name,
                        "consultant_name": line.consultant_id.display_name,
                        "state": line.quality_system_result,
                        "score": line.quality_score,
                        "task_score": line.quality_task_score,
                        "risk_score": line.quality_risk_score,
                        "acceptance_score": line.quality_acceptance_score,
                        "checklist_score": line.quality_checklist_score,
                        "blocker_snapshot": line.quality_blocker_summary,
                    }
                )
            gate = gate_model._create_snapshot(
                {
                    "project_id": project.id,
                    "state": "failed" if blockers else "passed",
                    "score": project.quality_score,
                    "threshold": project.company_id.erp_quality_threshold,
                    "task_score": project.quality_task_score,
                    "risk_score": project.quality_risk_score,
                    "line_score": project.quality_line_score,
                    "checklist_score": project.quality_checklist_score,
                    "quality_fingerprint_snapshot": project.quality_fingerprint,
                    "evaluator_id": self.env.user.id,
                    "evaluated_at": now,
                    "blocker_snapshot": "\n".join(blockers),
                }
            )
            self.env["erp.quality.gate.line"]._create_snapshot(
                [dict(values, gate_id=gate.id) for values in line_snapshot_values]
            )
            gates |= gate
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
            raise AccessError(
                _("Only ERP Delivery Consultants and Managers can view Quality Gates.")
            )
        return {
            "type": "ir.actions.act_window",
            "name": _("Quality Gate History"),
            "res_model": "erp.quality.gate",
            "view_mode": "list,form",
            "domain": [("project_id", "=", self.id)],
            "context": {"default_project_id": self.id},
        }
