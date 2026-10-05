from odoo import Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged

from odoo.addons.erp_delivery_management.tests.common import ErpDeliveryCase


@tagged("post_install", "-at_install")
class TestErpDeliveryQuality(ErpDeliveryCase):
    def _add_completed_task(self, project, line, **values):
        vals = {
            "name": "Completed Task",
            "project_id": project.id,
            "project_line_id": line.id,
            "state": "1_done",
            "acceptance_state": "accepted",
            "progress_weight": 1.0,
            "risk_status": "resolved",
        }
        vals.update(values)
        return self.env["project.task"].with_user(self.manager).create(vals)

    def _add_passed_line_check(self, project, line, **values):
        vals = {
            "name": "Acceptance Evidence",
            "project_id": project.id,
            "project_line_id": line.id,
            "weight": 2.0,
            "mandatory": True,
            "passed": True,
        }
        vals.update(values)
        return self.env["erp.quality.check"].with_user(self.manager).create(vals)

    def make_full_score_project(self):
        project = self.create_project()
        line = self.add_line(project, state="accepted")
        self._add_completed_task(project, line)
        self._add_passed_line_check(project, line)
        return project, line

    def test_line_and_project_quality_score_components(self):
        project, line = self.make_full_score_project()
        self.assertEqual(line.quality_task_score, 50.0)
        self.assertEqual(line.quality_risk_score, 20.0)
        self.assertEqual(line.quality_acceptance_score, 20.0)
        self.assertEqual(line.quality_checklist_score, 10.0)
        self.assertEqual(line.quality_score, 100.0)
        self.assertEqual(line.quality_system_result, "passed")
        self.assertEqual(project.quality_score, 100.0)
        self.assertEqual(project.quality_system_result, "passed")

    def test_failed_line_cannot_be_compensated_by_another_line(self):
        project, good_line = self.make_full_score_project()
        second_solution = self.env["erp.solution"].with_user(self.manager).create(
            {
                "name": "Accounting",
                "code": "SOL-ACCOUNTING",
                "solution_group": "core",
                "standard_effort": 80.0,
                "service_price": 5000.0,
            }
        )
        failed_line = self.add_line(
            project,
            solution_id=second_solution.id,
            expected_effort=1.0,
            state="in_progress",
        )
        good_line.expected_effort = 1000.0
        self.assertEqual(good_line.quality_system_result, "passed")
        self.assertEqual(failed_line.quality_system_result, "failed")
        self.assertEqual(project.quality_system_result, "failed")

    def test_gate_stores_line_snapshots(self):
        project, line = self.make_full_score_project()
        action = project.with_user(self.manager).action_evaluate_quality()
        gate = self.env["erp.quality.gate"].browse(action["res_id"])
        self.assertEqual(gate.state, "passed")
        self.assertEqual(gate.decision_state, "pending")
        self.assertEqual(len(gate.line_snapshot_ids), 1)
        self.assertEqual(gate.line_snapshot_ids.project_line_id, line)
        self.assertEqual(gate.line_snapshot_ids.score, 100.0)
        self.assertEqual(
            gate.quality_fingerprint_snapshot, project.quality_fingerprint
        )

    def test_manager_can_override_failed_result_with_required_reason(self):
        project = self.create_project()
        self.add_line(project, state="accepted")
        action = project.with_user(self.manager).action_evaluate_quality()
        gate = self.env["erp.quality.gate"].browse(action["res_id"])
        self.assertEqual(gate.state, "failed")
        with self.assertRaises(ValidationError):
            gate.with_user(self.manager)._apply_decision("approved", "")
        gate.with_user(self.manager)._apply_decision(
            "approved", "Go-live risk accepted by the steering committee."
        )
        self.assertEqual(gate.decision_state, "approved")
        self.assertTrue(gate.is_override)
        self.assertTrue(gate.decision_reason)
        quality_blockers = [
            blocker
            for blocker in project.with_user(self.manager)._get_go_live_blockers()
            if "quality gate" in blocker.lower()
        ]
        self.assertFalse(quality_blockers)

    def test_reject_requires_reason(self):
        project, _line = self.make_full_score_project()
        action = project.with_user(self.manager).action_evaluate_quality()
        gate = self.env["erp.quality.gate"].browse(action["res_id"])
        with self.assertRaises(ValidationError):
            gate.with_user(self.manager)._apply_decision("rejected", "")
        gate.with_user(self.manager)._apply_decision("rejected", "Evidence is insufficient.")
        self.assertEqual(gate.decision_state, "rejected")

    def test_approval_becomes_stale_after_quality_data_change(self):
        project, line = self.make_full_score_project()
        action = project.with_user(self.manager).action_evaluate_quality()
        gate = self.env["erp.quality.gate"].browse(action["res_id"])
        gate.with_user(self.manager)._apply_decision("approved")
        self.assertFalse(gate.is_stale)
        line.quality_check_ids.with_user(self.manager).write({"passed": False})
        self.assertTrue(gate.is_stale)
        self.assertTrue(
            any(
                "stale" in blocker.lower()
                for blocker in project.with_user(self.manager)._get_go_live_blockers()
            )
        )

    def test_only_manager_can_decide_gate(self):
        project, _line = self.make_full_score_project()
        action = project.with_user(self.manager).action_evaluate_quality()
        gate = self.env["erp.quality.gate"].browse(action["res_id"])
        with self.assertRaises(AccessError):
            gate.with_user(self.consultant)._apply_decision("approved")

    def test_snapshot_models_reject_public_create(self):
        project, line = self.make_full_score_project()
        with self.assertRaises(AccessError):
            self.env["erp.quality.gate"].with_user(self.manager).create(
                {
                    "project_id": project.id,
                    "state": "passed",
                    "evaluator_id": self.manager.id,
                    "evaluated_at": "2026-01-01 00:00:00",
                }
            )
        with self.assertRaises(AccessError):
            self.env["erp.quality.gate.line"].with_user(self.manager).create(
                {
                    "gate_id": False,
                    "project_line_id": line.id,
                    "solution_name": line.solution_id.display_name,
                    "state": "passed",
                }
            )
        action = project.with_user(self.manager).action_evaluate_quality()
        gate = self.env["erp.quality.gate"].browse(action["res_id"])
        with self.assertRaises(AccessError):
            gate.with_user(self.manager).with_context(
                allow_quality_gate_decision=True
            ).write({"decision_state": "approved"})

    def test_descriptive_change_does_not_make_approval_stale(self):
        project, line = self.make_full_score_project()
        task = line.task_ids
        action = project.with_user(self.manager).action_evaluate_quality()
        gate = self.env["erp.quality.gate"].browse(action["res_id"])
        gate.with_user(self.manager)._apply_decision("approved")

        task.with_user(self.manager).write({"name": "Renamed completed task"})
        self.assertFalse(gate.is_stale)

    def test_source_create_and_unlink_recompute_quality_fingerprint(self):
        project, line = self.make_full_score_project()
        action = project.with_user(self.manager).action_evaluate_quality()
        gate = self.env["erp.quality.gate"].browse(action["res_id"])
        gate.with_user(self.manager)._apply_decision("approved")

        blocking_task = self.env["project.task"].with_user(self.manager).create(
            {
                "name": "New mandatory task",
                "project_id": project.id,
                "project_line_id": line.id,
                "is_mandatory_for_golive": True,
                "progress_weight": 1.0,
            }
        )
        self.assertTrue(gate.is_stale)

        action = project.with_user(self.manager).action_evaluate_quality()
        current_gate = self.env["erp.quality.gate"].browse(action["res_id"])
        current_gate.with_user(self.manager)._apply_decision(
            "approved", "Temporary risk accepted for fingerprint regression test."
        )
        blocking_task.with_user(self.manager).unlink()
        self.assertTrue(current_gate.is_stale)

    def test_line_quality_detail_action_uses_dedicated_view(self):
        _project, line = self.make_full_score_project()
        action = line.action_view_quality_details()
        detail_view = self.env.ref(
            "erp_delivery_quality.view_erp_project_line_quality_detail"
        )
        self.assertEqual(action["res_model"], "erp.project.line")
        self.assertEqual(action["res_id"], line.id)
        self.assertEqual(action["views"], [(detail_view.id, "form")])
        self.assertEqual(action["target"], "new")

    def test_company_threshold_validation(self):
        with self.assertRaises(ValidationError):
            self.company.erp_quality_threshold = 101.0

    def test_combined_sales_and_quality_hooks_when_sales_is_installed(self):
        project, _line = self.make_full_score_project()
        if "sale_order_id" not in project._fields:
            self.skipTest("erp_delivery_sale is not installed in this test database")
        self.manager.write(
            {"groups_id": [Command.link(self.env.ref("sales_team.group_sale_salesman").id)]}
        )
        order = self.env["sale.order"].with_user(self.manager).create(
            {"partner_id": self.customer.id, "company_id": self.company.id}
        )
        project.with_user(self.manager).sale_order_id = order
        action = project.with_user(self.manager).action_evaluate_quality()
        gate = self.env["erp.quality.gate"].browse(action["res_id"])
        gate.with_user(self.manager)._apply_decision("approved")
        blockers = project.with_user(self.manager)._get_go_live_blockers()
        self.assertTrue(any("sales order" in blocker.lower() for blocker in blockers))
        self.assertFalse(any("quality gate" in blocker.lower() for blocker in blockers))
