import json

from odoo import http
from odoo.http import request
from werkzeug.exceptions import Forbidden
from odoo.addons.hr_attendance.controllers.main import HrAttendance as HrAttendanceBase
from odoo.service.common import exp_version
from odoo.tools import py_to_js_locale, format_datetime

def _is_ip_allowed(company):
    client_ip = request.httprequest.remote_addr
    forwarded_for = request.httprequest.environ.get('HTTP_X_FORWARDED_FOR')
    if forwarded_for:
        client_ip = forwarded_for.split(',')[0].strip()
        
    if not company.kiosk_allowed_ips:
        return True, client_ip
    
    allowed_ips = [ip.strip() for ip in company.kiosk_allowed_ips.split(',')]
    for allowed_ip in allowed_ips:
        if allowed_ip and client_ip.startswith(allowed_ip):
            return True, client_ip
    return False, client_ip

def _is_password_valid(company, password_hash):
    if not company.enable_kiosk_password or not company.kiosk_device_password:
        return True
    if not password_hash:
        return False
    # Both values are SHA-256 hashes — compare directly
    return password_hash == company.kiosk_device_password

class FaceAttendanceAPI(HrAttendanceBase):

    @http.route(["/hr_attendance/face_kiosk/<token>"], type='http', auth='public', website=True, sitemap=True)
    def open_face_kiosk_mode(self, token, **kwargs):
        """Dedicated URL for the custom Face Attendance Kiosk Mode.
        We skip Odoo's session.logout() here so the admin stays logged in on other tabs.
        """
        company = request.env['res.company'].sudo().search([('face_attendance_kiosk_key', '=', token)], limit=1)
        if not company:
            return request.not_found()
        department_list = [
            {"id": dep["id"], "name": dep["name"], "count": dep["total_employee"]}
            for dep in request.env["hr.department"]
            .with_context(allowed_company_ids=[company.id])
            .sudo()
            .search_read(
                domain=[("company_id", "=", company.id)],
                fields=["id", "name", "total_employee"],
            )
        ]
        version_info = exp_version()
        return request.render(
            'hr_attendance.public_kiosk_mode',
            {
                'kiosk_backend_info': {
                    'token': token,
                    'company_id': company.id,
                    'company_name': company.name,
                    'departments': department_list,
                    'kiosk_mode': company.attendance_kiosk_mode,
                    'from_trial_mode': False,
                    'barcode_source': company.attendance_barcode_source,
                    'device_tracking_enabled': company.attendance_device_tracking,
                    'lang': py_to_js_locale(company.partner_id.lang or company.env.lang),
                    'server_version_info': version_info.get('server_version_info'),
                },
            }
        )

    @http.route('/hr_attendance/get_face_descriptors', type="jsonrpc", auth="public", csrf=False)
    def get_face_descriptors(self, token, password=None):
        """Return face descriptors for ALL employees across all companies (cross-company kiosk support)."""
        company = request.env['res.company'].sudo().search(
            [('face_attendance_kiosk_key', '=', token)], limit=1
        )
        if not company:
            return []
        if not company.enable_face_recognition:
            return {'error': 'face_recognition_disabled'}

        is_allowed, client_ip = _is_ip_allowed(company)
        if not is_allowed:
            return {'error': 'ip_not_allowed', 'client_ip': client_ip}

        if not _is_password_valid(company, password):
            return {'error': 'invalid_password'}

        # Load all employees with registered faces across ALL companies
        employees = request.env['hr.employee'].sudo().search([
            ('face_descriptor', '!=', False),
        ])
        return [
            {
                'id': emp.id,
                'name': emp.name,
                'company_name': emp.company_id.name,
                'descriptor': [round(v, 6) for v in json.loads(emp.face_descriptor)],
                'attendance_state': emp.attendance_state
            }
            for emp in employees
        ]

    @http.route('/hr_attendance/get_attendance_states', type="jsonrpc", auth="public", csrf=False)
    def get_attendance_states(self, token, employee_id=None, password=None):
        """Return real-time attendance states for instant multi-device synchronization."""
        company = request.env['res.company'].sudo().search(
            [('face_attendance_kiosk_key', '=', token)], limit=1
        )
        if not company or not company.enable_face_recognition:
            return {}

        is_allowed, _ = _is_ip_allowed(company)
        if not is_allowed or not _is_password_valid(company, password):
            return {}

        if employee_id:
            emp = request.env['hr.employee'].sudo().browse(employee_id)
            if emp.exists():
                return {
                    'employee_id': emp.id,
                    'attendance_state': emp.attendance_state,
                }
            return {}

        employees = request.env['hr.employee'].sudo().search([
            ('face_descriptor', '!=', False),
        ])
        return {
            'states': {emp.id: emp.attendance_state for emp in employees},
            'count': len(employees),
        }

    @http.route('/hr_attendance/face_check_in_out', type="jsonrpc", auth="public", csrf=False)
    def rpc_face_check_in_out(self, token, employee_id, image, action=None, password=None):
        """Perform face-recognition-based check-in/out and attach the captured snapshot to the chatter."""
        company = request.env['res.company'].sudo().search(
            [('face_attendance_kiosk_key', '=', token)], limit=1
        )
        if not company:
            return {}
        if not company.enable_face_recognition:
            return {'error': 'face_recognition_disabled'}

        is_allowed, client_ip = _is_ip_allowed(company)
        if not is_allowed:
            return {'error': 'ip_not_allowed', 'client_ip': client_ip}

        if not _is_password_valid(company, password):
            return {'error': 'invalid_password'}

        employee = request.env['hr.employee'].sudo().browse(employee_id)
        if not employee.exists() or not employee.face_descriptor:
            return {}

        att = employee.last_attendance_id
        is_checked_in = att and not att.check_out

        if action == 'check_in' and is_checked_in:
            return {'error': 'already_checked_in', 'attendance_state': 'checked_in'}
        if action == 'check_out' and not is_checked_in:
            return {'error': 'not_checked_in', 'attendance_state': 'checked_out'}

        # Perform the standard check-in/out as OdooBot to ensure tracking messages have the correct author
        odoo_bot_id = request.env.ref('base.user_root').id
        try:
            with request.env.cr.savepoint():
                employee.with_user(odoo_bot_id)._attendance_action_change({'mode': 'kiosk'})
        except Exception as e:
            # Holiday / leave / weekend constraints raise ValidationError —
            # return it as a graceful JSON response so the kiosk can show a popup
            return {'error': 'validation_error', 'message': str(e)}

        # Attach the captured face snapshot to the latest attendance record
        att = employee.last_attendance_id
        if att and image:
            if ',' in image:
                image = image.split(',')[1]

            is_check_out = bool(att.check_out)
            file_name = 'face_logout.jpg' if is_check_out else 'face_login.jpg'

            action_time = att.check_out if is_check_out else att.check_in
            employee_tz = (
                employee.tz or 
                employee.user_id.tz or 
                employee.company_id.resource_calendar_id.tz or 
                'UTC'
            )
            formatted_time = format_datetime(request.env, action_time, tz=employee_tz, dt_format='medium')
            body_text = f"Face Logout Image (Checked Out at {formatted_time})" if is_check_out else f"Face Login Image (Checked In at {formatted_time})"

            attachment = request.env['ir.attachment'].sudo().create({
                'name': file_name,
                'datas': image,
                'res_model': 'mail.compose.message',
                'res_id': 0,
                'mimetype': 'image/jpeg',
            })
            author_id = request.env.ref('base.partner_root').sudo().id
            att.message_post(
                body=body_text,
                message_type='comment',
                subtype_xmlid='mail.mt_note',
                attachment_ids=[attachment.id],
                author_id=author_id,
            )

        return HrAttendanceBase._get_employee_info_response(employee)

    @http.route('/hr_attendance/face_kiosk_mode_menu/<int:company_id>', auth='user', type='http')
    def face_kiosk_menu_item_action(self, company_id):
        """Redirect authenticated HR users to the face kiosk URL."""
        if not request.env.user.has_group("hr_attendance.group_hr_attendance_user"):
            return request.not_found()

        company = request.env['res.company'].browse(company_id)
        if not company.enable_face_recognition:
            return request.not_found()

        is_allowed, client_ip = _is_ip_allowed(company)
        if not is_allowed:
            raise Forbidden(f"You are not allowed to open the kiosk from this network. Your current IP is {client_ip}. Please connect to the designated Wi-Fi.")

        # Redirect directly to the dedicated face kiosk URL
        # All kiosk API routes use auth="public" so they work for both
        # logged-in and anonymous users without destroying any session.
        kiosk_url = company.face_attendance_kiosk_url
        return request.redirect(kiosk_url)