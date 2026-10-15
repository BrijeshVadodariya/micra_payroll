/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ActivityMenu } from "@hr_attendance/components/attendance_menu/attendance_menu";
import { useService } from "@web/core/utils/hooks";
import { useState } from "@odoo/owl";

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

        this._checkoutGuardRunning = false;
    },

    async _getMyActiveTaskTimer() {
        try {
            return await this.orm.call("project.task", "get_my_running_timer", [], {});
        } catch (error) {
            console.error("Timer fetch error:", error);
            return {
                running: false,
                paused: false,
                task_id: false,
                task_name: "",
            };
        }
    },

    async _openTaskPopup(taskTimer) {
        if (!taskTimer?.task_id) {
            return;
        }

        return new Promise((resolve) => {
            this.action.doAction(
                {
                    type: "ir.actions.act_window",
                    name: "Task Confirmation",
                    res_model: "project.task",
                    res_id: taskTimer.task_id,
                    views: [[false, "form"]],
                    target: "new",
                    context: {
                        form_view_initial_mode: "edit",
                        attendance_checkout_confirmation: true,
                    },
                },
                {
                    onClose: () => resolve(true),
                }
            );
        });
    },

    async _waitForTimerToStop(maxAttempts = 20, delay = 300) {
        for (let i = 0; i < maxAttempts; i++) {
            const timer = await this._getMyActiveTaskTimer();

            if (!timer.task_id || (!timer.running && !timer.paused)) {
                return true;
            }

            await new Promise((resolve) => setTimeout(resolve, delay));
        }
        return false;
    },

    async _handleCheckoutWithTaskCheck() {
        const timer = await this._getMyActiveTaskTimer();

        // No running/paused timer => allow checkout
        if (!timer.task_id || (!timer.running && !timer.paused)) {
            return true;
        }

        // Open popup and wait until it is closed
        await this._openTaskPopup(timer);

        // After popup closes, wait briefly for backend/UI update
        const isStopped = await this._waitForTimerToStop();

        if (!isStopped) {
            this.notification.add(
                "Please stop or cancel the task timer before Check Out.",
                { type: "danger" }
            );
            return false;
        }

        return true;
    },

    async signInOut() {
        if (this._checkoutGuardRunning) {
            return;
        }

        const isCheckout = !!this.state.checkedIn;

        // Check In => normal flow
        if (!isCheckout) {
            return await super.signInOut(...arguments);
        }

        this._checkoutGuardRunning = true;

        try {
            const allowCheckout = await this._handleCheckoutWithTaskCheck();

            if (!allowCheckout) {
                return;
            }

            // Do checkout automatically
            await super.signInOut(...arguments);

            // Refresh page after checkout
            setTimeout(() => {
                window.location.reload();
            }, 500);
        } catch (error) {
            console.error("Checkout error:", error);

            const msg =
                error?.data?.message ||
                error?.message ||
                "Unable to complete Check Out.";

            this.notification.add(msg, { type: "danger" });
        } finally {
            this._checkoutGuardRunning = false;
        }
    },
});