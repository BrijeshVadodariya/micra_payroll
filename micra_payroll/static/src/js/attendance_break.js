/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ActivityMenu } from "@hr_attendance/components/attendance_menu/attendance_menu";
import { useService } from "@web/core/utils/hooks";
import { useState, onMounted, onWillUnmount } from "@odoo/owl";
import { rpc } from "@web/core/network/rpc";

patch(ActivityMenu.prototype, {
    setup() {
        super.setup();

        this.orm = useService("orm");
        this.notification = useService("notification");
        this.action = useService("action");

        this.breakState = useState({
            isOnBreak: false,
            loading: false,
            attendanceId: false,
        });

        this.timerState = useState({
            workingBaseSeconds: 0,
            breakBaseSeconds: 0,
            totalBaseSeconds: 0,
            workingText: "00:00:00",
            breakText: "00:00:00",
            totalText: "00:00:00",
        });

        this._timerInterval = null;

        onMounted(() => {
            this._startTimer();
        });

        onWillUnmount(() => {
            this._stopTimer();
        });
    },

    _formatSeconds(totalSeconds) {
        const secs = Math.max(0, Math.floor(totalSeconds || 0));
        const h = String(Math.floor(secs / 3600)).padStart(2, "0");
        const m = String(Math.floor((secs % 3600) / 60)).padStart(2, "0");
        const s = String(secs % 60).padStart(2, "0");
        return `${h}:${m}:${s}`;
    },

    _hhmmssToSeconds(value) {
        if (!value || typeof value !== "string") {
            return 0;
        }
        const parts = value.split(":").map(Number);
        if (parts.length !== 3 || parts.some(isNaN)) {
            return 0;
        }
        return (parts[0] * 3600) + (parts[1] * 60) + parts[2];
    },

    _secondsFromCheckIn(checkInValue) {
        if (!checkInValue) {
            return 0;
        }
        const checkInDate = new Date(checkInValue.replace(" ", "T") + "Z");
        if (isNaN(checkInDate.getTime())) {
            return 0;
        }
        return Math.max(0, Math.floor((Date.now() - checkInDate.getTime()) / 1000));
    },

    _refreshTimerTextFromBase() {
        this.timerState.totalBaseSeconds =
            (this.timerState.workingBaseSeconds || 0) + (this.timerState.breakBaseSeconds || 0);

        this.timerState.workingText = this._formatSeconds(this.timerState.workingBaseSeconds);
        this.timerState.breakText = this._formatSeconds(this.timerState.breakBaseSeconds);
        this.timerState.totalText = this._formatSeconds(this.timerState.totalBaseSeconds);
    },

    _tickRunningTimer() {
        if (!this.state.checkedIn) {
            this.timerState.workingBaseSeconds = 0;
            this.timerState.breakBaseSeconds = 0;
            this.timerState.totalBaseSeconds = 0;
            this.timerState.workingText = "00:00:00";
            this.timerState.breakText = "00:00:00";
            this.timerState.totalText = "00:00:00";
            return;
        }

        if (this.breakState.isOnBreak) {
            this.timerState.breakBaseSeconds += 1;
        } else {
            this.timerState.workingBaseSeconds += 1;
        }

        this._refreshTimerTextFromBase();
    },

    _startTimer() {
        this._stopTimer();
        this._timerInterval = setInterval(() => {
            this._tickRunningTimer();
        }, 1000);
    },

    _stopTimer() {
        if (this._timerInterval) {
            clearInterval(this._timerInterval);
            this._timerInterval = null;
        }
    },

    async _syncBreakState() {
        if (!this.employee || !this.employee.id || this.employee.attendance_state !== "checked_in") {
            this.breakState.isOnBreak = false;
            this.breakState.attendanceId = false;
            this.timerState.workingBaseSeconds = 0;
            this.timerState.breakBaseSeconds = 0;
            this.timerState.totalBaseSeconds = 0;
            this._refreshTimerTextFromBase();
            return;
        }

        const attendances = await this.orm.searchRead(
            "hr.attendance",
            [
                ["employee_id", "=", this.employee.id],
                ["check_out", "=", false],
            ],
            ["id", "is_on_break", "check_in", "worked_time_display", "total_break_time_display"],
            {
                limit: 1,
                order: "check_in desc",
            }
        );

        if (!attendances.length) {
            this.breakState.isOnBreak = false;
            this.breakState.attendanceId = false;
            this.timerState.workingBaseSeconds = 0;
            this.timerState.breakBaseSeconds = 0;
            this.timerState.totalBaseSeconds = 0;
            this._refreshTimerTextFromBase();
            return;
        }

        const attendance = attendances[0];

        this.breakState.attendanceId = attendance.id;
        this.breakState.isOnBreak = !!attendance.is_on_break;

        let workedSeconds = this._hhmmssToSeconds(attendance.worked_time_display);
        const breakSeconds = this._hhmmssToSeconds(attendance.total_break_time_display);

        if (workedSeconds === 0 && attendance.check_in) {
            workedSeconds = this._secondsFromCheckIn(attendance.check_in) - breakSeconds;
            if (workedSeconds < 0) {
                workedSeconds = 0;
            }
        }

        this.timerState.workingBaseSeconds = workedSeconds;
        this.timerState.breakBaseSeconds = breakSeconds;
        this.timerState.totalBaseSeconds = workedSeconds + breakSeconds;

        this._refreshTimerTextFromBase();
    },

    async searchReadEmployee() {
        this.employee = await rpc("/hr_attendance/attendance_user_data");
        this._searchReadEmployeeFill();
        await this._syncBreakState();
    },

    async _handleBreakServerAction(result) {
        if (!result) {
            return false;
        }

        if (result.type === "ir.actions.client" && result.tag === "reload") {
            window.location.reload();
            return true;
        }

        if (result.type) {
            await this.action.doAction(result);
            return true;
        }

        return false;
    },

    async toggleBreak() {
        if (!this.employee || !this.employee.id || this.breakState.loading || !this.state.checkedIn) {
            return;
        }

        this.breakState.loading = true;

        try {
            let result;
            if (this.breakState.isOnBreak) {
                result = await this.orm.call(
                    "hr.employee",
                    "action_employee_break_out",
                    [[this.employee.id]]
                );
            } else {
                result = await this.orm.call(
                    "hr.employee",
                    "action_employee_break_in",
                    [[this.employee.id]]
                );
            }

            const actionHandled = await this._handleBreakServerAction(result);
            if (actionHandled) {
                return;
            }

            this.employee = await rpc("/hr_attendance/attendance_user_data");
            this._searchReadEmployeeFill();
            await this._syncBreakState();
        } catch (error) {
            console.error("Break toggle error:", error);

            const message =
                error?.data?.message ||
                error?.message ||
                "Unable to process break action.";

            this.notification.add(message, {
                type: "danger",
            });
        } finally {
            this.breakState.loading = false;
        }
    },
});