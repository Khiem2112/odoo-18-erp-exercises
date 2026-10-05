from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests import tagged

from odoo.addons.erp_delivery_management.tests.common import ErpDeliveryCase


@tagged("post_install", "-at_install")
class TestErpDeliveryQuality(ErpDeliveryCase):
    def make_full_score_project(self):
        project = self.create_project()
        line = self.add_line(project, state="accepted")
        self.env["project.task"].with_user(self.manager).create(
            {
                "name": "Completed Task",
                "project_id": project.id,
                "project_line_id": line.id,
                "state": "1_done",
                "acceptance_state": "accepted",
                "progress_weight": 1.0,
                "risk_status": "resolved",
            }
        )
        self.env["erp.quality.check"].with_user(self.manager).create(
            {
                "name": "Acceptance Evidence",
                "project_id": project.id,
                "weight": 2.0,
                "mandatory": True,
                "passed": True,
            }
        )
        return project

    def test_quality_score_components_and_boundaries(self):
        project = self.make_full_score_project()
        self.assertEqual(project.quality_task_score, 50.0)
        self.assertEqual(project.quality_risk_score, 20.0)
        self.assertEqual(project.quality_line_score, 20.0)
        self.assertEqual(project.quality_checklist_score, 10.0)
        self.assertEqual(project.quality_score, 100.0)
        self.env["project.task"].with_user(self.manager).create(
            {
                "name": "Critical Risk",
                "project_id": project.id,
                "state": "1_canceled",
                "progress_weight": 0.0,
                "risk_level": "critical",
                "risk_status": "open",
            }
        )
        self.assertEqual(project.quality_risk_score, 10.0)

    def test_no_checklist_has_zero_checklist_score(self):
        project = self.create_project()
        self.add_line(project, state="accepted")
        project._compute_quality_score()
        self.assertEqual(project.quality_checklist_score, 0.0)

    def test_threshold_and_mandatory_check_blockers_use_current_data(self):
        project = self.make_full_score_project()
        self.company.erp_quality_threshold = 95.0
        check = project.quality_check_ids
        check.with_user(self.manager).passed = False
        blockers = project.with_user(self.manager)._get_go_live_blockers()
        self.assertTrue(any("quality score" in blocker.lower() for blocker in blockers))
        self.assertTrue(any("quality checks" in blocker.lower() for blocker in blockers))

    def test_gate_is_a_snapshot_and_current_score_can_change(self):
        project = self.make_full_score_project()
        action = project.with_user(self.manager).action_evaluate_quality()
        gate = self.env["erp.quality.gate"].browse(action["res_id"])
        snapshot_score = gate.score
        project.quality_check_ids.with_user(self.manager).passed = False
        project._compute_quality_score()
        self.assertNotEqual(project.quality_score, snapshot_score)
        self.assertEqual(gate.score, snapshot_score)

    def test_company_threshold_validation(self):
        with self.assertRaises(ValidationError):
            self.company.erp_quality_threshold = 101.0

    def test_combined_sales_and_quality_hooks_when_sales_is_installed(self):
        project = self.create_project()
        self.add_line(project, state="accepted")
        if "sale_order_id" not in project._fields:
            self.skipTest("erp_delivery_sale is not installed in this test database")
        self.manager.write(
            {"groups_id": [Command.link(self.env.ref("sales_team.group_sale_salesman").id)]}
        )
        order = self.env["sale.order"].with_user(self.manager).create(
            {"partner_id": self.customer.id, "company_id": self.company.id}
        )
        project.with_user(self.manager).sale_order_id = order
        blockers = project.with_user(self.manager)._get_go_live_blockers()
        self.assertTrue(any("sales order" in blocker.lower() for blocker in blockers))
        self.assertTrue(any("quality score" in blocker.lower() for blocker in blockers))

