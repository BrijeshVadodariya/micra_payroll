# -*- coding: utf-8 -*-
from odoo import models


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    def session_info(self):
        res = super().session_info()

        attendance_user_data = res.get('attendance_user_data')
        if attendance_user_data and attendance_user_data.get('id'):
            employee = self.env['hr.employee'].browse(attendance_user_data['id'])

            attendance = self.env['hr.attendance'].search([
                ('employee_id', '=', employee.id),
                ('check_out', '=', False),
            ], limit=1, order='check_in desc')

            attendance_user_data['is_on_break'] = bool(attendance and attendance.is_on_break)

        return res