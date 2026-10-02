from odoo import Command, fields
from odoo.tests.common import TransactionCase, new_test_user


class ErpDeliveryCase(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company_2 = cls.env["res.company"].create({"name": "ERP Company Two"})
        cls.manager = new_test_user(
            cls.env,
            login="erp_manager",
            groups="erp_delivery_management.group_erp_delivery_manager",
            company_id=cls.company.id,
            company_ids=[Command.set([cls.company.id, cls.company_2.id])],
        )
        cls.consultant = new_test_user(
            cls.env,
            login="erp_consultant",
            groups="erp_delivery_management.group_erp_delivery_consultant",
            company_id=cls.company.id,
        )
        cls.outsider = new_test_user(
            cls.env,
            login="erp_outsider",
            groups="erp_delivery_management.group_erp_delivery_consultant",
            company_id=cls.company.id,
        )
        cls.delivery_user = new_test_user(
            cls.env,
            login="erp_reader",
            groups="erp_delivery_management.group_erp_delivery_user",
            company_id=cls.company.id,
        )
        cls.customer = (
            cls.env["res.partner"]
            .with_user(cls.manager)
            .with_company(cls.company)
            .create(
                {
                    "name": "ERP Customer",
                    "is_company": True,
                    "is_erp_customer": True,
                    "ref_code": "ERP-CUST-01",
                    "company_id": cls.company.id,
                    "erp_subscription_value": 12000.0,
                }
            )
        )
        cls.solution = (
            cls.env["erp.solution"]
            .with_user(cls.manager)
            .with_company(cls.company)
            .create(
                {
                    "name": "Sales",
                    "code": "SOL-SALES",
                    "solution_group": "core",
                    "standard_effort": 80.0,
                    "service_price": 5000.0,
                    "internal_cost": 45.0,
                }
            )
        )

    def create_project(self, **values):
        vals = {
            "name": "ERP Rollout",
            "is_erp_project": True,
            "company_id": self.company.id,
            "partner_id": self.customer.id,
            "user_id": self.consultant.id,
            "team_member_ids": [Command.set([self.consultant.id])],
            "date_start": fields.Date.to_date("2026-01-01"),
            "date_golive_planned": fields.Date.to_date("2026-01-31"),
        }
        vals.update(values)
        return (
            self.env["project.project"]
            .with_user(self.manager)
            .with_company(self.company)
            .create(vals)
        )

    def add_line(self, project, **values):
        vals = {
            "project_id": project.id,
            "solution_id": self.solution.id,
            "consultant_id": self.consultant.id,
            "expected_effort": 80.0,
            "actual_effort": 20.0,
        }
        vals.update(values)
        return self.env["erp.project.line"].with_user(self.manager).create(vals)

