from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged

from .common import ErpDeliveryCase


@tagged("post_install", "-at_install")
class TestErpDeliveryTaskWorkflow(ErpDeliveryCase):
    def setUp(self):
        super().setUp()
        self.project = self.create_project(
            user_id=self.consultant.id,
            team_member_ids=[(4, self.consultant.id)],
        )
        self.line = self.add_line(self.project, state="in_progress")
        self.task = (
            self.env["project.task"]
            .with_user(self.manager)
            .create(
                {
                    "name": "Configure Financial Rules",
                    "project_id": self.project.id,
                    "project_line_id": self.line.id,
                    "is_mandatory_for_golive": True,
                    "progress_weight": 2.0,
                }
            )
        )

    def test_default_task_state_and_acceptance(self):
        self.assertEqual(self.task.acceptance_state, "draft")
        self.assertFalse(self.task.risk_level)
        self.assertFalse(self.task.risk_status)
        self.assertEqual(self.task.solution_id, self.line.solution_id)
        self.assertTrue(self.line.solution_id.name in self.line.display_name)
        self.assertEqual(self.project.mandatory_task_count, 1)
        self.assertEqual(self.project.mandatory_task_done_count, 0)
        self.assertEqual(self.project.progress_percentage, 0.0)

    def test_delivery_user_cannot_change_acceptance_state(self):
        with self.assertRaises(AccessError):
            self.task.with_user(self.delivery_user).action_accept()
        with self.assertRaises(AccessError):
            self.task.with_user(self.delivery_user).write({"acceptance_state": "accepted"})

    def test_outsider_consultant_cannot_change_acceptance_state(self):
        with self.assertRaises(AccessError):
            self.task.with_user(self.outsider).action_accept()

    def test_assigned_project_manager_can_accept_and_reject(self):
        task_as_pm = self.task.with_user(self.consultant)
        task_as_pm.action_reject()
        self.assertEqual(self.task.acceptance_state, "rejected")
        self.assertEqual(self.task.state, "02_changes_requested")

        task_as_pm.action_accept()
        self.assertEqual(self.task.acceptance_state, "accepted")
        self.assertEqual(self.task.state, "1_done")

    def test_delivery_manager_can_accept_and_reset(self):
        task_as_manager = self.task.with_user(self.manager)
        task_as_manager.action_accept()
        self.assertEqual(self.task.acceptance_state, "accepted")
        self.assertEqual(self.task.state, "1_done")
        self.assertEqual(self.project.mandatory_task_done_count, 1)

        task_as_manager.action_reset_acceptance()
        self.assertEqual(self.task.acceptance_state, "draft")
        self.assertEqual(self.project.mandatory_task_done_count, 0)

    def test_mandatory_task_must_be_accepted_for_golive(self):
        self.task.with_user(self.manager).write({"state": "1_done"})
        self.assertEqual(self.task.acceptance_state, "draft")
        self.assertEqual(self.project.progress_percentage, 0.0)
        blockers = self.project._get_ready_blockers()
        self.assertTrue(
            any("Mandatory tasks are incomplete or unaccepted" in b for b in blockers)
        )

        self.task.with_user(self.manager).action_accept()
        self.assertEqual(self.project.progress_percentage, 100.0)
        blockers = self.project._get_ready_blockers()
        self.assertFalse(
            any("Mandatory tasks are incomplete or unaccepted" in b for b in blockers)
        )

    def test_direct_transition_to_live_is_blocked_in_write(self):
        self.task.with_user(self.manager).action_accept()
        self.project.with_user(self.consultant).action_start_analysis()
        self.project.with_user(self.consultant).action_start_development()
        self.project.with_user(self.consultant).action_start_uat()
        self.project.with_user(self.manager).action_mark_ready()
        self.assertEqual(self.project.delivery_state, "ready")

        with self.assertRaises((ValidationError, UserError)):
            self.project.with_user(self.manager).write({"delivery_state": "live"})

    def test_action_go_live_success_and_date_actual(self):
        self.task.with_user(self.manager).action_accept()
        self.project.with_user(self.consultant).action_start_analysis()
        self.project.with_user(self.consultant).action_start_development()
        self.project.with_user(self.consultant).action_start_uat()
        self.project.with_user(self.manager).action_mark_ready()
        self.assertEqual(self.project.delivery_state, "ready")

        self.project.with_user(self.manager).action_go_live()
        self.assertEqual(self.project.delivery_state, "live")
        self.assertEqual(
            self.project.date_golive_actual,
            fields.Date.context_today(self.project),
        )

    def test_archived_mandatory_task_does_not_block_golive(self):
        self.task.with_user(self.manager).write({"active": False})
        self.assertEqual(self.project.mandatory_task_count, 0)
        self.assertEqual(self.project.mandatory_task_done_count, 0)
        blockers = self.project._get_ready_blockers()
        self.assertFalse(
            any("Mandatory tasks are incomplete or unaccepted" in b for b in blockers)
        )

    def test_mandatory_milestone_incomplete_blocks_golive(self):
        milestone = self.env["project.milestone"].with_user(self.manager).create({
            "name": "Integration Signoff",
            "project_id": self.project.id,
            "is_mandatory_for_golive": True,
            "is_reached": False,
        })
        self.task.with_user(self.manager).action_accept()
        blockers = self.project._get_ready_blockers()
        self.assertTrue(
            any("Mandatory milestones are incomplete" in b for b in blockers)
        )
        milestone.with_user(self.manager).write({"is_reached": True})
        blockers = self.project._get_ready_blockers()
        self.assertFalse(
            any("Mandatory milestones are incomplete" in b for b in blockers)
        )

    def test_duration_days_inverse_and_inconsistent_payload(self):
        self.project.with_user(self.manager).write({"duration_days": 40})
        expected_planned = self.project.date_start + timedelta(days=40)
        self.assertEqual(self.project.date_golive_planned, expected_planned)

        with self.assertRaises(ValidationError):
            self.project.with_user(self.manager).write({
                "duration_days": 10,
                "date_golive_planned": self.project.date_start + timedelta(days=20),
            })

    def test_cron_recompute_erp_health(self):
        self.assertTrue(self.env["project.project"]._cron_recompute_erp_health())

    def test_batch_line_and_task_operations(self):
        solution_2 = self.env["erp.solution"].with_user(self.manager).create({
            "name": "Inventory Management",
            "code": "SOL-INV",
            "solution_group": "supply_chain",
            "standard_effort": 50.0,
            "service_price": 3000.0,
        })
        line_2 = self.add_line(
            self.project,
            solution_id=solution_2.id,
            expected_effort=50.0,
            actual_effort=10.0,
        )
        self.assertEqual(self.project.solution_count, 2)
        self.assertEqual(self.project.total_expected_effort, 130.0)
        self.assertEqual(self.project.total_actual_effort, 30.0)

        line_2.with_user(self.manager).unlink()
        self.assertEqual(self.project.solution_count, 1)
        self.assertEqual(self.project.total_expected_effort, 80.0)
        self.assertEqual(self.project.total_actual_effort, 20.0)

    def test_action_view_tasks_and_line_task_counts(self):
        self.assertEqual(self.line.task_count, 1)
        self.assertEqual(self.project.line_task_count, 1)

        line_action = self.line.action_view_tasks()
        self.assertEqual(line_action["res_model"], "project.task")
        self.assertEqual(line_action["view_mode"], "list,kanban,form")
        self.assertEqual(line_action["domain"], [("project_line_id", "=", self.line.id)])
        self.assertEqual(line_action["context"]["default_project_line_id"], self.line.id)
        self.assertEqual(line_action["context"]["search_default_group_by_project_line_id"], 1)

        project_action = self.project.action_view_line_tasks()
        self.assertEqual(project_action["res_model"], "project.task")
        self.assertEqual(project_action["view_mode"], "list,kanban,form")
        self.assertEqual(
            project_action["domain"],
            [("project_id", "=", self.project.id), ("project_line_id", "!=", False)],
        )
        self.assertEqual(project_action["context"]["search_default_group_by_project_line_id"], 1)

