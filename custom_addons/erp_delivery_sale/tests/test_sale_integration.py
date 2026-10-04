from odoo import Command, fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged

from odoo.addons.erp_delivery_management.tests.common import ErpDeliveryCase


@tagged("post_install", "-at_install")
class TestErpDeliverySale(ErpDeliveryCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager.write(
            {"groups_id": [Command.link(cls.env.ref("sales_team.group_sale_salesman").id)]}
        )
        cls.product = cls.env["product.product"].create(
            {"name": "ERP Implementation", "type": "service", "list_price": 2500.0}
        )

    def create_order(self):
        order = (
            self.env["sale.order"]
            .with_user(self.manager)
            .with_company(self.company)
            .create(
                {
                    "partner_id": self.customer.id,
                    "company_id": self.company.id,
                    "order_line": [
                        (
                            0,
                            0,
                            {
                                "product_id": self.product.id,
                                "product_uom_qty": 2.0,
                                "price_unit": 2500.0,
                            },
                        )
                    ],
                }
            )
        )
        order.action_confirm()
        return order

    def test_create_project_snapshot_and_reverse_navigation(self):
        order = self.create_order()
        action = order.with_user(self.manager).action_create_erp_project()
        project = self.env["project.project"].browse(action["res_id"])
        self.assertEqual(project.sale_order_id, order)
        self.assertEqual(project.partner_id, order.partner_id)
        self.assertEqual(project.company_id, order.company_id)
        self.assertEqual(project.contract_value, order.amount_total)
        self.assertEqual(project.contract_currency_id, order.currency_id)
        self.assertEqual(order.erp_project_id, project)

        proj_view_action = order.with_user(self.manager).action_view_erp_project()
        self.assertEqual(proj_view_action["res_model"], "project.project")
        self.assertEqual(proj_view_action["res_id"], project.id)

        so_view_action = project.with_user(self.manager).action_view_sale_order()
        self.assertEqual(so_view_action["res_model"], "sale.order")
        self.assertEqual(so_view_action["res_id"], order.id)

        project.write({"sale_order_id": False})
        self.assertFalse(order.erp_project_id)
        project.write({"sale_order_id": order.id})
        self.assertEqual(order.erp_project_id, project)

        standalone_project = self.create_project(name="Standalone ERP Project")
        self.assertFalse(standalone_project.sale_order_id)
        with self.assertRaises(UserError):
            standalone_project.with_user(self.manager).action_view_sale_order()

        standalone_order = self.create_order()
        with self.assertRaises(UserError):
            standalone_order.with_user(self.manager).action_view_erp_project()

        with self.assertRaises(AccessError):
            project.with_user(self.delivery_user).action_view_sale_order()
        with self.assertRaises(AccessError):
            order.with_user(self.delivery_user).action_view_erp_project()

    def test_only_confirmed_order_can_create_project(self):
        order = self.create_order()
        order.write({"state": "cancel"})
        with self.assertRaises(UserError):
            order.with_user(self.manager).action_create_erp_project()

    def test_duplicate_project_is_rejected_in_action_and_database(self):
        order = self.create_order()
        action = order.with_user(self.manager).action_create_erp_project()
        with self.assertRaises(UserError):
            order.with_user(self.manager).action_create_erp_project()
        original = self.env["project.project"].browse(action["res_id"])
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self.env["project.project"].with_user(self.manager).create(
                {
                    "name": "Duplicate",
                    "is_erp_project": True,
                    "partner_id": self.customer.id,
                    "company_id": self.company.id,
                    "user_id": self.manager.id,
                    "date_start": fields.Date.today(),
                    "sale_order_id": order.id,
                }
            )
        self.assertTrue(original.exists())

    def test_sales_commercial_blocker(self):
        order = self.create_order()
        action = order.with_user(self.manager).action_create_erp_project()
        project = self.env["project.project"].browse(action["res_id"])
        self.add_line(project)
        order.write({"state": "cancel"})
        blockers = project.with_user(self.manager)._get_go_live_blockers()
        self.assertTrue(any("sales order" in blocker.lower() for blocker in blockers))

    def test_contract_sync_is_explicit(self):
        order = self.create_order()
        action = order.with_user(self.manager).action_create_erp_project()
        project = self.env["project.project"].browse(action["res_id"])
        old_value = project.contract_value
        order.order_line.price_unit = 4000.0
        self.assertEqual(project.contract_value, old_value)
        project.with_user(self.manager).action_sync_contract_from_sale()
        self.assertEqual(project.contract_value, order.amount_total)

