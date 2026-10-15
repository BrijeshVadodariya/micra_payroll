/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { useService } from "@web/core/utils/hooks";
import { formatDate } from "@web/core/l10n/dates";

const COLORS = {
    working: { bg: "#dcfce7", text: "#166534", border: "#86efac" },
    holiday: { bg: "#fee2e2", text: "#991b1b", border: "#fca5a5" },
    sunday: { bg: "#fee2e2", text: "#991b1b", border: "#fca5a5" },
};

const LEAVE_COLORS = {
    normal: { bg: "#fee2e2", text: "#991b1b", border: "#fca5a5" },
    today: { ring: "outline:2px solid #4f46e5;outline-offset:-2px;" },
};

class WorkingDaysCalendarDialog extends Component {
    static template = "micra_payroll.WorkingDaysCalendarDialog";
    static components = { Dialog };
    static props = {
        recordId: { type: Number },
        year: { type: Number, optional: true },
        month: { type: Number, optional: true },
        onUpdate: { type: Function, optional: true },
        close: { type: Function },
    };

    setup() {
        this.orm = useService("orm");
        this.state = useState({
            loading: true,
            savingDate: "",
            title: "",
            weeks: [],
            workingCount: 0,
            holidaysCount: 0,
            legend: [],
        });

        onWillStart(async () => {
            let data;
            if (this.props.year && this.props.month) {
                data = await this.orm.call(
                    "hr.working.days.config",
                    "get_calendar_data_for_period",
                    [[this.props.recordId], this.props.year, this.props.month]
                );
            } else {
                data = await this.orm.call(
                    "hr.working.days.config",
                    "get_calendar_data",
                    [[this.props.recordId]]
                );
            }
            this.buildCalendar(data);
        });
    }

    buildCalendar(data) {
        const year = data.year;
        const month = data.month;
        const holidayNames = data.holiday_names || {};
        const overrides = data.overrides || {};
        const daysInMonth = new Date(year, month, 0).getDate();
        const startDay = new Date(year, month - 1, 1).getDay();
        const today = new Date();
        const todayStr = this.formatDate(today.getFullYear(), today.getMonth() + 1, today.getDate());

        const cells = [];
        for (let i = 0; i < startDay; i++) {
            cells.push(null);
        }

        let workingCount = 0;
        let holidaysCount = 0;
        for (let day = 1; day <= daysInMonth; day++) {
            const dateStr = this.formatDate(year, month, day);
            const dayOfWeek = new Date(year, month - 1, day).getDay();
            const isSunday = dayOfWeek === 0;
            const isSaturday = dayOfWeek === 6;
            const isFirstSaturday = false;
            const isHoliday = Boolean(holidayNames[dateStr]);
            const override = overrides[dateStr];
            const isManualWorking = override === "working";
            const isManualHoliday = override === "holiday";

            let type = "working";
            let label = "Working";
            if (isManualWorking) {
                label = "Working";
            } else if (isManualHoliday) {
                type = "holiday";
                label = isHoliday ? holidayNames[dateStr] : "Holiday";
                holidaysCount++;
            } else if (isHoliday) {
                type = "holiday";
                label = holidayNames[dateStr] || "Public Holiday";
                holidaysCount++;
            } else if (isSunday) {
                type = "sunday";
                label = "Sunday";
            }

            if (type === "working") {
                workingCount++;
            }

            cells.push({
                day,
                dateStr,
                label,
                type,
                isToday: dateStr === todayStr,
                isHoliday,
                isSunday,
                isSaturday,
                isFirstSaturday,
                holidayName: holidayNames[dateStr] || "",
                isWorking: type === "working",
                isManualWorking,
                isManualHoliday,
                ...COLORS[type],
            });
        }

        while (cells.length % 7) {
            cells.push(null);
        }

        const weeks = [];
        for (let index = 0; index < cells.length; index += 7) {
            weeks.push(cells.slice(index, index + 7));
        }

        this.state.loading = false;
        this.state.title = data.display_name || `${month}/${year}`;
        this.state.weeks = weeks;
        this.state.workingCount = workingCount;
        this.state.holidaysCount = holidaysCount;
        this.state.legend = [
            { ...COLORS.working, label: "Working Day" },
            { ...COLORS.holiday, label: "Public Holiday" },
            { ...COLORS.sunday, label: "Sunday" },
        ];

        if (this.props.onUpdate) {
            this.props.onUpdate(workingCount);
        }
    }

    formatDate(year, month, day) {
        return `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
    }

    dayStyle(cell) {
        if (!cell) {
            return "background:transparent;border:0;";
        }
        const todayRing = cell.isToday ? "outline:2px solid #4f46e5;outline-offset:-2px;" : "";
        return `background:${cell.bg};color:${cell.text};border:1px solid ${cell.border};${todayRing}`;
    }

    headerStyle(index) {
        if (index === 0 || index === 6) {
            return "color:#991b1b;font-weight:700;";
        }
        return "color:#374151;font-weight:600;";
    }

    async toggleDay(cell) {
        if (!cell || this.state.savingDate) {
            return;
        }
        this.state.savingDate = cell.dateStr;
        try {
            const data = await this.orm.call(
                "hr.working.days.config",
                "action_set_calendar_day_status",
                [[this.props.recordId], cell.dateStr, !cell.isWorking]
            );
            this.state.savingDate = "";
            this.buildCalendar(data);
        } finally {
            this.state.savingDate = "";
        }
    }
}

class WorkingDaysField extends Component {
    static template = "micra_payroll.WorkingDaysField";
    static props = { ...standardFieldProps };

    setup() {
        this.dialog = useService("dialog");
        this.notification = useService("notification");
    }

    get value() {
        return this.props.record.data[this.props.name] || 0;
    }

    get recordId() {
        return this.props.record.resId || this.props.record.data.id;
    }

    openCalendar() {
        if (!this.recordId) {
            this.notification.add("Please save the record before opening the calendar.", {
                type: "warning",
            });
            return;
        }
        this.dialog.add(WorkingDaysCalendarDialog, {
            recordId: this.recordId,
            year: Number(this.props.record.data.year),
            month: Number(this.props.record.data.month),
            onUpdate: (count) => {
                this.props.record.update({ [this.props.name]: count });
            },
        });
    }
}

registry.category("fields").add("working_days_calendar", {
    component: WorkingDaysField,
    supportedTypes: ["integer"],
});

class LeaveCalendarDialog extends Component {
    static template = "micra_payroll.LeaveCalendarDialog";
    static components = { Dialog };
    static props = {
        recordId: { type: Number },
        modelName: { type: String, optional: true },
        year: { type: Number, optional: true },
        month: { type: Number, optional: true },
        close: { type: Function },
    };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            loading: true,
            title: "",
            employeeName: "",
            weeks: [],
            leaveCount: 0,
            canEdit: false,
        });

        onWillStart(async () => {
            const data = await this.orm.call(
                this.props.modelName || "hr.payslip",
                "get_employee_leave_calendar_data",
                [[this.props.recordId], this.props.year, this.props.month]
            );
            this.buildCalendar(data);
        });
    }

    buildCalendar(data) {
        const year = data.year;
        const month = data.month;
        const leavesByDate = data.leaves_by_date || {};
        const daysInMonth = new Date(year, month, 0).getDate();
        const startDay = new Date(year, month - 1, 1).getDay();
        const today = new Date();
        const todayStr = this.formatDate(today.getFullYear(), today.getMonth() + 1, today.getDate());

        const cells = [];
        for (let i = 0; i < startDay; i++) {
            cells.push(null);
        }

        let leaveDateCount = 0;
        for (let day = 1; day <= daysInMonth; day++) {
            const dateStr = this.formatDate(year, month, day);
            const leaves = leavesByDate[dateStr] || [];
            if (leaves.length) {
                leaveDateCount++;
            }
            cells.push({
                day,
                dateStr,
                leaves,
                isToday: dateStr === todayStr,
                hasLeave: Boolean(leaves.length),
            });
        }

        while (cells.length % 7) {
            cells.push(null);
        }

        const weeks = [];
        for (let index = 0; index < cells.length; index += 7) {
            weeks.push(cells.slice(index, index + 7));
        }

        this.state.loading = false;
        this.state.title = data.display_name || `${month}/${year}`;
        this.state.employeeName = data.employee_name || "";
        this.state.weeks = weeks;
        this.state.leaveCount = leaveDateCount;
        this.state.canEdit = Boolean(data.can_edit);
    }

    formatDate(year, month, day) {
        return `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
    }

    dayStyle(cell) {
        if (!cell) {
            return "background:transparent;border:0;";
        }
        const todayRing = cell.isToday ? LEAVE_COLORS.today.ring : "";
        if (cell.hasLeave) {
            return `background:${LEAVE_COLORS.normal.bg};color:${LEAVE_COLORS.normal.text};border:1px solid ${LEAVE_COLORS.normal.border};${todayRing}`;
        }
        return `background:#ffffff;color:#374151;border:1px solid #e5e7eb;${todayRing}`;
    }

    headerStyle(index) {
        if (index === 0 || index === 6) {
            return "color:#991b1b;font-weight:700;";
        }
        return "color:#374151;font-weight:600;";
    }

    async openLeave(cell) {
        if (!cell || !cell.leaves.length) {
            return;
        }
        const leave = cell.leaves[0];
        await this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "hr.leave",
            res_id: leave.id,
            views: [[false, "form"]],
            target: "current",
        });
        this.props.close();
    }
}

class LeavePeriodField extends Component {
    static template = "micra_payroll.LeavePeriodField";
    static props = { ...standardFieldProps };

    setup() {
        this.dialog = useService("dialog");
        this.notification = useService("notification");
    }

    get value() {
        const value = this.props.record.data[this.props.name];
        return value ? formatDate(value) : "";
    }

    get recordId() {
        return this.props.record.resId || this.props.record.data.id;
    }

    openCalendar() {
        if (!this.recordId) {
            this.notification.add("Please save the payslip before opening leave calendar.", {
                type: "warning",
            });
            return;
        }
        const dateFrom = this.props.record.data.date_from;
        this.dialog.add(LeaveCalendarDialog, {
            recordId: this.recordId,
            year: dateFrom ? dateFrom.year : undefined,
            month: dateFrom ? dateFrom.month : undefined,
        });
    }
}

registry.category("fields").add("leave_period_calendar", {
    component: LeavePeriodField,
    supportedTypes: ["date"],
});

export { WorkingDaysCalendarDialog, WorkingDaysField, LeaveCalendarDialog, LeavePeriodField };
