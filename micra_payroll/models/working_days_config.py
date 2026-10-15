# -*- coding: utf-8 -*-
import calendar
import datetime
import json
import pytz
from odoo import fields, models, api, _
from odoo.exceptions import ValidationError

MONTH_SELECTION = [
    ('1', 'January'), ('2', 'February'), ('3', 'March'),
    ('4', 'April'), ('5', 'May'), ('6', 'June'),
    ('7', 'July'), ('8', 'August'), ('9', 'September'),
    ('10', 'October'), ('11', 'November'), ('12', 'December'),
]


class HrWorkingDaysConfig(models.Model):
    _name = 'hr.working.days.config'
    _description = 'Monthly Working Days Configuration'
    _order = 'year desc, month asc'
    _rec_name = 'display_name'

    def init(self):
        super(HrWorkingDaysConfig, self).init()
        try:
            with self.env.cr.savepoint():
                self.env.cr.execute("ALTER TABLE IF EXISTS hr_working_days_config DROP CONSTRAINT IF EXISTS hr_working_days_config_unique_year_month_company")
        except Exception:
            pass

        for table_name in ['hr_payroll_structure', 'hr_salary_rule', 'hr_salary_rule_category', 'hr_contribution_register']:
            try:
                with self.env.cr.savepoint():
                    self.env.cr.execute("""
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name = %s AND column_name = 'company_id' AND is_nullable = 'NO'
                    """, (table_name,))
                    if self.env.cr.fetchone():
                        self.env.cr.execute(f"ALTER TABLE IF EXISTS {table_name} ALTER COLUMN company_id DROP NOT NULL")
            except Exception:
                pass




    company_ids = fields.Many2many(
        'res.company',
        'hr_working_days_config_company_rel',
        'config_id',
        'company_id',
        string='Companies',
        required=True,
        default=lambda self: self.env.company
    )
    company_id = fields.Many2one(
        'res.company',
        string='Primary Company',
        compute='_compute_company_id',
        store=True,
        readonly=False,
        help="Primary/First company from the selected companies."
    )
    year = fields.Integer(string='Year', required=True)
    month = fields.Selection(MONTH_SELECTION, string='Month', required=True)
    working_days = fields.Integer(
        string='Working Days', required=True, default=0,
        help='Total working days in this month after deducting public holidays and weekends.')
    holiday_line_ids = fields.One2many(
        'hr.working.days.config.holiday', 'config_id', string='Public Holidays')
    notes = fields.Text(string='Notes')
    calendar_day_overrides = fields.Text(string='Calendar Day Overrides', default='{}', copy=False)
    display_name = fields.Char(string='Name', compute='_compute_display_name', store=True)
    total_calendar_days = fields.Integer(string='Total Calendar Days',
                                         compute='_compute_total_calendar_days')
    total_holidays = fields.Integer(string='Total Public Holidays',
                                    compute='_compute_total_holidays')

    @api.depends('company_ids')
    def _compute_company_id(self):
        for rec in self:
            rec.company_id = rec.company_ids[0] if rec.company_ids else False

    @api.constrains('year', 'month', 'company_ids')
    def _check_unique_year_month_company(self):
        for rec in self:
            if not rec.year or not rec.month or not rec.company_ids:
                continue
            domain = [
                ('id', '!=', rec.id),
                ('year', '=', rec.year),
                ('month', '=', rec.month),
                ('company_ids', 'in', rec.company_ids.ids)
            ]
            overlap = self.search(domain, limit=1)
            if overlap:
                overlap_companies = rec.company_ids & overlap.company_ids
                company_names = ", ".join(overlap_companies.mapped('name'))
                raise ValidationError(_(
                    'A working days configuration already exists for year %s, month %s and company/companies: %s!'
                ) % (rec.year, dict(MONTH_SELECTION).get(rec.month, ''), company_names))

    def _get_tz(self):
        company = getattr(self, 'company_id', False) or (getattr(self, 'company_ids', False)[:1] if getattr(self, 'company_ids', False) else False) or self.env.company
        user_tz = (
            self.env.user.tz
            or (company.resource_calendar_id.tz if company.resource_calendar_id else False)
            or 'UTC'
        )
        try:
            return pytz.timezone(user_tz)
        except Exception:
            return pytz.UTC

    def _get_local_date(self, dt):
        if not dt:
            return False
        tz = self._get_tz()
        dt_utc = pytz.utc.localize(dt) if not dt.tzinfo else dt
        dt_local = dt_utc.astimezone(tz)
        return dt_local.date()

    def _local_to_utc_datetime(self, local_date, time_value):
        tz = self._get_tz()
        local_dt = datetime.datetime.combine(local_date, time_value)
        local_dt = tz.localize(local_dt)
        return local_dt.astimezone(pytz.utc).replace(tzinfo=None)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        return records

    def write(self, vals):
        result = super().write(vals)
        return result

    def unlink(self):
        for rec in self:
            if rec.holiday_line_ids:
                rec.holiday_line_ids.unlink()
        return super().unlink()

    @api.depends('year', 'month')
    def _compute_display_name(self):
        month_map = dict(MONTH_SELECTION)
        for rec in self:
            if rec.year and rec.month:
                rec.display_name = f"{month_map.get(rec.month, '')} {rec.year}"
            else:
                rec.display_name = ''

    @api.depends('year', 'month')
    def _compute_total_calendar_days(self):
        for rec in self:
            if rec.year and rec.month:
                rec.total_calendar_days = calendar.monthrange(rec.year, int(rec.month))[1]
            else:
                rec.total_calendar_days = 0

    @api.depends('holiday_line_ids')
    def _compute_total_holidays(self):
        for rec in self:
            rec.total_holidays = len(rec.holiday_line_ids)

    @api.constrains('working_days')
    def _check_working_days(self):
        for rec in self:
            if rec.working_days < 0:
                raise ValidationError(_('Working days cannot be negative.'))
            if rec.year and rec.month:
                max_days = calendar.monthrange(rec.year, int(rec.month))[1]
                if rec.working_days > max_days:
                    raise ValidationError(
                        _('Working days (%d) cannot exceed total days in %s (%d).')
                        % (rec.working_days, rec.display_name, max_days))



    @api.onchange('holiday_line_ids')
    def _onchange_holiday_line_ids(self):
        if self.year and self.month:
            year, month = self.year, int(self.month)
            holiday_names = {}
            for h in self.holiday_line_ids:
                if h.date_from and h.date_to:
                    current = h.date_from
                    while current <= h.date_to:
                        holiday_names[current.strftime('%Y-%m-%d')] = h.name or 'Public Holiday'
                        current += datetime.timedelta(days=1)
            overrides = self._clean_overrides_for_period(self._get_calendar_overrides(), year, month)
            working = self._calculate_calendar_working_days(year, month, holiday_names, overrides)
            self.working_days = working

    def _get_public_holiday_line_values(self, year, month):
        first_day = datetime.date(year, month, 1)
        last_day = datetime.date(year, month, calendar.monthrange(year, month)[1])

        first_day_utc = self._local_to_utc_datetime(first_day, datetime.time(0, 0, 0))
        last_day_utc = self._local_to_utc_datetime(last_day, datetime.time(23, 59, 59))

        domain = [
            ('date_from', '<=', last_day_utc),
            ('date_to', '>=', first_day_utc),
            ('resource_id', '=', False),
        ]
        if self.company_ids:
            domain += ['|', ('calendar_id', '=', False), '|', ('calendar_id.company_id', '=', False), ('calendar_id.company_id', 'in', self.company_ids.ids)]
        leaves = self.env['resource.calendar.leaves'].search(domain, order='date_from, id')

        holiday_values = []
        for leave in leaves:
            start_date = self._get_local_date(leave.date_from)
            end_date = self._get_local_date(leave.date_to)
            clamp_start = max(start_date, first_day)
            clamp_end = min(end_date, last_day)
            
            if clamp_start <= clamp_end:
                holiday_values.append({
                    'date_from': clamp_start,
                    'date_to': clamp_end,
                    'name': leave.name or 'Public Holiday',
                    'is_deducted': True,
                    'leave_id': leave.id,
                })
        return holiday_values

    def _sync_public_holidays_for_month(self):
        self.ensure_one()
        if not self.year or not self.month:
            return

        year, month = self.year, int(self.month)
        holiday_values = self._get_public_holiday_line_values(year, month)
        holiday_names = {}
        for vals in holiday_values:
            current = vals['date_from']
            while current <= vals['date_to']:
                holiday_names[current.strftime('%Y-%m-%d')] = vals['name']
                current += datetime.timedelta(days=1)
                
        overrides = self._clean_overrides_for_period(self._get_calendar_overrides(), year, month)
        working_days = self._calculate_calendar_working_days(year, month, holiday_names, overrides)

        # Remove existing holidays first
        self.holiday_line_ids.with_context(_hr_skip_sync=True).unlink()
        self.invalidate_recordset(['holiday_line_ids'])
        
        if holiday_values:
            self.env['hr.working.days.config.holiday'].with_context(
                _hr_skip_sync=True).create([
                dict(vals, config_id=self.id) for vals in holiday_values
            ])
        
        self.invalidate_recordset(['holiday_line_ids', 'working_days'])
        
        self.with_context(_hr_syncing_public_holidays=True).write({
            'calendar_day_overrides': json.dumps(overrides, sort_keys=True),
            'working_days': working_days,
        })

    def get_calendar_data(self):
        self.ensure_one()
        year, month = self.year, int(self.month)
        return self.get_calendar_data_for_period(year, month)

    def get_calendar_data_for_period(self, year, month):
        year, month = int(year), int(month)
        config = self.filtered(lambda rec: rec.year == year and rec.month == str(month))[:1]
        if not config:
            config = self.env['hr.working.days.config'].search([
                ('year', '=', year),
                ('month', '=', str(month)),
                ('company_ids', '=', self.env.company.id),
            ], limit=1)

        holiday_names = {}
        holiday_lines = config.holiday_line_ids if config else self.env['hr.working.days.config.holiday']
        for h in holiday_lines:
            if h.date_from and h.date_to:
                current = h.date_from
                while current <= h.date_to:
                    date_str = current.strftime('%Y-%m-%d')
                    holiday_names[date_str] = h.name or 'Public Holiday'
                    current += datetime.timedelta(days=1)
        month_name = dict(MONTH_SELECTION).get(str(month), '')
        overrides = config._get_calendar_overrides() if config else {}
        working_days = config._calculate_calendar_working_days(year, month, holiday_names, overrides) if config else 0
        return {
            'year': year,
            'month': month,
            'holiday_names': holiday_names,
            'overrides': overrides,
            'working_days_count': working_days,
            'display_name': f'{month_name} {year}'.strip(),
        }

    def _get_calendar_overrides(self):
        self.ensure_one()
        try:
            overrides = json.loads(self.calendar_day_overrides or '{}')
        except ValueError:
            overrides = {}
        return overrides if isinstance(overrides, dict) else {}

    def _clean_overrides_for_period(self, overrides, year, month):
        prefix = f'{year}-{str(month).zfill(2)}-'
        return {
            date_str: status
            for date_str, status in (overrides or {}).items()
            if date_str.startswith(prefix) and status in ('working', 'holiday')
        }

    def _base_day_is_working(self, year, month, day, holiday_names):
        weekday = calendar.weekday(year, month, day)
        date_str = datetime.date(year, month, day).strftime('%Y-%m-%d')
        if date_str in holiday_names:
            return False
        return weekday < 6

    def _calculate_calendar_working_days(self, year, month, holiday_names, overrides):
        total_days = calendar.monthrange(year, month)[1]
        working = 0
        for day in range(1, total_days + 1):
            date_str = datetime.date(year, month, day).strftime('%Y-%m-%d')
            override = overrides.get(date_str)
            if override == 'working':
                working += 1
            elif override == 'holiday':
                continue
            elif self._base_day_is_working(year, month, day, holiday_names):
                working += 1
        return working

    def is_calendar_date_working(self, day_date):
        self.ensure_one()
        if not day_date:
            return False
        if day_date.year != self.year or day_date.month != int(self.month):
            return False

        date_str = day_date.strftime('%Y-%m-%d')
        overrides = self._get_calendar_overrides()
        if overrides.get(date_str) == 'working':
            return True
        if overrides.get(date_str) == 'holiday':
            return False

        holiday_names = {}
        for h in self.holiday_line_ids:
            if h.date_from and h.date_to:
                current = h.date_from
                while current <= h.date_to:
                    holiday_names[current.strftime('%Y-%m-%d')] = h.name or 'Public Holiday'
                    current += datetime.timedelta(days=1)
        return self._base_day_is_working(self.year, int(self.month), day_date.day, holiday_names)

    def get_date_day_type(self, day_date):
        self.ensure_one()
        if not day_date:
            return False, False
        if day_date.year != self.year or day_date.month != int(self.month):
            return False, False

        date_str = day_date.strftime('%Y-%m-%d')
        overrides = self._get_calendar_overrides()
        override = overrides.get(date_str)

        if override == 'working':
            return 'working', 'Working'
        if override == 'holiday':
            return 'holiday', 'Holiday'

        holiday_names = {}
        for h in self.holiday_line_ids:
            if h.date_from and h.date_to:
                current = h.date_from
                while current <= h.date_to:
                    holiday_names[current.strftime('%Y-%m-%d')] = h.name or 'Public Holiday'
                    current += datetime.timedelta(days=1)

        if date_str in holiday_names:
            return 'holiday', holiday_names[date_str]

        weekday = calendar.weekday(self.year, int(self.month), day_date.day)
        if weekday == 6:
            return 'sunday', 'Sunday'

        return 'working', 'Working'

    def action_set_calendar_day_status(self, date_str, is_working):
        self.ensure_one()
        day_date = fields.Date.to_date(date_str)
        if not day_date:
            raise ValidationError(_('Invalid calendar date.'))

        year, month = self.year, int(self.month)
        if day_date.year != year or day_date.month != month:
            raise ValidationError(_('Calendar date must be within %s.') % self.display_name)

        holiday_names = {}
        for h in self.holiday_line_ids:
            if h.date_from and h.date_to:
                current = h.date_from
                while current <= h.date_to:
                    holiday_names[current.strftime('%Y-%m-%d')] = h.name or 'Public Holiday'
                    current += datetime.timedelta(days=1)
        overrides = self._get_calendar_overrides()
        base_working = self._base_day_is_working(year, month, day_date.day, holiday_names)
        requested_status = 'working' if is_working else 'holiday'

        if base_working == bool(is_working):
            overrides.pop(date_str, None)
        else:
            overrides[date_str] = requested_status

        working_days = self._calculate_calendar_working_days(year, month, holiday_names, overrides)
        self.write({
            'calendar_day_overrides': json.dumps(overrides, sort_keys=True),
            'working_days': working_days,
        })
        return self.get_calendar_data_for_period(year, month)


class HrWorkingDaysConfigHoliday(models.Model):
    _name = 'hr.working.days.config.holiday'
    _description = 'Public Holiday Line'
    _order = 'date_from asc'

    config_id = fields.Many2one('hr.working.days.config', string='Configuration',
                                required=True, ondelete='cascade')
    company_id = fields.Many2one('res.company', related='config_id.company_id', store=True, index=True)
    date_from = fields.Date(string='Start Date', required=True)
    date_to = fields.Date(string='End Date', required=True)
    name = fields.Char(string='Holiday Name', required=True)
    is_deducted = fields.Boolean(string='Deducted from Working Days', default=True)
    leave_id = fields.Many2one('resource.calendar.leaves', string='Linked Public Holiday',
                               ondelete='set null', copy=False)

    @api.constrains('date_from', 'date_to', 'config_id')
    def _check_date_in_month(self):
        for rec in self:
            if rec.config_id.year and rec.config_id.month:
                year = rec.config_id.year
                month = int(rec.config_id.month)
                if rec.date_from and (rec.date_from.year != year or rec.date_from.month != month):
                    raise ValidationError(
                        _('Start Date %s must be within %s.')
                        % (rec.date_from, rec.config_id.display_name))
                if rec.date_to and (rec.date_to.year != year or rec.date_to.month != month):
                    raise ValidationError(
                        _('End Date %s must be within %s.')
                        % (rec.date_to, rec.config_id.display_name))
                if rec.date_from and rec.date_to and rec.date_to < rec.date_from:
                    raise ValidationError(_('End Date must be greater than or equal to Start Date.'))

    def _get_utc_bounds(self, date_from, date_to):
        company = self.company_id or self.config_id.company_id or self.env.company
        user_tz = (
            self.env.user.tz
            or (company.resource_calendar_id.tz if company.resource_calendar_id else False)
            or 'UTC'
        )
        try:
            tz = pytz.timezone(user_tz)
        except Exception:
            tz = pytz.UTC
        local_start = tz.localize(datetime.datetime.combine(date_from, datetime.time.min))
        utc_start = local_start.astimezone(pytz.utc).replace(tzinfo=None)
        local_end = tz.localize(datetime.datetime.combine(date_to, datetime.time(23, 59, 59)))
        utc_end = local_end.astimezone(pytz.utc).replace(tzinfo=None)
        return utc_start, utc_end

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if not self.env.context.get('_hr_skip_sync'):
            for rec in records:
                if not rec.leave_id and rec.date_from and rec.date_to and rec.name:
                    date_from_utc, date_to_utc = rec._get_utc_bounds(rec.date_from, rec.date_to)
                    leave_vals = {
                        'name': rec.name,
                        'date_from': date_from_utc,
                        'date_to': date_to_utc,
                    }
                    company = rec.company_id or rec.config_id.company_id or self.env.company
                    if 'company_id' in self.env['resource.calendar.leaves']._fields and company:
                        leave_vals['company_id'] = company.id
                    leave = self.env['resource.calendar.leaves'].with_context(
                        _hr_skip_sync=True).create(leave_vals)
                    rec.with_context(_hr_skip_sync=True).write({'leave_id': leave.id})
        return records

    def write(self, vals):
        result = super().write(vals)
        if not self.env.context.get('_hr_skip_sync'):
            for rec in self:
                if rec.leave_id:
                    update_vals = {}
                    if 'name' in vals:
                        update_vals['name'] = vals['name']
                    if ('date_from' in vals or 'date_to' in vals) and rec.date_from and rec.date_to:
                        date_from_utc, date_to_utc = rec._get_utc_bounds(rec.date_from, rec.date_to)
                        update_vals['date_from'] = date_from_utc
                        update_vals['date_to'] = date_to_utc
                    if update_vals:
                        rec.leave_id.with_context(_hr_skip_sync=True).write(update_vals)
        return result

    def unlink(self):
        leaves = self.mapped('leave_id').filtered(lambda l: l.exists())
        result = super().unlink()
        if leaves and not self.env.context.get('_hr_skip_sync'):
            leaves.with_context(_hr_skip_sync=True).unlink()
        return result


def split_range_by_month(start_date, end_date):
    ranges = []
    current = start_date
    while current <= end_date:
        year = current.year
        month = current.month
        last_day_of_month = datetime.date(year, month, calendar.monthrange(year, month)[1])
        chunk_end = min(last_day_of_month, end_date)
        ranges.append((year, month, current, chunk_end))
        current = chunk_end + datetime.timedelta(days=1)
    return ranges


class ResourceCalendarLeaves(models.Model):
    _inherit = 'resource.calendar.leaves'

    def _get_tz(self):
        company = getattr(self, 'company_id', False) or (self.calendar_id.company_id if self.calendar_id else False) or self.env.company
        user_tz = (
            self.env.user.tz
            or (company.resource_calendar_id.tz if company.resource_calendar_id else False)
            or 'UTC'
        )
        try:
            return pytz.timezone(user_tz)
        except Exception:
            return pytz.UTC

    def _get_local_date(self, dt):
        if not dt:
            return False
        tz = self._get_tz()
        dt_utc = pytz.utc.localize(dt) if not dt.tzinfo else dt
        dt_local = dt_utc.astimezone(tz)
        return dt_local.date()

    @api.onchange('date_from')
    def _onchange_date_from(self):
        if self.date_from and not self.resource_id:
            tz = self._get_tz()
            dt_utc = pytz.utc.localize(self.date_from) if not self.date_from.tzinfo else self.date_from
            dt_local = dt_utc.astimezone(tz)
            if dt_local.time() != datetime.time.min:
                local_start = dt_local.replace(hour=0, minute=0, second=0, microsecond=0)
                self.date_from = local_start.astimezone(pytz.utc).replace(tzinfo=None)

    @api.onchange('date_to')
    def _onchange_date_to(self):
        if self.date_to and not self.resource_id:
            tz = self._get_tz()
            dt_utc = pytz.utc.localize(self.date_to) if not self.date_to.tzinfo else self.date_to
            dt_local = dt_utc.astimezone(tz)
            if dt_local.time() != datetime.time(23, 59, 59):
                local_end = dt_local.replace(hour=23, minute=59, second=59, microsecond=0)
                self.date_to = local_end.astimezone(pytz.utc).replace(tzinfo=None)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if self.env.context.get('_hr_skip_sync'):
            return records

        for leave in records:
            if not leave.resource_id and leave.date_from and leave.date_to:
                start_date = self._get_local_date(leave.date_from)
                end_date = self._get_local_date(leave.date_to)
                for y, m, s, e in split_range_by_month(start_date, end_date):
                    domain = [
                        ('year', '=', y),
                        ('month', '=', str(m))
                    ]
                    if leave.calendar_id and leave.calendar_id.company_id:
                        domain.append(('company_ids', '=', leave.calendar_id.company_id.id))
                    config = self.env['hr.working.days.config'].search(domain, limit=1)
                    if config:
                        exists = self.env['hr.working.days.config.holiday'].search([
                            ('config_id', '=', config.id),
                            ('leave_id', '=', leave.id)
                        ], limit=1)
                        if exists:
                            exists.with_context(_hr_skip_sync=True).write({
                                'date_from': s,
                                'date_to': e,
                                'name': leave.name or 'Public Holiday',
                            })
                        else:
                            self.env['hr.working.days.config.holiday'].with_context(
                                _hr_skip_sync=True).create({
                                'config_id': config.id,
                                'date_from': s,
                                'date_to': e,
                                'name': leave.name or 'Public Holiday',
                                'is_deducted': True,
                                'leave_id': leave.id,
                            })
        return records

    def write(self, vals):
        result = super().write(vals)
        if self.env.context.get('_hr_skip_sync'):
            return result

        for leave in self:
            if not leave.resource_id:
                synced_lines = self.env['hr.working.days.config.holiday'].search([
                    ('leave_id', '=', leave.id)
                ])
                if 'date_from' in vals or 'date_to' in vals:
                    synced_lines.with_context(_hr_skip_sync=True).unlink()
                    if leave.date_from and leave.date_to:
                        start_date = self._get_local_date(leave.date_from)
                        end_date = self._get_local_date(leave.date_to)
                        for y, m, s, e in split_range_by_month(start_date, end_date):
                            domain = [
                                ('year', '=', y),
                                ('month', '=', str(m))
                            ]
                            if leave.calendar_id and leave.calendar_id.company_id:
                                domain.append(('company_ids', '=', leave.calendar_id.company_id.id))
                            config = self.env['hr.working.days.config'].search(domain, limit=1)
                            if config:
                                self.env['hr.working.days.config.holiday'].with_context(
                                    _hr_skip_sync=True).create({
                                    'config_id': config.id,
                                    'date_from': s,
                                    'date_to': e,
                                    'name': leave.name or 'Public Holiday',
                                    'is_deducted': True,
                                    'leave_id': leave.id,
                                })
                elif 'name' in vals:
                    synced_lines.with_context(_hr_skip_sync=True).write({'name': leave.name})
        return result

    def unlink(self):
        if not self.env.context.get('_hr_skip_sync'):
            synced_lines = self.env['hr.working.days.config.holiday'].search([
                ('leave_id', 'in', self.ids)
            ])
            if synced_lines:
                synced_lines.with_context(_hr_skip_sync=True).unlink()
        return super().unlink()
