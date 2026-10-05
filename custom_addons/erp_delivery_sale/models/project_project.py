from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class ProjectProject(models.Model):
    _inherit = "project.project"

    erp_source_sale_order_id = fields.Many2one(
        "sale.order",
        string="Source Sales Order",
        copy=False,
        index=True,
        check_company=True,
        ondelete="restrict",
        groups="erp_delivery_management.group_erp_delivery_consultant",
    )

    _sql_constraints = [
        (
            "erp_delivery_source_sale_order_unique",
            "UNIQUE(erp_source_sale_order_id)",
            "Only one ERP delivery project can be linked to a sales order.",
        )
    ]

    @api.constrains("erp_source_sale_order_id", "company_id", "partner_id")
    def _check_sale_order_consistency(self):
        for project in self.filtered("erp_source_sale_order_id"):
            order = project.erp_source_sale_order_id
            if order.company_id != project.company_id:
                raise ValidationError(
                    _("The sales order and ERP project must belong to the same company.")
                )
            if order.partner_id != project.partner_id:
                raise ValidationError(
                    _("The sales order customer must match the ERP project customer.")
                )

    def _get_go_live_blockers(self):
        self.ensure_one()
        blockers = super()._get_go_live_blockers()
        if (
            self.erp_source_sale_order_id
            and self.erp_source_sale_order_id.state != "sale"
        ):
            blockers.append(_("The linked sales order must be confirmed."))
        return blockers

    def action_sync_contract_from_sale(self):
        if not self.env.user.has_group(
            "erp_delivery_management.group_erp_delivery_manager"
        ):
            raise AccessError(_("Only an ERP Delivery Manager can synchronize contract data."))
        for project in self:
            if not project.erp_source_sale_order_id:
                raise ValidationError(_("No source sales order is linked to this project."))
            order = project.erp_source_sale_order_id
            project.write(
                {
                    "partner_id": order.partner_id.id,
                    "company_id": order.company_id.id,
                    "contract_value": order.amount_total,
                    "contract_currency_id": order.currency_id.id,
                }
            )
            project.message_post(
                body=_("Contract value was synchronized from sales order %s.")
                % order.display_name
            )
        return True

    def action_view_sale_order(self):
        self.ensure_one()
        if not self.env.user.has_group(
            "erp_delivery_management.group_erp_delivery_consultant"
        ):
            raise AccessError(
                _("Only ERP Delivery Consultants and Managers can view the source contract.")
            )
        if not self.erp_source_sale_order_id:
            raise UserError(_("This ERP project has no source contract."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Source Contract"),
            "res_model": "sale.order",
            "res_id": self.erp_source_sale_order_id.id,
            "view_mode": "form",
            "target": "current",
        }


