from odoo import fields, models


class ProjectCancelWizard(models.TransientModel):
    _name = "erp.project.cancel.wizard"
    _description = "ERP Project Cancellation Wizard"

    project_id = fields.Many2one(
        "project.project",
        required=True,
        readonly=True,
        ondelete="cascade",
    )
    cancellation_reason = fields.Text(
        string="Cancellation Reason",
        required=True,
    )

    def action_confirm_cancel(self):
        self.ensure_one()
        self.project_id.action_cancel_with_reason(self.cancellation_reason)
        return {"type": "ir.actions.act_window_close"}
