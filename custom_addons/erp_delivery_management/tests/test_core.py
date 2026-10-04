from odoo import fields
from odoo.exceptions import AccessError, ValidationError
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
