/** @odoo-module **/

import { Component, xml, useState, onMounted, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

function parseOdooDatetime(value) {
    if (!value) {
        return null;
    }

    if (value instanceof Date) {
        return value;
    }

    if (typeof value === "string") {
        const normalized = value.includes("T") ? value : value.replace(" ", "T");
        const dt = new Date(normalized + (normalized.endsWith("Z") ? "" : "Z"));
        if (!isNaN(dt.getTime())) {
            return dt;
        }
    }

    if (typeof value === "object") {
        if (typeof value.toJSDate === "function") {
            return value.toJSDate();
        }
        if (value.ts) {
            const dt = new Date(value.ts);
            if (!isNaN(dt.getTime())) {
                return dt;
            }
        }
    }

    return null;
}

function formatDuration(totalSeconds) {
    const seconds = Math.max(0, Math.floor(totalSeconds || 0));
    const hours = String(Math.floor(seconds / 3600)).padStart(2, "0");
    const minutes = String(Math.floor((seconds % 3600) / 60)).padStart(2, "0");
    const secs = String(seconds % 60).padStart(2, "0");
    return `${hours}:${minutes}:${secs}`;
}

class TaskLiveTimer extends Component {
    static template = xml`
        <div class="o_task_live_timer d-flex align-items-center gap-2">
            <span class="fw-bold fs-3 text-primary">
                <t t-esc="state.display"/>
            </span>
            <span t-if="state.paused"
                  class="badge rounded-pill text-bg-warning">
                Paused
            </span>
        </div>
    `;

    static props = {
        ...standardFieldProps,
    };

    setup() {
        this.state = useState({
            display: "00:00:00",
            paused: false,
        });

        this.interval = null;

        const updateTimer = () => {
            const record = this.props.record;
            const data = record?.data || {};

            const timerRunning = !!data.timer_running;
            const timerPaused = !!data.timer_paused;
            const timerStart = data.timer_start;
            const timerPauseTime = data.timer_pause_time;
            const pausedSeconds = parseInt(data.timer_total_paused_seconds || 0, 10);
            const fallbackDisplay = data.timer_display || "00:00:00";

            this.state.paused = timerPaused;

            if ((!timerRunning && !timerPaused) || !timerStart) {
                this.state.display = fallbackDisplay;
                return;
            }

            const startDate = parseOdooDatetime(timerStart);
            if (!startDate) {
                this.state.display = fallbackDisplay;
                return;
            }

            let diffSeconds = Math.floor((Date.now() - startDate.getTime()) / 1000);
            diffSeconds -= pausedSeconds;

            if (timerPaused && timerPauseTime) {
                const pauseDate = parseOdooDatetime(timerPauseTime);
                if (pauseDate) {
                    diffSeconds -= Math.floor((Date.now() - pauseDate.getTime()) / 1000);
                }
            }

            this.state.display = formatDuration(Math.max(0, diffSeconds));
        };

        onMounted(() => {
            updateTimer();
            this.interval = setInterval(updateTimer, 1000);
        });

        onWillUnmount(() => {
            if (this.interval) {
                clearInterval(this.interval);
                this.interval = null;
            }
        });
    }
}

const taskLiveTimerField = {
    component: TaskLiveTimer,
    displayName: "Task Live Timer",
    supportedTypes: ["char"],
};

registry.category("fields").add("task_live_timer", taskLiveTimerField);