from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    erp_quality_threshold = fields.Float(
        related="company_id.erp_quality_threshold",
        readonly=False,
    )

