# -*- coding: utf-8 -*-
{
    'name': 'HR Payroll Management | Face Recognition Kiosk | HRMS Dashboard',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Payroll',
    'summary': 'Face Recognition Attendance Kiosk, Leave-Based Pro-Rated Payroll & Interactive HRMS Dashboard',
    'description': """
Micra HR Payroll & Face Attendance
==================================
A comprehensive, all-in-one Odoo 19 solution combining touchless AI Face Recognition Kiosk attendance, leave & working days automation, pro-rated payroll calculation, and an interactive HRMS employee dashboard:

Key Features:
-------------
- Touchless Face Recognition Attendance Kiosk with real-time AI biometric verification
- Kiosk security controls: Wi-Fi IP subnet whitelist and device password authentication
- Attendance audit chatter logs capturing employee check-in/out snapshots
- Monthly working days & gazetted public holidays configuration with visual interactive calendar
- Shift schedules with configurable late arrival grace time thresholds (Late Time)
- Real-time attendance break tracking (Break In / Break Out) with duration logs
- Automatic pro-rated salary calculation based on actual attended days vs period baselines
- Seamless wage integration with employee contracts (hr.version)
- Batch Salary Computation Wizard with monthly and custom date period options
- Salary Count summary view with one-click bulk computation
- Dynamic Python-powered Salary Rules, Salary Structures, and Contribution Registers
- Interactive Employee Self-Service Dashboard with live running timers and dark mode
- Built-in Project Task Live Timer stopwatch and assigned task status tracking
- Company holiday highlights, event countdowns, and real-time leave balance cards
- Professional printable PDF Payslips, Salary Breakdown sheets, and Contribution Register reports
    """,
    'author': 'Micra Digital',
    'website': 'https://www.micra.digital',
    'price': 61.0,
    'currency': 'USD',
    'depends': [
        'hr_holidays',
        'hr_attendance',
        'project',
        'hr_timesheet',
        'sales_team',
        'base',
        'sale_management',
        'mail',
        'hr',
        'web',
        'calendar',
        'crm',
        'base_setup',
        'partner_autocomplete',
        'account',
    ],
    'data': [
        'data/ir_module_category_data.xml',
        'security/micra_payroll_security.xml',
        'security/project_security.xml',
        'security/project_security_rules.xml',
        'security/crm_lead_rules.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'data/hr_payroll_data.xml',
        'wizard/hr_payslips_employees_views.xml',
        'wizard/payslip_lines_contribution_register_views.xml',
        'wizard/micra_payroll_compute_wizard_views.xml',
        'report/hr_payroll_report.xml',
        'report/report_contribution_register_templates.xml',
        'report/report_payslip_templates.xml',
        'report/report_payslip_details_templates.xml',
        'report/report_actions.xml',
        'report/sales_report.xml',
        'report/report_invoice.xml',
        'views/hr_version_views.xml',
        'views/hr_leave_type_views.xml',
        'views/hr_contract_advantage_template_views.xml',
        'views/hr_salary_rule_views.xml',
        'views/hr_salary_rule_category_views.xml',
        'views/hr_contribution_register_views.xml',
        'views/hr_payroll_structure_views.xml',
        'views/working_days_config_views.xml',
        'views/resource_calendar_views.xml',
        'views/hr_payslip_line_views.xml',
        'views/hr_payslip_views.xml',
        'views/hr_employee_views.xml',
        'views/hr_employee_face_views.xml',
        'views/hr_employee_break_views.xml',
        'views/hr_employee_late_views.xml',
        'views/hr_attendance_views.xml',
        'views/hr_leave_balance_views.xml',
        'views/hr_payroll_summary_views.xml',
        'views/hr_payslip_run_views.xml',
        'views/project_sprint_views.xml',
        'views/project_task_timer_views.xml',
        'views/project_views.xml',
        'views/recycle_bin_views.xml',
        'views/res_partner_views.xml',
        'views/sale_order_views.xml',
        'views/dashboard_menu.xml',
        'views/face_kiosk_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'demo': ['data/hr_payroll_demo.xml'],
    'assets': {
        'web.assets_backend': [
            'micra_payroll/static/src/js/month_calendar_dialog.js',
            'micra_payroll/static/src/xml/month_calendar_dialog.xml',
            'micra_payroll/static/src/js/attendance_break.js',
            'micra_payroll/static/src/xml/attendance_break.xml',
            'micra_payroll/static/src/js/attendance_geofence.js',
            'micra_payroll/static/src/js/attendance_menu_patch.js',
            'micra_payroll/static/src/js/dashboard_action.js',
            'micra_payroll/static/src/js/json_table_widget.js',
            'micra_payroll/static/src/xml/json_table_widget.xml',
            'micra_payroll/static/src/js/partner_autocomplete_patch.js',
            'micra_payroll/static/src/js/task_live_timer.js',
            'micra_payroll/static/src/js/task_timer_patch.js',
            'micra_payroll/static/src/js/task_timer_systray.js',
            'micra_payroll/static/src/scss/dashboard.scss',
            'micra_payroll/static/src/scss/dashboard.css',
            'micra_payroll/static/src/employee/face_capture_action.js',
            'micra_payroll/static/src/employee/face_capture_action.xml',
        ],
        'hr_attendance.assets_public_attendance': [
            'micra_payroll/static/src/kiosk/face_login_scanner.xml',
            'micra_payroll/static/src/kiosk/face_login_scanner.js',
            'micra_payroll/static/src/kiosk/public_kiosk_app.js',
            'micra_payroll/static/src/kiosk/public_kiosk_app.xml',
            'micra_payroll/static/src/kiosk/kiosk_theme.css',
        ],
    },
    'images': ['static/description/banner.png'],
    'license': 'OPL-1',
    'installable': True,
    'auto_install': False,
    'application': True,
}
