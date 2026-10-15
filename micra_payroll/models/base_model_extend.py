# -*- coding: utf-8 -*-
import json
import logging
import threading
from odoo import models, api

_logger = logging.getLogger(__name__)

# Thread-local state to track active operations per thread
_local_state = threading.local()

original_unlink = models.Model.unlink
original_write = models.Model.write
original_create = models.Model.create

# Models that must NEVER enter Recycle Bin (technical, calculation, chatter, child lines)
NOISY_MODELS = {
    # System and framework models
    'recycle.bin', 'ir.model.data', 'ir.ui.view', 'ir.module.module', 
    'res.users.log', 'bus.bus', 'bus.presence', 'base', 'base.document.layout', 
    'report.paperformat', 'decimal.precision', 'ir.exports', 'ir.exports.line', 
    'ir.cron', 'ir.cron.progress', 'ir.actions.server', 'ir.actions.act_window',
    'ir.actions.report', 'ir.actions.act_url', 'ir.actions.client', 'ir.property',
    'ir.filters', 'ir.default', 'ir.model', 'ir.model.fields', 'ir.model.constraint',
    'ir.model.relation', 'ir.rule', 'ir.sequence', 'ir.sequence.date_range',
    'res.users.settings', 'web_editor.assets', 'ir.asset',
    
    # Mail and chatter models (activities, followers, notifications, messages)
    'mail.message', 'mail.tracking.value', 'mail.followers', 'mail.activity',
    'mail.notification', 'mail.message.reaction', 'mail.link.preview',
    'mail.scheduled.message', 'mail.blacklist',
    
    # Technical & Auto-calculated violation / overtime models
    'hr.attendance.overtime.line', 'hr.attendance.overtime',
    'micra.ticket.violation', 'micra.ticket.violation.line',
    
    # Child line models (should never be standalone recycle bin items)
    'sale.order.line', 'account.move.line', 'account.tax.repartition.line',
    'account.partial.reconcile', 'account.payment.term.line', 'hr.attendance.break.line',
    'project.task.user.rel',
}


def is_user_direct_deletion(model):
    """Return True ONLY if the current unlink was directly triggered by a user in the UI
    (e.g. user selected records and clicked Actions -> Delete).
    Returns False for all background system deletions (updates, syncs, recalculations, cascades, cron).
    """
    if model.env.context.get('force_recycle_bin'):
        return True

    active_rpc = ''
    try:
        from odoo.service.server import thread_local
        active_rpc = getattr(thread_local, 'rpc_model_method', '')
        # If the root RPC call was not an unlink on this exact model, it's a background side-effect!
        if active_rpc and active_rpc != f"{model._name}.unlink":
            return False
    except Exception:
        pass

    try:
        from odoo.http import request
        if not request:
            return False

        params = getattr(request, 'params', None)
        if not isinstance(params, dict):
            if hasattr(request, 'get_json_data'):
                try:
                    data = request.get_json_data()
                    params = data.get('params') if isinstance(data, dict) else None
                except Exception:
                    params = None

        if not isinstance(params, dict):
            return active_rpc == f"{model._name}.unlink"

        rpc_model = params.get('model')
        rpc_method = params.get('method')

        # The user in the UI directly invoked the 'unlink' RPC on this exact model
        return rpc_method == 'unlink' and rpc_model == model._name
    except Exception:
        return False


class BaseModelExtend(models.AbstractModel):
    _inherit = 'base'

    @api.model_create_multi
    def create(self, vals_list):
        already_in_create = getattr(_local_state, 'create_depth', 0) > 0 or self.env.context.get('_in_create_operation')
        if already_in_create:
            return super().create(vals_list)

        _local_state.create_depth = getattr(_local_state, 'create_depth', 0) + 1
        try:
            return super(BaseModelExtend, self.with_context(_in_create_operation=True)).create(vals_list)
        finally:
            _local_state.create_depth = max(0, getattr(_local_state, 'create_depth', 1) - 1)

    def write(self, vals):
        already_in_write = getattr(_local_state, 'write_depth', 0) > 0 or self.env.context.get('_in_write_operation')
        if already_in_write:
            return super().write(vals)

        _local_state.write_depth = getattr(_local_state, 'write_depth', 0) + 1
        try:
            return super(BaseModelExtend, self.with_context(_in_write_operation=True)).write(vals)
        finally:
            _local_state.write_depth = max(0, getattr(_local_state, 'write_depth', 1) - 1)

    def unlink(self):
        if self._name in NOISY_MODELS:
            return super().unlink()

        if getattr(_local_state, 'write_depth', 0) > 0 or self.env.context.get('_in_write_operation'):
            return super().unlink()
        if getattr(_local_state, 'create_depth', 0) > 0 or self.env.context.get('_in_create_operation'):
            return super().unlink()

        if getattr(_local_state, 'unlink_depth', 0) > 0 or self.env.context.get('_in_unlink_operation'):
            return super().unlink()

        if getattr(self, '_transient', False) or getattr(self, '_abstract', False):
            return super().unlink()

        if not is_user_direct_deletion(self):
            return super().unlink()

        _local_state.unlink_depth = getattr(_local_state, 'unlink_depth', 0) + 1
        try:
            try:
                recycle_bin = self.env['recycle.bin'].sudo()
                for rec in self:
                    if getattr(self.env, 'uid', False) == 1:
                        continue

                    if not rec.id or not isinstance(rec.id, int):
                        continue

                    try:
                        def deep_read(record, depth=2):
                            if record._name == 'ir.attachment':
                                fields_to_read = list(record._fields.keys())
                                data = record.with_context(bin_size=False).read(fields_to_read)[0]
                                try:
                                    if record.datas:
                                        val = record.datas
                                        data['datas'] = val.decode('utf-8') if isinstance(val, bytes) else val
                                    data.pop('raw', None)
                                    data.pop('db_datas', None)
                                except Exception:
                                    pass
                            else:
                                data = record.with_context(bin_size=False).read()[0]
                            
                            if depth > 0:
                                for fname, f in record._fields.items():
                                    if f.type == 'one2many':
                                        CHILD_LINE_MODELS = {'sale.order.line', 'account.move.line', 'account.tax.repartition.line', 'account.partial.reconcile', 'account.payment.term.line', 'hr.attendance.break.line', 'project.task.user.rel'}
                                        if fname.startswith('message_') or fname.startswith('activity_'):
                                            continue
                                        if f.comodel_name in NOISY_MODELS and f.comodel_name not in CHILD_LINE_MODELS:
                                            continue
                                        try:
                                            lines = getattr(record, fname)
                                            if lines:
                                                data[fname] = [deep_read(line, depth - 1) for line in lines]
                                        except Exception:
                                            pass
                            return data

                        data = deep_read(rec, depth=2)
                        safe_data = json.dumps(data, default=str, indent=4)
                    except Exception as read_err:
                        _logger.warning("Recycle Bin deep_read failed for %s ID %s: %s", self._name, rec.id, read_err)
                        safe_data = "{}"

                    try:
                        base_name = rec.display_name or f"{self._name} ID {rec.id}"
                        context_prefix = ""
                        if 'employee_id' in rec and rec.employee_id:
                            context_prefix = f"[{rec.employee_id.display_name}] "
                        elif 'partner_id' in rec and rec.partner_id:
                            context_prefix = f"[{rec.partner_id.display_name}] "
                        elif 'task_id' in rec and rec.task_id:
                            context_prefix = f"[Task: {rec.task_id.display_name}] "
                        elif 'project_id' in rec and rec.project_id:
                            context_prefix = f"[Project: {rec.project_id.display_name}] "

                        name = f"{context_prefix}{base_name}"
                    except Exception:
                        name = f"{self._name} ID {rec.id}"

                    try:
                        recycle_bin.create({
                            'name': name,
                            'model_name': self._name,
                            'record_id': rec.id,
                            'deleted_by_id': getattr(self.env, 'uid', 1),
                            'record_data': safe_data
                        })
                    except Exception as e:
                        _logger.error("Recycle Bin creation failed: %s", e)
            except Exception as outer_e:
                _logger.error("Recycle Bin outer exception: %s", outer_e)

            return super(BaseModelExtend, self.with_context(_in_unlink_operation=True)).unlink()
        finally:
            _local_state.unlink_depth = max(0, getattr(_local_state, 'unlink_depth', 1) - 1)


# Monkey-patch _has_cycle to fix hr.payslip.line inheritance relation error
original_has_cycle = models.Model._has_cycle

def patched_has_cycle(self, field_name=None):
    if self._name == 'hr.payslip.line' and field_name == 'parent_rule_id':
        return False
    return original_has_cycle(self, field_name)

models.Model._has_cycle = patched_has_cycle
models.BaseModel._has_cycle = patched_has_cycle
