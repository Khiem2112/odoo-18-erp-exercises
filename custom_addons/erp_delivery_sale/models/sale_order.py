from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError


class SaleOrder(models.Model):
    _inherit = "sale.order"

    erp_project_ids = fields.One2many(
        "project.project",
        "sale_order_id",
        string="ERP Delivery Projects",
        groups="erp_delivery_management.group_erp_delivery_consultant",
    )
    erp_project_id = fields.Many2one(
        "project.project",
        string="ERP Delivery Project",
        compute="_compute_erp_project_id",
        search="_search_erp_project_id",
        groups="erp_delivery_management.group_erp_delivery_consultant",
    )

    @api.depends("erp_project_ids")
    def _compute_erp_project_id(self):
        for order in self:
            order.erp_project_id = order.erp_project_ids[:1]

    def _search_erp_project_id(self, operator, value):
        supported = {"=", "!=", "in", "not in"}
        if operator not in supported:
            raise UserError(_("Unsupported ERP project search operator: %s") % operator)
        return [("erp_project_ids", operator, value)]

    def action_create_erp_project(self):
        self.ensure_one()
        if not self.env.user.has_group(
            "erp_delivery_management.group_erp_delivery_manager"
        ):
            raise AccessError(_("Only an ERP Delivery Manager can create a delivery project."))
        if self.state != "sale":
            raise UserError(_("Confirm the sales order before creating an ERP project."))
        if self.erp_project_id:
            raise UserError(_("This sales order already has an ERP delivery project."))
        if not self.partner_id.is_erp_customer:
            raise UserError(_("The sales order customer must be marked as an ERP customer."))
        if self.partner_id.company_id != self.company_id:
            raise UserError(
                _("The ERP customer and sales order must belong to the same company.")
            )
        vals = {
            "name": _("%(customer)s - %(order)s")
            % {"customer": self.partner_id.name, "order": self.name},
            "is_erp_project": True,
            "partner_id": self.partner_id.id,
            "company_id": self.company_id.id,
            "user_id": self.env.user.id,
            "date_start": fields.Date.context_today(self),
            "date_golive_planned": fields.Date.context_today(self),
            "contract_value": self.amount_total,
            "contract_currency_id": self.currency_id.id,
            "sale_order_id": self.id,
            "allow_milestones": True,
        }
        if self.order_line and "sale_line_id" in self.env["project.project"]._fields:
            vals["sale_line_id"] = self.order_line[:1].id
        project = self.env["project.project"].create(vals)
        return {
            "type": "ir.actions.act_window",
            "name": _("ERP Delivery Project"),
            "res_model": "project.project",
            "res_id": project.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_view_erp_project(self):
        self.ensure_one()
        if not self.env.user.has_group(
            "erp_delivery_management.group_erp_delivery_consultant"
        ):
            raise AccessError(
                _("Only ERP Delivery Consultants and Managers can view the ERP delivery project.")
            )
        if not self.erp_project_id:
            raise UserError(_("This sales order has no ERP delivery project."))
        return {
            "type": "ir.actions.act_window",
            "name": _("ERP Delivery Project"),
            "res_model": "project.project",
            "res_id": self.erp_project_id.id,
            "view_mode": "form",
            "target": "current",
        }

