{
    "name": "ERP Delivery Management",
    "summary": "ERP implementation delivery lifecycle management",
    "version": "18.0.1.2.0",
    "category": "Services/Project",
    "author": "khiem nguyen",
    "license": "LGPL-3",
    "depends": ["base", "mail", "project"],
    "data": [
        "security/erp_delivery_security.xml",
        "security/ir.model.access.csv",
        "data/erp_project_sequence.xml",
        "data/ir_cron.xml",
        "views/res_partner_views.xml",
        "views/erp_solution_views.xml",
        "views/project_project_views.xml",
        "views/project_task_views.xml",
        "views/project_milestone_views.xml",
    ],
    "application": True,
    "installable": True,
}

