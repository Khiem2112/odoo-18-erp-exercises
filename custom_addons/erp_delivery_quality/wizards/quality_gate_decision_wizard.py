from odoo import _, fields, models
from odoo.exceptions import ValidationError


class ErpQualityGateDecisionWizard(models.TransientModel):
    _name = "erp.quality.gate.decision.wizard"
    _description = "Quality Gate Decision"

    gate_id = fields.Many2one("erp.quality.gate", required=True, readonly=True)
    decision = fields.Selection(
        [("approved", "Approve"), ("rejected", "Reject")],
        required=True,
        readonly=True,
    )
    system_result = fields.Selection(related="gate_id.state", readonly=True)
    reason = fields.Text(string="Decision Reason")

    def action_confirm(self):
        self.ensure_one()
        reason = (self.reason or "").strip()
        if self.decision == "rejected" and not reason:
            raise ValidationError(_("A rejection reason is required."))
        if self.decision == "approved" and self.system_result == "failed" and not reason:
            raise ValidationError(
                _("An override reason is required to approve a failed system result.")
            )
        self.gate_id._apply_decision(self.decision, reason)
        return {"type": "ir.actions.act_window_close"}
