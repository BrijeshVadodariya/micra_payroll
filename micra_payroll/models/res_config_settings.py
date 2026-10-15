# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    """Inherit res_config_settings model for adding payroll and attendance settings"""
    _inherit = 'res.config.settings'

    module_account_accountant = fields.Boolean(string='Account Accountant',
                                               help="Is Account Accountant")
    module_l10n_fr_hr_payroll = fields.Boolean(string='French Payroll',
                                               help="Is French Payroll")
    module_l10n_be_hr_payroll = fields.Boolean(string='Belgium Payroll',
                                               help="Is Belgium Payroll")
    module_l10n_in_hr_payroll = fields.Boolean(string='Indian Payroll',
                                               help="Is Indian Payroll")
    working_days_in_month = fields.Integer(
        related='company_id.working_days_in_month',
        readonly=False,
        string="Working Days in Month"
    )

    # Face Recognition & Kiosk Settings
    enable_face_recognition = fields.Boolean(
        string="Enable Face Recognition",
        related='company_id.enable_face_recognition',
        readonly=False
    )
    kiosk_allowed_ips = fields.Char(
        string="Allowed Kiosk IPs (Wi-Fi)",
        related='company_id.kiosk_allowed_ips',
        readonly=False
    )
    enable_kiosk_password = fields.Boolean(
        string="Enable Kiosk Password Protection",
        related='company_id.enable_kiosk_password',
        readonly=False
    )
    kiosk_device_password = fields.Char(
        string="Kiosk Device Password",
    )
    face_attendance_kiosk_url = fields.Char(
        related='company_id.face_attendance_kiosk_url',
        readonly=True
    )

    # Dummy field to prevent ParseError if l10n_in views are orphaned in the database
    l10n_in_gsp = fields.Char(string="Dummy GSP Field")

    def set_values(self):
        super().set_values()
        menu = self.env.ref('micra_payroll.menu_kiosk_face_attendance', raise_if_not_found=False)
        if menu:
            menu.active = self.enable_face_recognition
        # Clear the password when the checkbox is unchecked
        if not self.enable_kiosk_password:
            self.company_id.kiosk_device_password = False
        elif self.kiosk_device_password:
            # Only update the password if the admin typed a new one
            self.company_id.kiosk_device_password = self.kiosk_device_password

    def regenerate_face_attendance_kiosk_key(self):
        self.company_id._regenerate_face_attendance_kiosk_key()
