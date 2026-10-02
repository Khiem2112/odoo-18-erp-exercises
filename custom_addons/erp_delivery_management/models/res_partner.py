from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


class ResPartner(models.Model):
    _inherit = "res.partner"

    company_id = fields.Many2one(
        "res.company",
        string="Company",
        default=lambda self: self.env.company,
        compute="_compute_company_id",
        store=True,
        readonly=False,
        precompute=True,
        recursive=True,
    )
    is_erp_customer = fields.Boolean(string="ERP Customer", index=True)
    ref_code = fields.Char(string="ERP Customer Code", index=True, copy=False)
    erp_tier = fields.Selection(
        [
            ("standard", "Standard"),
            ("silver", "Silver"),
            ("gold", "Gold"),
            ("platinum", "Platinum"),
        ],
        default="standard",
        index=True,
    )
    erp_contract_start_date = fields.Date(string="ERP Contract Start")
    erp_contract_end_date = fields.Date(string="ERP Contract End")
    erp_expected_users = fields.Integer(string="Expected ERP Users", default=0)
    erp_subscription_period = fields.Selection(
        [("monthly", "Monthly"), ("yearly", "Yearly")],
        string="Subscription Period",
        default="yearly",
    )
    erp_currency_id = fields.Many2one(
        "res.currency",
        string="ERP Currency",
        related="company_id.currency_id",
        readonly=True,
    )
    erp_subscription_value = fields.Monetary(
        string="Subscription Value",
        currency_field="erp_currency_id",
        groups="erp_delivery_management.group_erp_delivery_manager",
    )
    erp_project_ids = fields.One2many(
        "project.project",
        "partner_id",
        string="ERP Projects",
        domain=[("is_erp_project", "=", True)],
    )

    _sql_constraints = [
        (
            "erp_ref_unique",
            "UNIQUE(company_id, ref_code)",
            "The ERP customer code must be unique per company.",
        ),
        (
            "erp_customer_identity_required",
            "CHECK(NOT is_erp_customer OR "
            "(company_id IS NOT NULL AND ref_code IS NOT NULL AND BTRIM(ref_code) != ''))",
            "An ERP customer must have a company and a customer code.",
        ),
        (
            "erp_contract_dates_order",
            "CHECK(erp_contract_start_date IS NULL OR erp_contract_end_date IS NULL OR erp_contract_end_date >= erp_contract_start_date)",
            "The ERP contract end date must be greater than or equal to the start date.",
        ),
    ]

    _ERP_MANAGED_FIELDS = {
        "is_erp_customer",
        "ref_code",
        "erp_tier",
        "erp_contract_start_date",
        "erp_contract_end_date",
        "erp_expected_users",
        "erp_subscription_period",
        "erp_subscription_value",
    }

    @api.depends("is_erp_customer", "parent_id", "parent_id.company_id")
    def _compute_company_id(self):
        for partner in self:
            if partner.parent_id and partner.parent_id.company_id:
                partner.company_id = partner.parent_id.company_id
            elif partner.is_erp_customer and not partner.company_id:
                print("Fallback into currrent usser company")
                partner.company_id = self.env.company

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.user.has_group(
            "erp_delivery_management.group_erp_delivery_manager"
        ):
            for vals in vals_list:
                if self._ERP_MANAGED_FIELDS.intersection(vals):
                    raise AccessError(_("Only an ERP Delivery Manager can set ERP customer data."))
        return super().create(vals_list)

    def write(self, vals):
        changes_erp_company = "company_id" in vals and any(
            partner.is_erp_customer and partner.company_id.id != vals.get("company_id")
            for partner in self
        )
        if (
            self._ERP_MANAGED_FIELDS.intersection(vals) or changes_erp_company
        ) and not self.env.user.has_group("erp_delivery_management.group_erp_delivery_manager"):
            raise AccessError(_("Only an ERP Delivery Manager can change ERP customer data."))
        return super().write(vals)

    @api.constrains(
        "is_erp_customer",
        "ref_code",
        "company_id",
        "erp_contract_start_date",
        "erp_contract_end_date",
        "erp_expected_users",
    )
    def _check_erp_customer_data(self):
        for partner in self:
            if partner.is_erp_customer:
                if not partner.company_id:
                    raise ValidationError(_("An ERP customer must belong to a company."))
                if not partner.ref_code or not partner.ref_code.strip():
                    raise ValidationError(_("An ERP customer code is required."))
            if (
                partner.erp_contract_start_date
                and partner.erp_contract_end_date
                and partner.erp_contract_end_date < partner.erp_contract_start_date
            ):
                raise ValidationError(
                    _("The ERP contract end date must be greater than or equal to the start date.")
                )
            if partner.erp_expected_users < 0:
                raise ValidationError(_("Expected ERP users cannot be negative."))

    @api.constrains("erp_subscription_value")
    def _check_erp_subscription_value(self):
        for partner in self:
            if partner.erp_subscription_value < 0:
                raise ValidationError(_("The subscription value cannot be negative."))

