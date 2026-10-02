from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError


class SaleOrder(models.Model):
    _inherit = "sale.order"

    erp_project_id = fields.Many2one(
        "project.project",
        string="ERP Delivery Project",
        compute="_compute_erp_projects",
        search="_search_erp_project_id",
        groups="erp_delivery_management.group_erp_delivery_consultant",
    )
    erp_project_count = fields.Integer(
        compute="_compute_erp_projects",
        groups="erp_delivery_management.group_erp_delivery_consultant",
    )

    def _compute_erp_projects(self):
        projects_by_order = {}
        if self.ids:
            rows = self.env["project.project"]._read_group(
                [("sale_order_id", "in", self.ids)],
                ["sale_order_id"],
                ["id:recordset"],
            )
            projects_by_order = {order.id: projects for order, projects in rows}
        empty_projects = self.env["project.project"]
        for order in self:
            projects = projects_by_order.get(order.id, empty_projects)
            order.erp_project_id = projects[:1]
            order.erp_project_count = len(projects)

    def _search_erp_project_id(self, operator, value):
        supported = {"=", "!=", "in", "not in"}
        if operator not in supported:
            raise UserError(_("Unsupported ERP project search operator: %s") % operator)
        Project = self.env["project.project"]
        if value is False:
            linked_order_ids = Project.search(
                [("sale_order_id", "!=", False)]
            ).mapped("sale_order_id").ids
            return [("id", "not in" if operator == "=" else "in", linked_order_ids)]
        if operator in {"=", "in"}:
            matching_order_ids = Project.search([("id", operator, value)]).mapped(
                "sale_order_id"
            ).ids
            return [("id", "in", matching_order_ids)]
        inverse_operator = "=" if operator == "!=" else "in"
        excluded_order_ids = Project.search(
            [("id", inverse_operator, value)]
        ).mapped("sale_order_id").ids
        return [("id", "not in", excluded_order_ids)]

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
        project = self.env["project.project"].create(
            {
                "name": _("%(customer)s - %(order)s")
                % {"customer": self.partner_id.name, "order": self.name},
                "is_erp_project": True,
                "partner_id": self.partner_id.id,
                "company_id": self.company_id.id,
                "user_id": self.env.user.id,
                "date_start": fields.Date.context_today(self),
                "contract_value": self.amount_total,
                "contract_currency_id": self.currency_id.id,
                "sale_order_id": self.id,
                "allow_milestones": True,
            }
        )
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

