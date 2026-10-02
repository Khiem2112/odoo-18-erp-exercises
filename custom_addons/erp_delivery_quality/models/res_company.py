from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ResCompany(models.Model):
    _inherit = "res.company"

    erp_quality_threshold = fields.Float(
        string="ERP Quality Go-live Threshold",
        default=80.0,
    )

    @api.constrains("erp_quality_threshold")
    def _check_erp_quality_threshold(self):
        for company in self:
            if not 0.0 <= company.erp_quality_threshold <= 100.0:
                raise ValidationError(_("The ERP quality threshold must be between 0 and 100."))

