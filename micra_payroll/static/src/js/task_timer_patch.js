/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { FormController } from "@web/views/form/form_controller";

function triggerTimerChanged(detail) {
    window.dispatchEvent(new CustomEvent("task-timer-changed", { detail }));
}

function triggerPopupClosed() {
    window.dispatchEvent(new CustomEvent("task-timer-popup-closed"));
}

function triggerForceSync() {
    window.dispatchEvent(new CustomEvent("task-timer-force-sync"));
}

function parseDurationToSeconds(value) {
    if (!value || typeof value !== "string") {
        return 0;
    }
    const parts = value.split(":").map((x) => parseInt(x, 10));
    if (parts.length !== 3 || parts.some((x) => Number.isNaN(x))) {
        return 0;
    }
    return (parts[0] * 3600) + (parts[1] * 60) + parts[2];
}

function getLiveTimerSeconds(taskId, fallbackSeconds = 0) {
    const live = window.__taskTimerLiveState || null;
    if (live && live.taskId && taskId && Number(live.taskId) === Number(taskId)) {
        return Math.max(0, parseInt(live.effectiveSeconds || 0, 10));
    }
    return Math.max(0, parseInt(fallbackSeconds || 0, 10));
}

patch(FormController.prototype, {
    async beforeExecuteActionButton(clickParams) {
        const resModel = this.props?.resModel || this.model?.root?.resModel;
        const name = clickParams?.name || clickParams?.attrs?.name;
        const record = this.model?.root?.data || {};
        const taskId = record.id || this.props?.resId || false;
        const taskName = record.name || "";
        const fallbackSeconds = parseDurationToSeconds(record.timer_display || "00:00:00");
        const liveSeconds = getLiveTimerSeconds(taskId, fallbackSeconds);

        try {
            if (resModel === "project.task") {
                if (name === "action_start_timer") {
                    triggerTimerChanged({
                        running: true,
                        paused: false,
                        taskId,
                        taskName,
                        effectiveSeconds: 0,
                    });
                }

                if (name === "action_pause_timer") {
                    triggerTimerChanged({
                        running: false,
                        paused: true,
                        taskId,
                        taskName,
                        effectiveSeconds: liveSeconds,
                    });
                }

                if (name === "action_resume_timer") {
                    triggerTimerChanged({
                        running: true,
                        paused: false,
                        taskId,
                        taskName,
                        effectiveSeconds: liveSeconds,
                    });
                }

                if (name === "action_stop_timer" || name === "action_cancel_timer") {
                    triggerTimerChanged({
                        running: false,
                        paused: false,
                        taskId: false,
                        taskName: "",
                        effectiveSeconds: 0,
                    });
                }
            }
        } catch (error) {
            console.error("Optimistic task timer patch error", error);
        }

        try {
            const result = await super.beforeExecuteActionButton(...arguments);

            if (resModel === "project.task") {
                setTimeout(() => triggerForceSync(), 120);
            }

            return result;
        } catch (error) {
            if (resModel === "project.task") {
                triggerForceSync();
            }
            throw error;
        }
    },

    async onWillUnmount() {
        if (super.onWillUnmount) {
            await super.onWillUnmount(...arguments);
        }

        try {
            const resModel = this.props?.resModel || this.model?.root?.resModel;
            if (resModel === "project.task") {
                triggerPopupClosed();
            }
        } catch (error) {
            console.error("Task popup close patch error", error);
        }
    },
});