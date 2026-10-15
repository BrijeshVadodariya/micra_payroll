# -*- coding: utf-8 -*-
import hashlib
import re
import uuid

from odoo import models, fields, api
from odoo.exceptions import UserError
from odoo.tools.urls import urljoin


class ResCompany(models.Model):
    _inherit = 'res.company'

    working_days_in_month = fields.Integer(
        string="Payroll: Working Days in Month",
        default=23,
        help="Global working days for the month used in salary calculation when no monthly configuration exists."
    )

    enable_face_recognition = fields.Boolean(string="Enable Face Recognition")
    kiosk_allowed_ips = fields.Char(string="Allowed Kiosk IPs (Wi-Fi)", help="Comma-separated list of IP addresses allowed to access the kiosk mode. (e.g., 192.168.1.37 or 192.168.1. to allow the entire subnet). Leave empty to allow all.")
    enable_kiosk_password = fields.Boolean(string="Enable Kiosk Password Protection", default=False)
    kiosk_device_password = fields.Char(string="Kiosk Device Password", help="Password required to authorize a new device for kiosk mode. Leave empty to allow any device without a password.")
    face_attendance_kiosk_key = fields.Char(default=lambda s: uuid.uuid4().hex, copy=False, groups='hr_attendance.group_hr_attendance_user')
    face_attendance_kiosk_url = fields.Char(compute="_compute_face_attendance_kiosk_url")

    @api.depends("face_attendance_kiosk_key")
    def _compute_face_attendance_kiosk_url(self):
        for company in self:
            if company.face_attendance_kiosk_key:
                company.face_attendance_kiosk_url = urljoin(company.get_base_url(), f'/hr_attendance/face_kiosk/{company.face_attendance_kiosk_key}')
            else:
                company.face_attendance_kiosk_url = False

    def _init_column(self, column_name):
        if column_name != 'face_attendance_kiosk_key':
            super()._init_column(column_name)
        else:
            self.env.cr.execute("SELECT id FROM %s WHERE face_attendance_kiosk_key IS NULL" % self._table)
            attendance_ids = self.env.cr.dictfetchall()
            if attendance_ids:
                values_args = [(attendance_id['id'], uuid.uuid4().hex) for attendance_id in attendance_ids]
                query = """
                    UPDATE {table}
                    SET face_attendance_kiosk_key = vals.token
                    FROM (VALUES %s) AS vals(id, token)
                    WHERE {table}.id = vals.id
                """.format(table=self._table)
                self.env.cr.execute_values(query, values_args)

    def _regenerate_face_attendance_kiosk_key(self):
        self.ensure_one()
        self.write({
            'face_attendance_kiosk_key': uuid.uuid4().hex
        })

    def write(self, vals):
        if 'kiosk_device_password' in vals and vals['kiosk_device_password']:
            pwd = vals['kiosk_device_password']
            if not (len(pwd) == 64 and re.fullmatch(r'[0-9a-f]{64}', pwd)):
                vals['kiosk_device_password'] = hashlib.sha256(pwd.encode('utf-8')).hexdigest()
        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('kiosk_device_password'):
                pwd = vals['kiosk_device_password']
                if not (len(pwd) == 64 and re.fullmatch(r'[0-9a-f]{64}', pwd)):
                    vals['kiosk_device_password'] = hashlib.sha256(pwd.encode('utf-8')).hexdigest()
        return super().create(vals_list)

    def _action_open_face_kiosk_mode(self):
        if not self.env.company.enable_face_recognition:
            raise UserError("Face Recognition is disabled in the configuration settings.")
        return {
            'type': 'ir.actions.act_url',
            'target': 'self',
            'url': f'/hr_attendance/face_kiosk_mode_menu/{self.env.company.id}',
        }
