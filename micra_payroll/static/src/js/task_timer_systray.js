/** @odoo-module **/

import { Component, onMounted, onWillUnmount, useState, xml } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

class TaskTimerSystray extends Component {
    static template = xml`
        <div t-if="false"></div>
    `;

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");

        this.state = useState({
            running: false,
            paused: false,
            taskId: false,
            taskName: "",
            display: "00:00:00",
            hidden: true,
            popupOpenedFromTimer: false,
            elapsedSecondsBase: 0,
            runningAnchorMs: null,
        });

        this._tickInterval = null;
        this._reloadInterval = null;
        this._screenWatchInterval = null;
        this._syncTimeout = null;

        this._boundFocus = this.onWindowFocus.bind(this);
        this._boundHashChange = this.updateHiddenState.bind(this);
        this._boundTimerChanged = this.onTimerChanged.bind(this);
        this._boundTaskPopupClosed = this.onTaskPopupClosed.bind(this);
        this._boundForceSync = this.onForceSync.bind(this);

        onMounted(async () => {
            await this.loadTimer();
            this.startTicking();
            this.startReloading();
            this.startScreenWatcher();

            window.addEventListener("focus", this._boundFocus);
            window.addEventListener("hashchange", this._boundHashChange);
            window.addEventListener("task-timer-changed", this._boundTimerChanged);
            window.addEventListener("task-timer-popup-closed", this._boundTaskPopupClosed);
            window.addEventListener("task-timer-force-sync", this._boundForceSync);
        });

        onWillUnmount(() => {
            this.clearIntervals();

            window.removeEventListener("focus", this._boundFocus);
            window.removeEventListener("hashchange", this._boundHashChange);
            window.removeEventListener("task-timer-changed", this._boundTimerChanged);
            window.removeEventListener("task-timer-popup-closed", this._boundTaskPopupClosed);
            window.removeEventListener("task-timer-force-sync", this._boundForceSync);
        });
    }

    clearIntervals() {
        if (this._tickInterval) {
            clearInterval(this._tickInterval);
            this._tickInterval = null;
        }
        if (this._reloadInterval) {
            clearInterval(this._reloadInterval);
            this._reloadInterval = null;
        }
        if (this._screenWatchInterval) {
            clearInterval(this._screenWatchInterval);
            this._screenWatchInterval = null;
        }
        if (this._syncTimeout) {
            clearTimeout(this._syncTimeout);
            this._syncTimeout = null;
        }
    }

    publishLiveState() {
        window.__taskTimerLiveState = {
            running: this.state.running,
            paused: this.state.paused,
            taskId: this.state.taskId || false,
            taskName: this.state.taskName || "",
            effectiveSeconds: this.getCurrentElapsedSeconds(),
            updatedAt: Date.now(),
        };
    }

    onWindowFocus() {
        this.loadTimer();
        this.updateHiddenState();
    }

    onForceSync() {
        this.loadTimer();
    }

    async onTimerChanged(ev) {
        const detail = ev.detail || {};

        if ("running" in detail) {
            this.state.running = !!detail.running;
        }
        if ("paused" in detail) {
            this.state.paused = !!detail.paused;
        }
        if ("taskId" in detail) {
            this.state.taskId = detail.taskId || false;
        }
        if ("taskName" in detail) {
            this.state.taskName = detail.taskName || "";
        }
        if ("effectiveSeconds" in detail) {
            this.state.elapsedSecondsBase = Math.max(0, parseInt(detail.effectiveSeconds || 0, 10));
        }

        if (this.state.running) {
            this.state.runningAnchorMs = Date.now();
        } else {
            this.state.runningAnchorMs = null;
        }

        if (!this.state.running && !this.state.paused) {
            this.state.taskId = false;
            this.state.taskName = "";
            this.state.elapsedSecondsBase = 0;
            this.state.runningAnchorMs = null;
            this.state.display = "00:00:00";
            this.state.popupOpenedFromTimer = false;
        } else {
            this.updateDisplay();
        }

        this.publishLiveState();
        this.updateHiddenState();

        if (this._syncTimeout) {
            clearTimeout(this._syncTimeout);
        }
        this._syncTimeout = setTimeout(() => {
            this.loadTimer();
            this._syncTimeout = null;
        }, 300);
    }

    onTaskPopupClosed() {
        this.state.popupOpenedFromTimer = false;
        this.updateHiddenState();
        this.loadTimer();
    }

    formatDuration(seconds) {
        const safe = Math.max(0, Math.floor(seconds || 0));
        const h = String(Math.floor(safe / 3600)).padStart(2, "0");
        const m = String(Math.floor((safe % 3600) / 60)).padStart(2, "0");
        const s = String(safe % 60).padStart(2, "0");
        return `${h}:${m}:${s}`;
    }

    parseDate(value) {
        if (!value) {
            return null;
        }
        if (value instanceof Date) {
            return value;
        }
        if (typeof value === "string") {
            const normalized = value.includes("T") ? value : value.replace(" ", "T");
            const dt = new Date(normalized + (normalized.endsWith("Z") ? "" : "Z"));
            return isNaN(dt.getTime()) ? null : dt;
        }
        if (typeof value === "object" && typeof value.toJSDate === "function") {
            return value.toJSDate();
        }
        return null;
    }

    computeBackendEffectiveSeconds(result) {
        if (!result?.timer_start) {
            return 0;
        }

        const start = this.parseDate(result.timer_start);
        if (!start) {
            return 0;
        }

        let diff = Math.max(0, Math.floor((Date.now() - start.getTime()) / 1000));
        diff -= parseInt(result?.paused_seconds || 0, 10);

        if (result?.paused && result?.timer_pause_time) {
            const pauseDate = this.parseDate(result.timer_pause_time);
            if (pauseDate) {
                diff -= Math.max(0, Math.floor((Date.now() - pauseDate.getTime()) / 1000));
            }
        }

        return Math.max(0, diff);
    }

    getCurrentElapsedSeconds() {
        let value = Math.max(0, parseInt(this.state.elapsedSecondsBase || 0, 10));

        if (this.state.running && this.state.runningAnchorMs) {
            value += Math.max(0, Math.floor((Date.now() - this.state.runningAnchorMs) / 1000));
        }

        return value;
    }

    updateDisplay() {
        this.state.display = this.formatDuration(this.getCurrentElapsedSeconds());
        this.publishLiveState();
    }

    resetState() {
        this.state.running = false;
        this.state.paused = false;
        this.state.taskId = false;
        this.state.taskName = "";
        this.state.display = "00:00:00";
        this.state.hidden = true;
        this.state.popupOpenedFromTimer = false;
        this.state.elapsedSecondsBase = 0;
        this.state.runningAnchorMs = null;
        this.publishLiveState();
    }

    getHashParams() {
        const hash = window.location.hash || "";
        const hashString = hash.startsWith("#") ? hash.slice(1) : hash;
        return new URLSearchParams(hashString);
    }

    isOnTaskMainScreen() {
        try {
            const params = this.getHashParams();
            return params.get("model") === "project.task";
        } catch {
            return false;
        }
    }

    isTaskPopupStillOpen() {
        if (!this.state.popupOpenedFromTimer) {
            return false;
        }
        return !!document.querySelector(".modal .o_form_view, .o_dialog .o_form_view");
    }

    updateHiddenState() {
        this.state.hidden = true;
    }

    async loadTimer() {
        try {
            const result = await this.orm.call("project.task", "get_my_running_timer", [], {});
            this.state.running = !!result?.running;
            this.state.paused = !!result?.paused;
            this.state.taskId = result?.task_id || false;
            this.state.taskName = result?.task_name || "";

            if (!this.state.running && !this.state.paused) {
                this.state.popupOpenedFromTimer = false;
                this.state.elapsedSecondsBase = 0;
                this.state.runningAnchorMs = null;
                this.state.display = "00:00:00";
            } else {
                this.state.elapsedSecondsBase = this.computeBackendEffectiveSeconds(result);
                this.state.runningAnchorMs = this.state.running ? Date.now() : null;
                this.updateDisplay();
            }

            this.publishLiveState();
            this.updateHiddenState();
        } catch (error) {
            console.error("Failed to load timer", error);
            this.resetState();
        }
    }

    startTicking() {
        this.updateDisplay();
        this._tickInterval = setInterval(() => {
            this.updateDisplay();
        }, 200);
    }

    startReloading() {
        this._reloadInterval = setInterval(async () => {
            await this.loadTimer();
        }, 4000);
    }

    startScreenWatcher() {
        this._screenWatchInterval = setInterval(() => {
            this.updateHiddenState();
        }, 300);
    }

    async openTask() {
        return;
    }
}

// registration removed intentionally