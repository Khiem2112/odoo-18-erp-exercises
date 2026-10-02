{
    "name": "ERP Delivery Quality",
    "summary": "Quality scoring and auditable Go-live gates for ERP delivery",
    "version": "18.0.1.0.0",
    "category": "Services/Project",
    "author": "khiem nguyen",
    "license": "LGPL-3",
    "depends": ["erp_delivery_management"],
    "data": [
        "security/ir.model.access.csv",
        "security/erp_delivery_quality_security.xml",
        "data/quality_gate_sequence.xml",
        "views/res_config_settings_views.xml",
        "views/quality_gate_views.xml",
        "views/project_project_views.xml",
    ],
    "installable": True,
}

