from odoo import Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import new_test_user

from .common import ErpDeliveryCase


@tagged("post_install", "-at_install")
class TestErpDeliverySecurity(ErpDeliveryCase):
    def test_unassigned_consultant_cannot_see_public_erp_project(self):
        project = self.create_project(privacy_visibility="employees")
        visible = self.env["project.project"].with_user(self.outsider).search(
            [("id", "=", project.id)]
        )
        self.assertFalse(visible)
        assigned = self.env["project.project"].with_user(self.consultant).search(
            [("id", "=", project.id)]
        )
        self.assertEqual(assigned.ids, project.ids)

    def test_delivery_user_cannot_write_erp_project(self):
        project = self.create_project()
        with self.assertRaises(AccessError):
            project.with_user(self.delivery_user).write({"name": "Forbidden"})

    def test_manager_only_fields_are_enforced_by_python_groups(self):
        with self.assertRaises(AccessError):
            self.customer.with_user(self.consultant).read(["erp_subscription_value"])
        with self.assertRaises(AccessError):
            self.solution.with_user(self.consultant).read(["internal_cost"])

    def test_company_isolation_and_cross_company_relation(self):
        company_2_user = new_test_user(
            self.env,
            login="company_two_reader",
            groups="erp_delivery_management.group_erp_delivery_user",
            company_id=self.company_2.id,
            company_ids=[Command.set([self.company_2.id])],
        )
        project = self.create_project()
        self.assertFalse(
            self.env["project.project"].with_user(company_2_user).search(
                [("id", "=", project.id)]
            )
        )
        self.assertFalse(
            self.env["res.partner"].with_user(company_2_user).search(
                [("id", "=", self.customer.id)]
            )
        )
        internal_partner = self.consultant.partner_id.with_user(self.manager)
        internal_partner.write(
            {
                "is_erp_customer": True,
                "ref_code": "ERP-INTERNAL-A",
                "company_id": self.company.id,
            }
        )
        self.assertFalse(
            self.env["res.partner"].with_user(company_2_user).search(
                [("id", "=", internal_partner.id)]
            )
        )
        global_partner = self.env["res.partner"].with_user(self.manager).create(
            {"name": "Shared Non-ERP Contact", "company_id": False}
        )
        visible_global_partner = self.env["res.partner"].with_user(company_2_user).search(
            [("id", "=", global_partner.id)]
        )
        self.assertEqual(visible_global_partner.ids, global_partner.ids)
        customer_2 = (
            self.env["res.partner"]
            .with_user(self.manager)
            .with_company(self.company_2)
            .create(
                {
                    "name": "ERP Customer Two",
                    "is_erp_customer": True,
                    "ref_code": "ERP-CUST-02",
                    "company_id": self.company_2.id,
                }
            )
        )
        with self.assertRaises(ValidationError):
            project.with_user(self.manager).write({"partner_id": customer_2.id})

    def test_company_dependent_internal_cost(self):
        solution = self.solution.with_user(self.manager)
        solution.with_company(self.company).internal_cost = 50.0
        solution.with_company(self.company_2).internal_cost = 80.0
        self.assertEqual(solution.with_company(self.company).internal_cost, 50.0)
        self.assertEqual(solution.with_company(self.company_2).internal_cost, 80.0)

    def test_customer_reference_is_unique_per_company(self):
        customer_2 = (
            self.env["res.partner"]
            .with_user(self.manager)
            .with_company(self.company_2)
            .create(
                {
                    "name": "Same Reference in Company Two",
                    "is_erp_customer": True,
                    "ref_code": self.customer.ref_code,
                    "company_id": self.company_2.id,
                }
            )
        )
        self.assertEqual(customer_2.ref_code, self.customer.ref_code)
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            (
                self.env["res.partner"]
                .with_user(self.manager)
                .with_company(self.company)
                .create(
                    {
                        "name": "Duplicate Reference in Company One",
                        "is_erp_customer": True,
                        "ref_code": self.customer.ref_code,
                        "company_id": self.company.id,
                    }
                )
            )
        with self.assertRaises((AccessError, ValidationError)):
            self.env["res.partner"].with_user(self.manager).create(
                {
                    "name": "Global ERP Customer",
                    "is_erp_customer": True,
                    "ref_code": "ERP-GLOBAL",
                    "company_id": False,
                }
            )

