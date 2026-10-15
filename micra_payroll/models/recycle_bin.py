# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError
import json
import logging

_logger = logging.getLogger(__name__)

NOISY_RECYCLE_MODELS = [
    'hr.attendance.overtime.line',
    'hr.attendance.overtime',
    'micra.ticket.violation',
    'micra.ticket.violation.line',
    'mail.followers',
    'mail.activity',
    'mail.message',
    'mail.tracking.value',
    'mail.notification',
    'sale.order.line',
    'account.move.line',
    'hr.attendance.break.line',
]


class RecycleBin(models.Model):
    _name = "recycle.bin"
    _description = "Recycle Bin"
    _order = "deletion_date desc"

    name = fields.Char(string="Record Name", required=True)
    model_name = fields.Char(string="Model", required=True, index=True)
    record_id = fields.Integer(string="Record ID", required=True)
    deleted_by_id = fields.Many2one("res.users", string="Deleted By", default=lambda self: self.env.uid)
    deletion_date = fields.Datetime(string="Deletion Date", default=fields.Datetime.now, required=True)
    record_data = fields.Text(string="Record Data", help="JSON serialized data of the original record")
    preview_image = fields.Binary(string="Image Preview", compute="_compute_preview_image")
    attachment_mimetype = fields.Char(string="Mimetype", compute="_compute_preview_image")

    @api.depends('record_data', 'model_name')
    def _compute_preview_image(self):
        for rec in self:
            if rec.model_name == 'ir.attachment':
                try:
                    data = json.loads(rec.record_data)
                    rec.preview_image = data.get('datas')
                    rec.attachment_mimetype = data.get('mimetype', '')
                except Exception:
                    rec.preview_image = False
                    rec.attachment_mimetype = False
            else:
                rec.preview_image = False
                rec.attachment_mimetype = False

    def init(self):
        super().init()
        try:
            with self.env.cr.savepoint():
                placeholders = ','.join(f"'{m}'" for m in NOISY_RECYCLE_MODELS)
                self.env.cr.execute(f"DELETE FROM recycle_bin WHERE model_name IN ({placeholders})")
        except Exception as e:
            _logger.warning("Recycle bin auto-cleanup error in init: %s", e)

    @api.model
    def _search(self, domain, offset=0, limit=None, order=None, **kwargs):
        # Auto-exclude system/background calculation models from all queries
        domain = [('model_name', 'not in', NOISY_RECYCLE_MODELS)] + list(domain or [])
        return super()._search(domain, offset=offset, limit=limit, order=order, **kwargs)

    @api.model
    def action_purge_system_records(self):
        """Purge any background system records from recycle bin table."""
        placeholders = ','.join(f"'{m}'" for m in NOISY_RECYCLE_MODELS)
        self.env.cr.execute(f"DELETE FROM recycle_bin WHERE model_name IN ({placeholders})")
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def _prepare_restore_data(self, model_name, raw_data):
        Model = self.env.get(model_name)
        if Model is None:
            return {}
            
        clean_data = {}
        for key, val in raw_data.items():
            if key in ['id', 'create_date', 'create_uid', 'write_date', 'write_uid', 'display_name', '__last_update', 'access_token', 'access_url']:
                continue
            if key.startswith('message_') or key.startswith('activity_'):
                continue
            
            field = Model._fields.get(key)
            if not field:
                continue

            # Strip fractional seconds from datetime strings to prevent strptime errors
            if field.type in ('datetime', 'date') and isinstance(val, str):
                val = val.split('.')[0]

            if field.type == 'many2one':
                if isinstance(val, list) and len(val) == 2 and isinstance(val[0], int):
                    clean_data[key] = val[0]
                elif val is False:
                    clean_data[key] = False
                else:
                    clean_data[key] = val

            elif field.type == 'many2many':
                # Target records usually still exist. Link them back.
                if isinstance(val, list) and all(isinstance(i, int) for i in val):
                    clean_data[key] = [(6, 0, val)]

            elif field.type == 'one2many':
                # Children were likely cascade-deleted and are in the Recycle Bin.
                # Reconstruct them via (0, 0, values)
                if isinstance(val, list):
                    child_commands = []
                    child_model = field.comodel_name
                    for child_item in val:
                        if isinstance(child_item, dict):
                            # Recursively parse deep serialized dict
                            child_clean = self._prepare_restore_data(child_model, child_item)
                            if field.inverse_name and field.inverse_name in child_clean:
                                del child_clean[field.inverse_name]
                            child_commands.append((0, 0, child_clean))
                        elif isinstance(child_item, int):
                            # Fallback: search in Recycle Bin
                            deleted_children = self.env['recycle.bin'].search([
                                ('model_name', '=', child_model),
                                ('record_id', '=', child_item)
                            ])
                            for child in deleted_children:
                                try:
                                    child_raw = json.loads(child.record_data)
                                    child_clean = self._prepare_restore_data(child_model, child_raw)
                                    if field.inverse_name and field.inverse_name in child_clean:
                                        del child_clean[field.inverse_name]
                                    child_commands.append((0, 0, child_clean))
                                    child.unlink()
                                except Exception as e:
                                    _logger.error("Failed to parse child %s: %s", child.id, e)
                                    
                    if child_commands:
                        clean_data[key] = child_commands

            else:
                clean_data[key] = val

        if model_name == 'ir.attachment':
            # Force Odoo to recreate the file in the filestore from the base64 'datas' payload
            for k in ['store_fname', 'checksum', 'file_size', 'index_content', 'raw', 'db_datas']:
                clean_data.pop(k, None)
            
            # Sanitize the base64 payload to prevent "Invalid base64-encoded string" errors
            if clean_data.get('datas'):
                datas_str = str(clean_data['datas']).strip()
                # Remove b'...' wrapper if it accidentally got cast to string via str(bytes)
                if datas_str.startswith("b'") and datas_str.endswith("'"):
                    datas_str = datas_str[2:-1]
                elif datas_str.startswith('b"') and datas_str.endswith('"'):
                    datas_str = datas_str[2:-1]
                
                # Fix base64 padding
                pad_len = len(datas_str) % 4
                if pad_len > 0:
                    # If pad_len == 1, it's technically invalid base64 (corrupted), but we can try to strip the last char or pad to 4.
                    if pad_len == 1:
                        datas_str = datas_str[:-1]
                    else:
                        datas_str += '=' * (4 - pad_len)
                
                clean_data['datas'] = datas_str

        return clean_data

    def action_restore(self):
        for rec in self:
            try:
                data = json.loads(rec.record_data)
            except Exception:
                raise UserError(_("Cannot parse record data."))

            clean_data = self._prepare_restore_data(rec.model_name, data)
                    
            try:
                # Attempt to create the record (this will also create One2many children!)
                new_record = self.env[rec.model_name].create(clean_data)
                
                # Delete the parent from recycle bin
                rec.unlink()
                
                # Return action to open the restored record
                return {
                    'type': 'ir.actions.act_window',
                    'name': _('Restored Record'),
                    'res_model': new_record._name,
                    'res_id': new_record.id,
                    'view_mode': 'form',
                    'target': 'current',
                }
            except Exception as e:
                raise UserError(_("Could not restore record. Missing relational data or constraints? Error: %s") % str(e))

    def action_preview_ui(self):
        self.ensure_one()
        try:
            data = json.loads(self.record_data)
        except Exception:
            raise UserError(_("Cannot parse record data."))

        clean_data = self._prepare_restore_data(self.model_name, data)
        
        context = dict(self.env.context)
        for k, v in clean_data.items():
            context[f'default_{k}'] = v
            
        return {
            'type': 'ir.actions.act_window',
            'name': _('Preview (Unsaved): %s') % self.name,
            'res_model': self.model_name,
            'view_mode': 'form',
            'target': 'new',
            'context': context,
            'flags': {'mode': 'readonly'},
        }

    @api.model
    def get_clean_preview_context(self, model_name, record_data):
        try:
            data = json.loads(record_data)
            clean_data = self.env['recycle.bin']._prepare_restore_data(model_name, data)
            context = {}
            for k, v in clean_data.items():
                context[f'default_{k}'] = v
            return context
        except Exception as e:
            _logger.error("Failed to generate preview context: %s", e)
            return {}
