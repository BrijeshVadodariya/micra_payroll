/** @odoo-module **/

import { Component, onMounted, onWillUnmount, useState, xml } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

class HRMSBizCompassDashboard extends Component {
    static template = xml`
        <div t-att-class="'o_hrms_workspace_wrap o_hrms_workspace_scrollable ' + getThemeClass()" style="height:100%; overflow:auto;">
            <div class="o_hrms_workspace_shell container-fluid" style="padding-bottom:24px;">

                <t t-if="state.error">
                    <div class="alert alert-danger o_hrms_alert_box mb-4" role="alert">
                        <i class="fa fa-exclamation-circle me-2"/>
                        <t t-esc="state.error"/>
                    </div>
                </t>

                <section class="o_hrms_hero_card mb-4">
                    <div class="o_hrms_brand_strip">
                        <div class="o_hrms_company_logo_box">
                            <img
                                t-if="getCompanyLogo()"
                                t-att-src="getCompanyLogo()"
                                alt="Company Logo"
                                class="o_hrms_company_logo"
                            />
                            <div t-if="!getCompanyLogo()" class="o_hrms_company_logo_fallback">
                                <i class="fa fa-building-o"/>
                            </div>
                        </div>
                        <div class="o_hrms_brand_name_col">
                            <span class="o_hrms_company_name"><t t-esc="getCompanyName()"/></span>
                            <span class="o_hrms_brand_sub">Employee Dashboard</span>
                        </div>
                        <div class="o_hrms_brand_clock" id="o_hrms_wall_clock">00:00:00</div>
                    </div>

                    <div class="o_hrms_hero_body">
                        <div class="o_hrms_hero_left">
                            <div t-att-class="'o_hrms_status_pill ' + getAttendanceStatusClass()">
                                <span class="o_hrms_status_dot"/>
                                <t t-esc="attendanceStatusText"/>
                            </div>

                            <h2 class="o_hrms_greeting_title mt-2">
                                <t t-esc="getGreetingTitle()"/>
                            </h2>

                            <p class="o_hrms_greeting_subtitle">
                                <t t-esc="getGreetingSubtitle()"/>
                            </p>

                            <div class="o_hrms_action_row mt-3">
                                <button
                                    t-att-class="'btn o_hrms_btn_main1 ' + (isCheckedIn() ? 'danger' : 'primary')"
                                    t-on-click="toggleAttendance"
                                    t-att-disabled="state.loading"
                                >
                                    <i t-att-class="'fa ' + (isCheckedIn() ? 'fa-sign-out' : 'fa-sign-in') + ' me-2'"/>
                                    <t t-esc="attendanceActionText"/>
                                </button>

                                <button
                                    t-if="!isMobileDevice"
                                    t-att-class="'btn o_hrms_btn_main ' + (isOnBreak() ? 'warning' : 'success')"
                                    t-on-click="toggleBreak"
                                    t-att-disabled="state.loading || !isCheckedIn()"
                                >
                                    <i t-att-class="'fa ' + (isOnBreak() ? 'fa-play-circle' : 'fa-pause-circle') + ' me-2'"/>
                                    <t t-esc="breakActionText"/>
                                </button>

                                <button class="btn o_hrms_btn_soft" t-on-click="openLeaveApply">
                                    <i class="fa fa-calendar-plus-o me-2"/>Apply Leave
                                </button>

                                <button class="btn o_hrms_btn_soft" t-on-click="openMyTasks">
                                    <i class="fa fa-tasks me-2"/>My Tasks
                                </button>

                                <button class="btn o_hrms_btn_soft" t-on-click="toggleTheme" type="button">
                                    <i t-att-class="'fa ' + (state.theme === 'dark' ? 'fa-sun-o' : 'fa-moon-o') + ' me-2'"/>
                                    <t t-esc="state.theme === 'dark' ? 'Light Mode' : 'Dark Mode'"/>
                                </button>
                            </div>
                        </div>

                        <div class="o_hrms_today_panel">
                            <div class="o_hrms_today_panel_title d-flex align-items-center justify-content-between">
                                <div><i class="fa fa-calendar-check-o me-2"/>Today Snapshot</div>
                            </div>

                            <div class="o_hrms_today_grid">
                                <div class="o_hrms_today_item">
                                    <div class="o_hrms_today_label">
                                        <i class="fa fa-sign-in me-1"/>Check In
                                    </div>
                                    <div class="o_hrms_today_value">
                                        <t t-esc="getAttendanceCheckIn()"/>
                                    </div>
                                </div>

                                <div class="o_hrms_today_item">
                                    <div class="o_hrms_today_label">
                                        <i class="fa fa-sign-out me-1"/>Check Out
                                    </div>
                                    <div class="o_hrms_today_value">
                                        <t t-esc="getAttendanceCheckOut()"/>
                                    </div>
                                </div>

                                <div class="o_hrms_today_item">
                                    <div class="o_hrms_today_label">
                                        <i class="fa fa-coffee me-1"/>Break Status
                                    </div>
                                    <div class="o_hrms_today_value">
                                        <t t-esc="isOnBreak() ? 'On Break' : 'Not On Break'"/>
                                    </div>
                                </div>

                                <div class="o_hrms_today_item">
                                    <div class="o_hrms_today_label">
                                        <i class="fa fa-briefcase me-1"/>Worked Today
                                    </div>
                                    <div class="o_hrms_today_value">
                                        <t t-esc="state.liveWorkingTimeText"/>
                                    </div>
                                </div>
                            </div>


                        </div>
                    </div>
                </section>

                <section class="o_hrms_section_card mb-4">
                    <div class="o_hrms_section_header">
                        <div>
                            <h3 class="o_hrms_section_title">
                                <span class="o_hrms_live_dot"/>My Log Today
                            </h3>
                            <div class="o_hrms_section_subtitle">Live running attendance breakdown</div>
                        </div>
                        <div t-if="isCheckedIn()" t-att-class="'badge rounded-pill ' + (isOnBreak() ? 'text-bg-warning' : 'text-bg-success')">
                            <t t-esc="isOnBreak() ? 'On Break' : 'Working'"/>
                        </div>
                    </div>

                    <div class="row g-3">
                        <div class="col-12 col-md-4">
                            <div class="o_hrms_metric_card color-blue">
                                <div class="o_hrms_metric_glow"/>
                                <div class="o_hrms_metric_icon"><i class="fa fa-briefcase"/></div>
                                <div class="o_hrms_metric_label">Working Time</div>
                                <div class="o_hrms_metric_value o_hrms_live_timer" id="live_working">
                                    <t t-esc="state.liveWorkingTimeText"/>
                                </div>
                                <div class="o_hrms_metric_bar">
                                    <div class="o_hrms_metric_bar_fill blue" t-att-style="'width:' + getWorkingBarPct() + '%'"/>
                                    <div class="o_hrms_metric_bar_fill green" t-att-style="'width:' + getWorkingExtraBarPct() + '%'"/>
                                </div>
                                <div class="o_hrms_metric_hint">Live productive time</div>
                            </div>
                        </div>

                        <div class="col-12 col-md-4">
                            <div class="o_hrms_metric_card color-amber">
                                <div class="o_hrms_metric_glow"/>
                                <div class="o_hrms_metric_icon"><i class="fa fa-coffee"/></div>
                                <div class="o_hrms_metric_label">Break Time</div>
                                <div class="o_hrms_metric_value o_hrms_live_timer" id="live_break">
                                    <t t-esc="state.liveBreakTodayText"/>
                                </div>
                                <div class="o_hrms_metric_bar">
                                    <div class="o_hrms_metric_bar_fill amber" t-att-style="'width:' + getBreakBarPct() + '%'"/>
                                    <div class="o_hrms_metric_bar_fill red" t-att-style="'width:' + getBreakExtraBarPct() + '%'"/>
                                </div>
                                <div class="o_hrms_metric_hint">Live break duration</div>
                            </div>
                        </div>

                        <div class="col-12 col-md-4">
                            <div class="o_hrms_metric_card color-purple">
                                <div class="o_hrms_metric_glow"/>
                                <div class="o_hrms_metric_icon"><i class="fa fa-clock-o"/></div>
                                <div class="o_hrms_metric_label">Total Time</div>
                                <div class="o_hrms_metric_value o_hrms_live_timer" id="live_total">
                                    <t t-esc="state.liveOverallTotalText"/>
                                </div>
                                <div class="o_hrms_metric_bar">
                                    <div class="o_hrms_metric_bar_fill purple" t-att-style="'width:' + getTotalBarPct() + '%'"/>
                                </div>
                                <div class="o_hrms_metric_hint">Overall attendance duration</div>
                            </div>
                        </div>
                    </div>

                    <div class="mt-3">
                        <div
                            t-if="!isCheckedIn()"
                            class="o_hrms_log_status_box"
                            style="background:#f8fafc; border:1px solid #e5e7eb; color:#475569;"
                        >
                            <i class="fa fa-clock-o me-2"/>
                            <span>You are checked out. All timers are stopped.</span>
                        </div>
                    </div>
                </section>

                <section class="o_hrms_section_card mb-4">
                    <div class="o_hrms_section_header">
                        <div>
                            <h3 class="o_hrms_section_title">
                                <i class="fa fa-calendar me-2"/>Monthly Attendance Log
                            </h3>
                            <div class="o_hrms_section_subtitle">Monthly attendance summary</div>
                        </div>
                    </div>

                    <div class="row g-3">
                        <div class="col-12 col-md-6 col-xl">
                            <div class="o_hrms_metric_card color-blue">
                                <div class="o_hrms_metric_glow"/>
                                <div class="o_hrms_metric_icon"><i class="fa fa-calendar-o"/></div>
                                <div class="o_hrms_metric_label">Working Days</div>
                                <div class="o_hrms_metric_value">
                                    <t t-esc="getMonthWorkingDays()"/>
                                </div>
                                <div class="o_hrms_metric_hint">Planned working days</div>
                            </div>
                        </div>

                        <div class="col-12 col-md-6 col-xl">
                            <div class="o_hrms_metric_card color-purple">
                                <div class="o_hrms_metric_glow"/>
                                <div class="o_hrms_metric_icon"><i class="fa fa-clock-o"/></div>
                                <div class="o_hrms_metric_label">Hours</div>
                                <div class="o_hrms_metric_value">
                                    <t t-esc="getMonthWorkingHours()"/>
                                </div>
                                <div class="o_hrms_metric_hint">Planned working hours</div>
                            </div>
                        </div>

                        <div class="col-12 col-md-6 col-xl">
                            <div class="o_hrms_metric_card color-green">
                                <div class="o_hrms_metric_glow"/>
                                <div class="o_hrms_metric_icon"><i class="fa fa-check-square-o"/></div>
                                <div class="o_hrms_metric_label">Worked Days</div>
                                <div class="o_hrms_metric_value">
                                    <t t-esc="getMonthWorkedDays()"/>
                                </div>
                                <div class="o_hrms_metric_hint">Actual attended days</div>
                            </div>
                        </div>

                        <div class="col-12 col-md-6 col-xl">
                            <div class="o_hrms_metric_card color-amber">
                                <div class="o_hrms_metric_glow"/>
                                <div class="o_hrms_metric_icon"><i class="fa fa-line-chart"/></div>
                                <div class="o_hrms_metric_label">Worked Hours</div>
                                <div class="o_hrms_metric_value">
                                    <t t-esc="getMonthWorkedHoursDisplay()"/>
                                </div>
                                <div class="o_hrms_metric_hint">Actual worked hours</div>
                            </div>
                        </div>

                        <div class="col-12 col-md-6 col-xl">
                            <div class="o_hrms_metric_card color-pink">
                                <div class="o_hrms_metric_glow"/>
                                <div class="o_hrms_metric_icon"><i class="fa fa-clock-o"/></div>
                                <div class="o_hrms_metric_label">Late Days</div>
                                <div class="o_hrms_metric_value">
                                    <t t-esc="getMonthLateDays()"/>
                                </div>
                                <div class="o_hrms_metric_hint">In this month</div>
                            </div>
                        </div>
                    </div>
                </section>

                

                <section class="o_hrms_section_card mb-4">
                    <div class="o_hrms_timer_header">
                        <div>
                            <h3 class="o_hrms_section_title">Project Task Timer</h3>
                            <div class="o_hrms_section_subtitle">Select a task from table or dropdown and start live tracking</div>
                        </div>
                        <div t-att-class="'o_hrms_timer_status_badge ' + getTimerStatusClass()">
                            <span class="o_hrms_timer_status_dot"/>
                            <t t-esc="getTimerStatusText()"/>
                        </div>
                    </div>

                    <div class="row g-3 mb-4">
                        <div class="col-12 col-lg-4">
                            <div class="o_hrms_timer_name_card o_hrms_timer_project_card">
                                <div class="o_hrms_timer_small_label">Selected Project</div>
                                <div class="o_hrms_timer_selected_name">
                                    <i class="fa fa-folder-open me-2"/>
                                    <t t-esc="getSelectedProjectName()"/>
                                </div>
                            </div>
                        </div>

                        <div class="col-12 col-lg-4">
                            <div class="o_hrms_timer_name_card o_hrms_timer_task_card">
                                <div class="o_hrms_timer_small_label">Selected Task</div>
                                <div class="o_hrms_timer_selected_name">
                                    <i class="fa fa-check-square-o me-2"/>
                                    <t t-esc="getSelectedTaskName()"/>
                                </div>
                            </div>
                        </div>

                        <div class="col-12 col-lg-4">
                            <div class="o_hrms_timer_clock_info o_hrms_timer_clock_big">
                                <div class="o_hrms_timer_small_label">Live Timer</div>
                                <div class="o_hrms_timer_big_value o_hrms_live_timer" id="live_task_timer">
                                    <t t-esc="state.liveTimerText"/>
                                </div>
                                <button
                                    class="btn o_hrms_btn_soft mt-2"
                                    type="button"
                                    t-on-click="openCurrentTimerTask"
                                    t-att-disabled="!getCurrentTimerTaskId()"
                                >
                                    <i class="fa fa-external-link me-2"/>Open Running Task
                                </button>
                            </div>
                        </div>
                    </div>

                    <div class="row g-3 mb-4">
                        <div class="col-12 col-md-6">
                            <label class="o_hrms_form_label">Select Project</label>
                            <select
                                class="form-select o_hrms_select"
                                t-on-change="onProjectSelectionChange"
                                t-att-disabled="areSelectorsLocked()"
                            >
                                <option value="">All Projects</option>
                                <t t-foreach="state.projectOptions" t-as="project" t-key="project.id">
                                    <option t-att-value="project.id" t-att-selected="isSelectedProject(project.id)">
                                        <t t-esc="project.name"/>
                                    </option>
                                </t>
                            </select>
                        </div>
                        <div class="col-12 col-md-6">
                            <label class="o_hrms_form_label">Select Task</label>
                            <div class="input-group">
                                <select
                                    class="form-select o_hrms_select"
                                    t-on-change="onTaskSelectionChange"
                                    t-att-disabled="areSelectorsLocked()"
                                    style="border-top-right-radius: 0; border-bottom-right-radius: 0;"
                                >
                                    <option value="">Select Task</option>
                                    <t t-foreach="filteredTaskOptions" t-as="task" t-key="task.id">
                                        <option t-att-value="task.id" t-att-selected="isSelectedTask(task.id)">
                                            <t t-esc="task.name"/>
                                        </option>
                                    </t>
                                </select>
                                <button t-if="state.selectedProjectId" class="btn btn-primary" type="button" t-on-click="addNewTask" style="border-top-left-radius: 0; border-bottom-left-radius: 0; min-height: 40px; padding: 0 15px; background-color: #6c5ffc; border-color: #6c5ffc;">
                                    <i class="fa fa-plus"/>
                                </button>
                            </div>
                        </div>
                    </div>

                    <div class="o_hrms_timer_buttons d-flex justify-content-center flex-wrap gap-3 mt-3">
                        <!-- 1. Start/Stop Toggle Button -->
                        <button t-attf-class="btn o_hrms_timer_btn #{dynamicMainButtonClass}" 
                                t-on-click="onTimerButtonClick" 
                                t-att-data-action="dynamicMainButtonAction"
                                t-att-disabled="state.loading || (dynamicMainButtonAction === 'start' &amp;&amp; !canStart)">
                            <i t-attf-class="fa #{dynamicMainButtonIcon} me-2"/>
                            <t t-esc="dynamicMainButtonLabel"/>
                        </button>

                        <!-- 2. Pause/Resume Toggle Button -->
                        <button t-if="isTimerRunning() || isTimerPaused()"
                                t-attf-class="btn o_hrms_timer_btn #{dynamicSecondaryButtonClass}" 
                                t-on-click="onTimerButtonClick" 
                                t-att-data-action="dynamicSecondaryButtonAction"
                                t-att-disabled="state.loading">
                            <i t-attf-class="fa #{dynamicSecondaryButtonIcon} me-2"/>
                            <t t-esc="dynamicSecondaryButtonLabel"/>
                        </button>

                        <!-- 3. Cancel Button -->
                        <button t-if="isTimerRunning() || isTimerPaused()"
                                class="btn o_hrms_timer_btn cancel" 
                                t-on-click="onTimerButtonClick" 
                                data-action="cancel"
                                t-att-disabled="state.loading">
                            <i class="fa fa-times me-2"/>Cancel
                        </button>
                    </div>
                </section>

                <div class="row g-4 pb-4">
                    <div class="col-12">
                        <section class="o_hrms_section_card o_hrms_fixed_list_card">
                            <div class="o_hrms_section_header">
                                <div>
                                    <h3 class="o_hrms_section_title">Tasks for Selected Project</h3>
                                    <div class="o_hrms_section_subtitle">Click row to select task for timer</div>
                                </div>
                                <div class="o_hrms_count_badge"><t t-esc="filteredDashboardTasks.length"/></div>
                            </div>

                            <div class="o_hrms_task_table_scroll">
                                <table class="table o_hrms_table mb-0 align-middle">
                                    <thead>
                                        <tr>
                                            <th style="width:34%;">Task</th>
                                            <th style="width:22%;">Project</th>
                                            <th style="width:16%;">Stage</th>
                                            <th style="width:16%;">Deadline</th>
                                            <th style="width:12%;" class="text-center">Action</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        <tr t-if="!filteredDashboardTasks.length">
                                            <td colspan="5" class="text-center text-muted py-4">
                                                No tasks found for selected project.
                                            </td>
                                        </tr>

                                        <tr
                                            t-foreach="filteredDashboardTasks"
                                            t-as="task"
                                            t-key="task.id"
                                            t-on-click="onTaskRowSelect"
                                            t-att-data-task-id="task.id"
                                            t-att-class="'o_hrms_task_row ' + (isSelectedTask(task.id) ? 'selected' : '')"
                                            style="cursor:pointer;"
                                        >
                                            <td>
                                                <div class="o_hrms_task_name_cell">
                                                    <div class="o_hrms_task_primary_name">
                                                        <t t-esc="task.name || '-'"/>
                                                    </div>
                                                </div>
                                            </td>
                                            <td><t t-esc="task.project_name || '-'"/></td>
                                            <td><span class="o_hrms_chip_table"><t t-esc="task.stage_name || '-'"/></span></td>
                                            <td><t t-esc="task.deadline || '-'"/></td>
                                            <td class="text-center">
                                                <button
                                                    type="button"
                                                    class="btn btn-sm o_hrms_row_open_btn"
                                                    t-on-click.stop="openTaskFromButton"
                                                    t-att-data-task-id="task.id"
                                                >
                                                    <i class="fa fa-external-link me-1"/>Open
                                                </button>
                                            </td>
                                        </tr>
                                    </tbody>
                                </table>
                            </div>
                        </section>
                    </div>
                </div>

                <div class="row g-4 pb-4">
                    <div class="col-12">
                        <section class="o_hrms_section_card o_hrms_fixed_list_card">
                            <div class="o_hrms_section_header">
                                <div>
                                    <h3 class="o_hrms_section_title">My Leaves</h3>
                                    <div class="o_hrms_section_subtitle">Leave records and quick apply option</div>
                                </div>
                                <button class="btn o_hrms_btn_soft" t-on-click="openLeaveApply">Apply Leave</button>
                            </div>

                            <div t-if="!hasLeaves()" class="o_hrms_empty_state o_hrms_scroll_body">
                                <i class="fa fa-umbrella o_hrms_empty_icon"/>
                                <div>No current leave records.</div>
                            </div>

                            <div t-if="hasLeaves()" class="o_hrms_scroll_body">
                                <div
                                    t-foreach="getLeaves()"
                                    t-as="item"
                                    t-key="'leave_' + item.id"
                                    class="o_hrms_leave_card"
                                    t-on-click="openLeaveFromCard"
                                    t-att-data-leave-id="item.id"
                                    style="cursor:pointer;"
                                >
                                    <div class="o_hrms_leave_title"><t t-esc="item.holiday_status || item.name || '-'"/></div>
                                    <div class="o_hrms_leave_meta">
                                        <t t-esc="item.date_from || '-'"/> → <t t-esc="item.date_to || '-'"/>
                                    </div>
                                </div>
                            </div>
                        </section>
                    </div>
                </div>

                <div class="row g-4 pb-4">
                    <div class="col-12 col-xl-6">
                        <section class="o_hrms_section_card h-100 o_hrms_fixed_list_card">
                            <div class="o_hrms_section_header">
                                <div>
                                    <h3 class="o_hrms_section_title">Upcoming Birthdays</h3>
                                </div>
                                <div class="o_hrms_count_badge"><t t-esc="getBirthdays().length"/></div>
                            </div>

                            <div t-if="!getBirthdays().length" class="o_hrms_empty_state o_hrms_scroll_body">
                                <i class="fa fa-birthday-cake o_hrms_empty_icon"/>
                                <div>No upcoming birthdays.</div>
                            </div>

                            <div t-if="getBirthdays().length" class="o_hrms_scroll_body">
                                <div
                                    t-foreach="getBirthdays()"
                                    t-as="item"
                                    t-key="'birthday_' + item.id"
                                    class="o_hrms_leave_card"
                                >
                                    <div class="o_hrms_leave_title">
                                        <i class="fa fa-birthday-cake me-2"/> <t t-esc="item.name || '-'"/>
                                    </div>
                                    <div class="o_hrms_leave_meta">
                                        <t t-esc="item.next_date || '-'"/> • In <t t-esc="item.days_left"/> day(s)
                                    </div>
                                    <div class="o_hrms_leave_meta" t-if="item.age">
                                        Turning <t t-esc="item.age"/>
                                    </div>
                                </div>
                            </div>
                        </section>
                    </div>

                    <div class="col-12 col-xl-6">
                        <section class="o_hrms_section_card h-100 o_hrms_fixed_list_card">
                            <div class="o_hrms_section_header">
                                <div>
                                    <h3 class="o_hrms_section_title">Work Anniversaries</h3>
                                </div>
                                <div class="o_hrms_count_badge"><t t-esc="getAnniversaries().length"/></div>
                            </div>

                            <div t-if="!getAnniversaries().length" class="o_hrms_empty_state o_hrms_scroll_body">
                                <i class="fa fa-trophy o_hrms_empty_icon"/>
                                <div>No upcoming anniversaries.</div>
                            </div>

                            <div t-if="getAnniversaries().length" class="o_hrms_scroll_body">
                                <div
                                    t-foreach="getAnniversaries()"
                                    t-as="item"
                                    t-key="'anniversary_' + item.id"
                                    class="o_hrms_leave_card"
                                >
                                    <div class="o_hrms_leave_title">
                                        <i class="fa fa-star me-2"/> <t t-esc="item.name || '-'"/>
                                    </div>
                                    <div class="o_hrms_leave_meta">
                                        <t t-esc="item.next_date || '-'"/> • In <t t-esc="item.days_left"/> day(s)
                                    </div>
                                    <div class="o_hrms_leave_meta" t-if="item.years">
                                        Completing <t t-esc="item.years"/> year(s)
                                    </div>
                                </div>
                            </div>
                        </section>
                    </div>
                </div>

                <div class="row g-4 pb-4">
                    <div class="col-12 col-xl-6">
                        <section class="o_hrms_section_card h-100 o_hrms_fixed_list_card">
                            <div class="o_hrms_section_header">
                                <div>
                                    <h3 class="o_hrms_section_title">Upcoming Holidays</h3>
                                    <div class="o_hrms_section_subtitle">Holiday calendar highlights</div>
                                </div>
                                <div class="o_hrms_count_badge"><t t-esc="getHolidays().length"/></div>
                            </div>

                            <div t-if="!getHolidays().length" class="o_hrms_empty_state o_hrms_scroll_body">
                                <i class="fa fa-sun-o o_hrms_empty_icon"/>
                                <div>No upcoming holidays.</div>
                            </div>

                            <div t-if="getHolidays().length" class="o_hrms_scroll_body">
                                <div
                                    t-foreach="getHolidays()"
                                    t-as="item"
                                    t-key="'holiday_' + item.id"
                                    class="o_hrms_leave_card"
                                >
                                    <div class="o_hrms_leave_title"><t t-esc="item.name || '-'"/></div>
                                    <div class="o_hrms_leave_meta">
                                        <i class="fa fa-calendar me-2"/><t t-esc="item.date_range_display || '-'"/>
                                    </div>
                                    <div class="o_hrms_leave_meta" t-if="item.duration_label">
                                        <i class="fa fa-clock-o me-2"/>Duration: <t t-esc="item.duration_label"/>
                                    </div>
                                </div>
                            </div>
                        </section>
                    </div>

                    <div class="col-12 col-xl-6">
                        <section class="o_hrms_section_card h-100 o_hrms_fixed_list_card">
                            <div class="o_hrms_section_header">
                                <div>
                                    <h3 class="o_hrms_section_title">Upcoming Events</h3>
                                    <div class="o_hrms_section_subtitle">Scrollable upcoming event list</div>
                                </div>
                                <div class="o_hrms_count_badge"><t t-esc="getEvents().length"/></div>
                            </div>

                            <div t-if="!getEvents().length" class="o_hrms_empty_state o_hrms_scroll_body">
                                <i class="fa fa-calendar o_hrms_empty_icon"/>
                                <div>No upcoming events.</div>
                            </div>

                            <div t-if="getEvents().length" class="o_hrms_scroll_body">
                                <div
                                    t-foreach="getEvents()"
                                    t-as="item"
                                    t-key="'event_' + item.id"
                                    class="o_hrms_leave_card"
                                >
                                    <div class="o_hrms_leave_title"><t t-esc="item.name || '-'"/></div>
                                    <div class="o_hrms_leave_meta"><t t-esc="item.start || '-'"/></div>
                                    <div class="o_hrms_leave_meta" t-if="item.location">
                                        <i class="fa fa-map-marker me-1"/> <t t-esc="item.location"/>
                                    </div>
                                </div>
                            </div>
                        </section>
                    </div>
                </div>

                <section class="o_hrms_section_card mb-4">
                    <div class="o_hrms_section_header">
                        <div>
                            <h3 class="o_hrms_section_title">
                                <i class="fa fa-umbrella me-2"/>Leave Summary
                            </h3>
                            <div class="o_hrms_section_subtitle">1 leave credited for each completed month of service</div>
                        </div>
                    </div>

                    <div class="row g-3">
                        <div class="col-12 col-md-4">
                            <div class="o_hrms_metric_card color-amber">
                                <div class="o_hrms_metric_glow"/>
                                <div class="o_hrms_metric_icon"><i class="fa fa-minus-circle"/></div>
                                <div class="o_hrms_metric_label">Consumed Paid Leave</div>
                                <div class="o_hrms_metric_value">
                                    <t t-esc="getLeaveConsumedTotal()"/>
                                </div>
                            </div>
                        </div>

                        <div class="col-12 col-md-4">
                            <div class="o_hrms_metric_card color-purple">
                                <div class="o_hrms_metric_glow"/>
                                <div class="o_hrms_metric_icon"><i class="fa fa-minus-square-o"/></div>
                                <div class="o_hrms_metric_label">Consumed Unpaid Leave</div>
                                <div class="o_hrms_metric_value">
                                    <t t-esc="getLeaveConsumedUnpaidTotal()"/>
                                </div>
                            </div>
                        </div>

                        <div class="col-12 col-md-4">
                            <div class="o_hrms_metric_card color-green">
                                <div class="o_hrms_metric_glow"/>
                                <div class="o_hrms_metric_icon"><i class="fa fa-check-circle-o"/></div>
                                <div class="o_hrms_metric_label">Remaining Paid Leave</div>
                                <div class="o_hrms_metric_value">
                                    <t t-esc="getLeaveRemainingTotal()"/>
                                </div>
                            </div>
                        </div>
                    </div>
                </section>
            </div>
        </div>
    `;

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");

        this.state = useState({
            loading: false,
            error: "",
            data: {},
            taskOptions: [],
            projectOptions: [],
            selectedTaskId: "",
            selectedTaskName: "",
            selectedProjectId: "",
            selectedProjectName: "",
            selectorsLockedByTimer: false,

            liveTimerText: "00:00:00",
            liveOverallTotalText: "00:00:00",
            liveWorkingTimeText: "00:00:00",
            liveBreakTodayText: "00:00:00",

            tickInterval: null,
            refreshInterval: null,
            wallClockInterval: null,

            timerBaseSeconds: 0,
            timerSyncMs: Date.now(),

            theme: "light",
            serverTimeOffsetMs: 0,
        });

        this.onVisibilityChange = this.onVisibilityChange.bind(this);

        onMounted(async () => {
            this.loadTheme();
            await this.refresh();
            this.startLiveTickers();
            this.startAutoRefresh();
            this.startWallClock();
            document.addEventListener("visibilitychange", this.onVisibilityChange);
        });

        onWillUnmount(() => {
            this.stopIntervals();
            document.removeEventListener("visibilitychange", this.onVisibilityChange);
        });
    }

    loadTheme() {
        try {
            const savedTheme = window.localStorage.getItem("hrms_workspace_theme");
            this.state.theme = savedTheme === "dark" ? "dark" : "light";
        } catch {
            this.state.theme = "light";
        }
        this.applyThemeToBody();
    }

    saveTheme() {
        try {
            window.localStorage.setItem("hrms_workspace_theme", this.state.theme);
        } catch {
            //
        }
    }

    applyThemeToBody() {
        try {
            document.body.classList.remove("o_hrms_theme_light", "o_hrms_theme_dark");
            document.body.classList.add(this.state.theme === "dark" ? "o_hrms_theme_dark" : "o_hrms_theme_light");
        } catch {
            //
        }
    }

    toggleTheme() {
        this.state.theme = this.state.theme === "dark" ? "light" : "dark";
        this.saveTheme();
        this.applyThemeToBody();
        this.notification.add(
            this.state.theme === "dark" ? "Dark mode enabled." : "Light mode enabled.",
            { type: "success" }
        );
    }

    getThemeClass() {
        return this.state.theme === "dark" ? "o_hrms_theme_dark" : "o_hrms_theme_light";
    }

    startWallClock() {
        const tick = () => {
            const el = document.getElementById("o_hrms_wall_clock");
            if (el) {
                const now = new Date();
                const h = String(now.getHours()).padStart(2, "0");
                const m = String(now.getMinutes()).padStart(2, "0");
                const s = String(now.getSeconds()).padStart(2, "0");
                el.textContent = `${h}:${m}:${s}`;
            }
        };
        tick();
        this.state.wallClockInterval = setInterval(tick, 1000);
    }

    getWorkingBarPct() {
        const val = this.hhmmssToSeconds(this.state.liveWorkingTimeText || "00:00:00");
        const target = 28800;
        if (val <= target) return Math.round((val / target) * 100);
        const extraRaw = ((val - target) / val) * 100;
        const extraPct = Math.max(3, Math.round(extraRaw));
        return 100 - extraPct;
    }

    getWorkingExtraBarPct() {
        const val = this.hhmmssToSeconds(this.state.liveWorkingTimeText || "00:00:00");
        const target = 28800;
        if (val <= target) return 0;
        const extraRaw = ((val - target) / val) * 100;
        return Math.max(3, Math.round(extraRaw));
    }

    getBreakBarPct() {
        const val = this.hhmmssToSeconds(this.state.liveBreakTodayText || "00:00:00");
        const target = 3600;
        if (val <= target) return Math.round((val / target) * 100);
        const extraRaw = ((val - target) / val) * 100;
        const extraPct = Math.max(3, Math.round(extraRaw));
        return 100 - extraPct;
    }

    getBreakExtraBarPct() {
        const val = this.hhmmssToSeconds(this.state.liveBreakTodayText || "00:00:00");
        const target = 3600;
        if (val <= target) return 0;
        const extraRaw = ((val - target) / val) * 100;
        return Math.max(3, Math.round(extraRaw));
    }

    getTotalBarPct() {
        const val = this.hhmmssToSeconds(this.state.liveOverallTotalText || "00:00:00");
        const target = 32400;
        if (val <= target) return Math.round((val / target) * 100);
        const extraRaw = ((val - target) / val) * 100;
        const extraPct = Math.max(3, Math.round(extraRaw));
        return 100 - extraPct;
    }

    getTotalExtraBarPct() {
        const val = this.hhmmssToSeconds(this.state.liveOverallTotalText || "00:00:00");
        const target = 32400;
        if (val <= target) return 0;
        const extraRaw = ((val - target) / val) * 100;
        return Math.max(3, Math.round(extraRaw));
    }

    isCompletedTask(task) {
        const stageName = String(task?.stage_name || "").trim().toLowerCase();
        return ["completed", "done"].includes(stageName);
    }

    get filteredTaskOptions() {
        const tasks = this.state.taskOptions || [];
        const projectId = String(this.state.selectedProjectId || "");

        const activeTasks = tasks.filter((t) => !this.isCompletedTask(t));

        if (!projectId) return activeTasks;
        return activeTasks.filter((t) => String(t.project_id || "") === projectId);
    }

    get filteredDashboardTasks() {
        const tasks = this.getTasks();
        const projectId = String(this.state.selectedProjectId || "");
        if (!projectId) return tasks;
        return tasks.filter((t) => String(t.project_id || "") === projectId);
    }

    get attendanceStatusText() {
        const attendance = this.state.data.attendance || {};
        if (attendance.checked_in && attendance.is_on_break) return "On Break";
        if (attendance.checked_in) return "Checked In";
        return "Checked Out";
    }

    get attendanceActionText() {
        return this.isCheckedIn() ? "Check Out" : "Check In";
    }

    get breakActionText() {
        return this.isOnBreak() ? "Break Out" : "Break In";
    }

    get isMobileDevice() {
        const ua = navigator.userAgent;

        if (/Windows/i.test(ua)) {
            return false;
        }

        const isMobileUA = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini|Mobile/i.test(ua);

        const isTouch = ('ontouchstart' in window) || (navigator.maxTouchPoints > 0);

        const isIpadSpoof = /Macintosh/i.test(ua) && isTouch;

        const isPhoneScreen = Math.min(window.screen.width, window.screen.height) <= 600;

        return isMobileUA || isIpadSpoof || (isTouch && isPhoneScreen);
    }

    get canStart() {
        return !!this.state.selectedTaskId && !this.isTimerRunning() && !this.isTimerPaused();
    }

    getCompany() { return this.state.data.company || {}; }
    getCompanyName() { return this.getCompany().name || "Company"; }
    getCompanyLogo() { return this.getCompany().logo_url || ""; }
    getEmployee() { return this.state.data.employee || {}; }
    getEmployeeName() { return this.getEmployee().name || "Employee"; }
    getCurrentUserId() { return (this.state.data.employee || {}).user_id || false; }
    getGreetingTitle() { return `${this.getDayGreeting()}, ${this.getEmployeeName()}`; }
    getTasks() { return this.state.data.tasks || []; }
    getLeaves() { return this.state.data.leaves || []; }
    getEvents() { return this.state.data.events || []; }
    getHolidays() { return this.state.data.holidays || []; }
    getBirthdays() { return this.state.data.birthdays || []; }
    getAnniversaries() { return this.state.data.work_anniversaries || []; }
    hasLeaves() { return this.getLeaves().length > 0; }
    isCheckedIn() { return !!(this.state.data.attendance || {}).checked_in; }
    isOnBreak() { return !!(this.state.data.attendance || {}).is_on_break; }
    isTimerRunning() { return !!(this.state.data.timer || {}).running; }
    isTimerPaused() { return !!(this.state.data.timer || {}).paused; }
    canStopOrCancel() { return this.isTimerRunning() || this.isTimerPaused(); }
    areSelectorsLocked() { return this.state.selectorsLockedByTimer && (this.isTimerRunning() || this.isTimerPaused()); }
    isSelectedTask(id) { return String(this.state.selectedTaskId || "") === String(id || ""); }
    isSelectedProject(id) { return String(this.state.selectedProjectId || "") === String(id || ""); }
    getAttendanceCheckIn() { return (this.state.data.attendance || {}).check_in_display || (this.state.data.attendance || {}).check_in || "-"; }
    getAttendanceCheckOut() { return (this.state.data.attendance || {}).check_out_display || (this.state.data.attendance || {}).check_out || "-"; }
    getMonthAttendance() { return this.state.data.month_attendance || {}; }
    getMonthWorkingDays() { return this.getMonthAttendance().working_days || 0; }
    getMonthWorkingHours() { return `${this.getMonthAttendance().working_hours || 0}h`; }
    getMonthWorkedDays() { return this.getMonthAttendance().worked_days || 0; }
    getMonthWorkedHoursDisplay() { return this.getMonthAttendance().worked_hours_display || "0h 0m"; }
    getMonthLateDays() { return this.getMonthAttendance().late_days || 0; }
    getTicketsRemaining() { return this.getMonthAttendance().tickets_remaining !== undefined ? this.getMonthAttendance().tickets_remaining : 4; }
    getTicketViolations() { return this.getMonthAttendance().ticket_violations || 0; }
    getCurrentViolateTicket() { return this.getMonthAttendance().unrevoked_ticket_violations || 0; }
    getCompensationDays() { return this.getMonthAttendance().compensation_days || 0; }
    getTotalTicketsRemaining() { return this.getCompensationDays() + this.getTicketsRemaining(); }
    getLeaveSummary() { return this.state.data.leave_summary || {}; }
    getLeaveAvailableTotal() { return this.formatLeaveNumber(this.getLeaveSummary().available_total || 0); }
    getLeaveAccruedTotal() { return this.formatLeaveNumber(this.getLeaveSummary().accrued_total || 0); }
    getLeaveAllocatedManual() { return this.formatLeaveNumber(this.getLeaveSummary().allocated_manual || 0); }
    getLeaveConsumedTotal() { return this.formatLeaveNumber(this.getLeaveSummary().consumed_total || 0); }
    getLeaveConsumedUnpaidTotal() { return this.formatLeaveNumber(this.getLeaveSummary().consumed_unpaid_total || 0); }
    getLeaveRemainingTotal() { return this.formatLeaveNumber(this.getLeaveSummary().remaining_total || 0); }
    getLeaveMonthlyCredit() { return `${this.formatLeaveNumber(this.getLeaveSummary().monthly_credit || 0)} / month`; }
    getLeaveServiceMonths() { return this.getLeaveSummary().service_months || 0; }

    getSelectedTaskName() {
        if (this.state.selectedTaskName) return this.state.selectedTaskName;
        return (this.state.data.timer || {}).task_name || "No task selected";
    }

    getSelectedProjectName() {
        if (this.state.selectedProjectName) return this.state.selectedProjectName;
        return (this.state.data.timer || {}).project_name || "All Projects";
    }

    getCurrentTimerTaskId() {
        const timer = this.state.data.timer || {};
        return timer.task_id || this.state.selectedTaskId || false;
    }

    getTimerStatusText() {
        if (this.isTimerRunning()) return "Running";
        if (this.isTimerPaused()) return "Paused";
        return "Idle";
    }

    getTimerStatusClass() {
        if (this.isTimerRunning()) return "running";
        if (this.isTimerPaused()) return "paused";
        return "idle";
    }

    get dynamicMainButtonLabel() { return (this.isTimerRunning() || this.isTimerPaused()) ? "Stop" : "Start"; }
    get dynamicMainButtonAction() { return (this.isTimerRunning() || this.isTimerPaused()) ? "stop" : "start"; }
    get dynamicMainButtonIcon() { return (this.isTimerRunning() || this.isTimerPaused()) ? "fa-stop" : "fa-play"; }
    get dynamicMainButtonClass() { return (this.isTimerRunning() || this.isTimerPaused()) ? "stop" : "start"; }

    get dynamicSecondaryButtonLabel() { return this.isTimerPaused() ? "Resume" : "Pause"; }
    get dynamicSecondaryButtonAction() { return this.isTimerPaused() ? "resume" : "pause"; }
    get dynamicSecondaryButtonIcon() { return this.isTimerPaused() ? "fa-play-circle" : "fa-pause"; }
    get dynamicSecondaryButtonClass() { return this.isTimerPaused() ? "resume" : "pause"; }

    getAttendanceStatusClass() {
        if (this.isOnBreak()) return "break";
        if (this.isCheckedIn()) return "active";
        return "inactive";
    }

    getGreetingSubtitle() {
        if (this.isCheckedIn() && this.isOnBreak()) {
            return "You are checked in and currently on break. Break hours are running and working hours are paused.";
        }
        if (this.isCheckedIn()) {
            return "You are checked in. Working hours and total hours are running live.";
        }
        return "You are currently checked out. Check in to start attendance and work tracking.";
    }

    getDayGreeting() {
        const h = new Date().getHours();
        if (h < 12) return "Good Morning";
        if (h < 17) return "Good Afternoon";
        return "Good Evening";
    }

    hhmmssToSeconds(value) {
        if (!value || typeof value !== "string") return 0;
        const parts = value.split(":").map(Number);
        if (parts.length !== 3 || parts.some(isNaN)) return 0;
        return (parts[0] * 3600) + (parts[1] * 60) + parts[2];
    }

    formatSeconds(totalSeconds) {
        const secs = Math.max(0, Math.floor(totalSeconds || 0));
        const h = String(Math.floor(secs / 3600)).padStart(2, "0");
        const m = String(Math.floor((secs % 3600) / 60)).padStart(2, "0");
        const s = String(secs % 60).padStart(2, "0");
        return `${h}:${m}:${s}`;
    }

    getElapsedSeconds(syncMs, nowMs = Date.now()) {
        return Math.max(0, Math.floor((nowMs - (syncMs || nowMs)) / 1000));
    }

    getServerNow() {
        const offset = this.state.serverTimeOffsetMs || 0;
        return new Date(Date.now() + offset);
    }

    parseServerDateTime(value) {
        if (!value || value === "-") return null;
        try {
            const normalized = String(value).replace(" ", "T");
            const hasTimezone = /[zZ]|[+-]\d{2}:\d{2}$/.test(normalized);
            const dt = new Date(hasTimezone ? normalized : `${normalized}Z`);
            return Number.isNaN(dt.getTime()) ? null : dt;
        } catch {
            return null;
        }
    }

    secondsBetween(startDate, endDate) {
        if (!startDate || !endDate) return 0;
        return Math.max(0, Math.floor((endDate.getTime() - startDate.getTime()) / 1000));
    }

    formatDateMonDDYYYY(value) {
        if (!value || value === "-") return "-";
        try {
            const date = this.parseServerDateTime(value) || new Date(value);
            if (!date || Number.isNaN(date.getTime())) return value;
            return date.toLocaleDateString("en-US", {
                month: "short",
                day: "2-digit",
                year: "numeric",
            });
        } catch {
            return value;
        }
    }

    formatOdooDateTime(value) {
        if (!value || value === "-") return "-";
        try {
            const utcDate = this.parseServerDateTime(value);
            if (!utcDate) return value;
            return utcDate.toLocaleString("en-US", {
                month: "short",
                day: "2-digit",
                year: "numeric",
                hour: "2-digit",
                minute: "2-digit",
                second: "2-digit",
                hour12: true,
            });
        } catch {
            return value;
        }
    }

    formatLeaveNumber(value) {
        const num = Number(value || 0);
        if (Number.isNaN(num)) return "0";
        return Number.isInteger(num) ? String(num) : num.toFixed(1);
    }

    normalizeTaskRows(rows) {
        return (rows || []).map((t) => ({
            ...t,
            deadline: t.deadline && t.deadline !== "-" ? this.formatDateMonDDYYYY(t.deadline) : "-",
        }));
    }

    normalizeListRows(rows, ...keys) {
        return (rows || []).map((r) => {
            const item = { ...r };
            for (const key of keys) {
                if (item[key]) item[key] = this.formatDateMonDDYYYY(item[key]);
            }
            return item;
        });
    }

    normalizeAttendance(attendance) {
        const row = { ...(attendance || {}) };
        if (row.check_in) row.check_in_display = this.formatOdooDateTime(row.check_in);
        if (row.check_out) row.check_out_display = this.formatOdooDateTime(row.check_out);
        return row;
    }

    syncAttendanceBases() {
        const attendance = this.state.data.attendance || {};
        this.state.liveOverallTotalText = attendance.overall_time_display || "00:00:00";
        this.state.liveWorkingTimeText = attendance.worked_time_display || "00:00:00";
        this.state.liveBreakTodayText = attendance.total_break_time_display || "00:00:00";
        this.state.liveProductiveTimeText = attendance.productive_time_display || "00:00:00";
    }

    getActiveBreakStart(attendance) {
        return (
            attendance.current_break_start_raw ||
            attendance.break_start_raw ||
            attendance.last_break_start_raw ||
            attendance.current_break_start ||
            attendance.break_start ||
            attendance.last_break_start ||
            false
        );
    }

    updateLiveAttendanceTexts() {
        const attendance = this.state.data.attendance || {};

        if (!attendance.checked_in) {
            this.state.liveOverallTotalText = attendance.overall_time_display || "00:00:00";
            this.state.liveBreakTodayText = attendance.total_break_time_display || "00:00:00";
            this.state.liveWorkingTimeText = attendance.worked_time_display || "00:00:00";
            this.state.liveProductiveTimeText = attendance.productive_time_display || "00:00:00";
            return;
        }

        const now = this.getServerNow();
        const serverTime = this.parseServerDateTime(this.state.data.server_time);

        const elapsed = serverTime ? this.secondsBetween(serverTime, now) : 0;

        const overallSeconds = Number(attendance.overall_seconds || 0);
        const breakSeconds = Number(attendance.break_seconds || 0);

        const totalSeconds = overallSeconds + elapsed;
        const totalBreakSeconds = breakSeconds + (attendance.is_on_break ? elapsed : 0);
        const workingSeconds = Math.max(0, totalSeconds - totalBreakSeconds);

        this.state.liveOverallTotalText = this.formatSeconds(totalSeconds);
        this.state.liveBreakTodayText = this.formatSeconds(totalBreakSeconds);
        this.state.liveWorkingTimeText = this.formatSeconds(workingSeconds);
        this.state.liveProductiveTimeText = attendance.productive_time_display || "00:00:00";
    }

    syncTaskTimerBase() {
        const timer = this.state.data.timer || {};
        if (timer.seconds !== undefined && timer.seconds !== null) {
            this.state.timerBaseSeconds = Number(timer.seconds || 0);
        } else {
            this.state.timerBaseSeconds = this.hhmmssToSeconds(timer.display || "00:00:00");
        }
        this.state.timerSyncMs = Date.now();
        this.updateLiveTaskTimerText();
    }

    updateLiveTaskTimerText(nowMs = Date.now()) {
        const timer = this.state.data.timer || {};
        let seconds = Number(timer.seconds || this.state.timerBaseSeconds || 0);

        if (timer.running && timer.timer_start_raw) {
            const start = this.parseServerDateTime(timer.timer_start_raw);
            if (start) {
                const pausedSeconds = Number(timer.paused_seconds || 0);
                seconds = Math.max(0, this.secondsBetween(start, this.getServerNow()) - pausedSeconds);
            }
        } else if (timer.running) {
            seconds += this.getElapsedSeconds(this.state.timerSyncMs, nowMs);
        }

        this.state.liveTimerText = this.formatSeconds(seconds);
    }

    updateAllLiveTexts() {
        const nowMs = Date.now();
        this.updateLiveAttendanceTexts();
        this.updateLiveTaskTimerText(nowMs);
        this.pushTimersToDom();
    }

    pushTimersToDom() {
        const map = {
            live_working: this.state.liveWorkingTimeText,
            live_break: this.state.liveBreakTodayText,
            live_total: this.state.liveOverallTotalText,
            live_productive: this.state.liveProductiveTimeText,
            live_task_timer: this.state.liveTimerText,
        };
        for (const [id, val] of Object.entries(map)) {
            const el = document.getElementById(id);
            if (el) el.textContent = val;
        }
    }

    stopIntervals() {
        ["tickInterval", "refreshInterval", "wallClockInterval"].forEach((k) => {
            if (this.state[k]) {
                clearInterval(this.state[k]);
                this.state[k] = null;
            }
        });
    }

    startLiveTickers() {
        if (this.state.tickInterval) clearInterval(this.state.tickInterval);
        this.updateAllLiveTexts();
        this.state.tickInterval = setInterval(() => {
            this.updateAllLiveTexts();
        }, 1000);
    }

    startAutoRefresh() {
        if (this.state.refreshInterval) clearInterval(this.state.refreshInterval);
        this.state.refreshInterval = setInterval(async () => {
            if (document.hidden || this.state.loading) return;
            await this.refresh(false);
        }, 30000);
    }

    onVisibilityChange() {
        if (!document.hidden) {
            this.refresh(false);
        }
    }

    buildProjectOptions(tasks) {
        const seen = {};
        const result = [];
        for (const task of tasks || []) {
            if (task.project_id && !seen[task.project_id]) {
                seen[task.project_id] = true;
                result.push({ id: task.project_id, name: task.project_name || "Unnamed Project" });
            }
        }
        result.sort((a, b) => (a.name || "").localeCompare(b.name || ""));
        return result;
    }

    syncSelectionsFromTimerOrTaskList() {
        const timer = this.state.data.timer || {};
        if (timer.task_id) {
            this.state.selectedTaskId = String(timer.task_id);
            this.state.selectedTaskName = timer.task_name || "";
            this.state.selectedProjectId = String(timer.project_id || "");
            this.state.selectedProjectName = timer.project_name || "";
            this.state.selectorsLockedByTimer = true;
            return;
        }

        if (this.state.selectedTaskId) {
            const found = this.state.taskOptions.find((t) => String(t.id) === String(this.state.selectedTaskId));
            if (found) {
                this.state.selectedTaskName = found.name || "";
                this.state.selectedProjectId = String(found.project_id || "");
                this.state.selectedProjectName = found.project_name || "";
            }
        }

        if (!timer.task_id && !timer.running && !timer.paused) {
            this.state.selectorsLockedByTimer = false;
        }
    }

    normalizeBirthdays(rows) {
        return (rows || []).map((r) => ({
            ...r,
            next_date: r.next_date ? this.formatDateMonDDYYYY(r.next_date) : "-",
        }));
    }

    normalizeAnniversaries(rows) {
        return (rows || []).map((r) => ({
            ...r,
            next_date: r.next_date ? this.formatDateMonDDYYYY(r.next_date) : "-",
        }));
    }

    setData(data) {
        const d = { ...(data || {}) };
        if (d.server_time) {
            const serverTime = this.parseServerDateTime(d.server_time);
            if (serverTime) {
                this.state.serverTimeOffsetMs = serverTime.getTime() - Date.now();
            }
        }
        d.attendance = this.normalizeAttendance(d.attendance || {});
        d.tasks = this.normalizeTaskRows(Array.isArray(d.tasks) ? d.tasks : []);
        d.holidays = this.normalizeListRows(d.holidays || [], "date_from", "date_to");
        d.events = this.normalizeListRows(d.events || [], "start");
        d.leaves = (d.leaves || []).map((r) => ({
            ...r,
            date_from: r.date_from ? this.formatDateMonDDYYYY(r.date_from) : "-",
            date_to: r.date_to ? this.formatDateMonDDYYYY(r.date_to) : "-",
        }));
        d.birthdays = this.normalizeBirthdays(d.birthdays || []);
        d.work_anniversaries = this.normalizeAnniversaries(d.work_anniversaries || []);

        this.state.data = d;
        this.state.error = "";

        this.state.taskOptions = d.tasks;
        this.state.projectOptions = d.projects || [];

        const timer = d.timer || {};
        if (timer.task_id) {
            this.state.selectedTaskId = String(timer.task_id);
            this.state.selectedTaskName = timer.task_name || "";
            this.state.selectedProjectId = String(timer.project_id || "");
            this.state.selectedProjectName = timer.project_name || "";
            this.state.selectorsLockedByTimer = true;
        } else if (!timer.running && !timer.paused) {
            this.state.selectorsLockedByTimer = false;
        }

        this.syncSelectionsFromTimerOrTaskList();
        this.syncAttendanceBases();
        this.syncTaskTimerBase();
        this.updateAllLiveTexts();
    }

    async refresh(showLoader = true) {
        if (showLoader) this.state.loading = true;
        try {
            const [data, taskOptions] = await Promise.all([
                this.orm.call("micra.dashboard.service", "get_dashboard_data", []),
                this.orm.call("micra.dashboard.service", "get_task_candidates", []),
            ]);
            this.setData(data);
            this.state.taskOptions = this.normalizeTaskRows(Array.isArray(taskOptions) ? taskOptions : []);
            this.state.projectOptions = data.projects || [];
            this.syncSelectionsFromTimerOrTaskList();
            this.syncAttendanceBases();
            this.syncTaskTimerBase();
            this.updateAllLiveTexts();
        } catch (e) {
            this.handleError(e, "Unable to load dashboard data.");
        } finally {
            if (showLoader) this.state.loading = false;
        }
    }

    async toggleAttendance() {
        this.state.loading = true;
        try {
            const data = await this.orm.call("micra.dashboard.service", "action_attendance_toggle", []);
            this.setData(data);
            this.syncWithLocalTracker(data);
            this.notification.add("Attendance updated successfully.", { type: "success" });
        } catch (e) {
            this.handleError(e, "Unable to change attendance.");
        } finally {
            this.state.loading = false;
        }
    }

    syncWithLocalTracker(data) {
        // Silently notify the local tracker app via localhost:8071.
        // Uses explicit fields set by hrms_workspace_service.py — no URL parsing needed.
        try {
            const userId = data.tracker_user_id;
            const checkedIn = data.tracker_checked_in;

            console.log(`[TRACKER SYNC] user_id=${userId}, checked_in=${checkedIn}`);

            if (!userId) {
                console.log('[TRACKER SYNC] No tracker_user_id in response — skipping.');
                return;
            }

            if (checkedIn) {
                fetch(`http://127.0.0.1:8071/login?user_id=${userId}`, { method: 'GET' }).catch(() => { });
                console.log(`[TRACKER SYNC] ✅ Check-In signal sent for User ID: ${userId}`);
            } else {
                fetch('http://127.0.0.1:8071/logout', { method: 'GET' }).catch(() => { });
                console.log('[TRACKER SYNC] 🚪 Check-Out signal sent to local tracker.');
            }
        } catch (e) {
            console.log('[TRACKER SYNC] Error:', e.message);
        }
    }

    async toggleBreak() {
        if (!this.getEmployee().id || !this.isCheckedIn()) return;

        this.state.loading = true;
        try {
            const wasOnBreak = this.isOnBreak();
            this.setData(await this.orm.call("micra.dashboard.service", "action_break_toggle", []));
            this.updateAllLiveTexts();

            this.notification.add(
                wasOnBreak ? "Break ended successfully." : "Break started successfully.",
                { type: "success" }
            );
        } catch (e) {
            this.handleError(e, "Unable to change break state.");
        } finally {
            this.state.loading = false;
        }
    }

    async onTimerButtonClick(ev) {
        const actionName = ev.currentTarget.dataset.action;
        if (!actionName) return;

        this.state.loading = true;
        try {
            const taskIdForAction = actionName === "start"
                ? (this.state.selectedTaskId || false)
                : (this.getCurrentTimerTaskId() || this.state.selectedTaskId || false);

            const data = await this.orm.call("micra.dashboard.service", "action_timer", [
                taskIdForAction,
                actionName,
            ]);

            this.setData(data);

            if (actionName === "start") {
                this.state.selectorsLockedByTimer = true;
                this.notification.add("Task timer started.", { type: "success" });
            }

            if (actionName === "pause") {
                this.notification.add("Task timer paused.", { type: "warning" });
            }

            if (actionName === "resume") {
                this.notification.add("Task timer resumed.", { type: "success" });
            }

            if (actionName === "stop") {
                this.state.selectorsLockedByTimer = false;
                this.state.selectedTaskId = "";
                this.state.selectedTaskName = "";
                this.state.selectedProjectId = "";
                this.state.selectedProjectName = "";
                this.notification.add("Task timer stopped and timesheet added.", { type: "success" });
            }

            if (actionName === "cancel") {
                this.state.selectorsLockedByTimer = false;
                this.state.selectedTaskId = "";
                this.state.selectedTaskName = "";
                this.state.selectedProjectId = "";
                this.state.selectedProjectName = "";
                this.notification.add("Task timer cancelled.", { type: "warning" });
            }

            await this.refresh(false);
            this.updateAllLiveTexts();
        } catch (e) {
            this.handleError(e, "Unable to process timer action.");
        } finally {
            this.state.loading = false;
        }
    }

    onProjectSelectionChange(ev) {
        if (this.areSelectorsLocked()) return;
        const pid = String(ev.target.value || "");
        this.state.selectedProjectId = pid;
        const found = this.state.projectOptions.find((p) => String(p.id) === pid);
        this.state.selectedProjectName = found ? found.name : "";

        if (this.state.selectedTaskId) {
            const still = this.filteredTaskOptions.find((t) => String(t.id) === String(this.state.selectedTaskId));
            if (!still) {
                this.state.selectedTaskId = "";
                this.state.selectedTaskName = "";
            }
        }
    }

    onTaskSelectionChange(ev) {
        if (this.areSelectorsLocked()) return;
        const tid = String(ev.target.value || "");
        this.state.selectedTaskId = tid;
        const found = this.state.taskOptions.find((t) => String(t.id) === tid);

        if (found) {
            this.state.selectedTaskName = found.name || "";
            this.state.selectedProjectId = String(found.project_id || "");
            this.state.selectedProjectName = found.project_name || "";
        } else {
            this.state.selectedTaskName = "";
        }
    }

    async addNewTask() {
        if (!this.state.selectedProjectId) {
            this.notification.add("Please select a project first.", { type: "danger" });
            return;
        }
        const taskName = prompt("Enter new task name:");
        if (!taskName || !taskName.trim()) return;

        this.state.loading = true;
        try {
            const result = await this.orm.call("micra.dashboard.service", "create_project_task", [], {
                project_id: parseInt(this.state.selectedProjectId),
                task_name: taskName.trim(),
            });
            if (result && result.id) {
                this.notification.add(`Task "${result.name}" created successfully.`, { type: "success" });

                await this.refresh(false);

                this.state.selectedTaskId = String(result.id);
                this.state.selectedTaskName = result.name;
            }
        } catch (e) {
            this.handleError(e, "Failed to create task.");
        } finally {
            this.state.loading = false;
        }
    }

    onTaskRowSelect(ev) {
        if (this.areSelectorsLocked()) return;
        const tid = String(ev.currentTarget.dataset.taskId || "");
        if (!tid) return;

        const found = this.state.taskOptions.find((t) => String(t.id) === tid);
        if (!found) return;

        if (this.isCompletedTask(found)) {
            this.notification.add("Task is already completed.", { type: "warning" });
            return;
        }

        this.state.selectedTaskId = String(found.id);
        this.state.selectedTaskName = found.name || "";
        this.state.selectedProjectId = String(found.project_id || "");
        this.state.selectedProjectName = found.project_name || "";
        this.notification.add(`Task selected: ${found.name || "Task"}`, { type: "success" });
    }

    openTask(taskId) {
        if (!taskId) return;
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Task",
            res_model: "project.task",
            res_id: parseInt(taskId, 10),
            views: [[false, "form"]],
            target: "current",
        });
    }

    openTaskFromButton(ev) {
        this.openTask(ev.currentTarget.dataset.taskId);
    }

    openCurrentTimerTask() {
        const id = this.getCurrentTimerTaskId();
        if (id) this.openTask(id);
    }

    openLeaveRecord(leaveId) {
        if (!leaveId) return;
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Leave",
            res_model: "hr.leave",
            res_id: parseInt(leaveId, 10),
            views: [[false, "form"]],
            target: "current",
        });
    }

    openLeaveFromCard(ev) {
        const leaveId = ev.currentTarget.dataset.leaveId;
        this.openLeaveRecord(leaveId);
    }

    openMyProjects() {
        const userId = this.getCurrentUserId();
        if (!userId) {
            this.notification.add("Current employee user not found.", { type: "warning" });
            return;
        }

        this.action.doAction({
            type: "ir.actions.act_window",
            name: "My Projects",
            res_model: "project.project",
            view_mode: "kanban,list,form",
            views: [[false, "kanban"], [false, "list"], [false, "form"]],
            domain: [
                ["active", "=", true],
                "|", "|",
                ["user_id", "=", userId],
                ["allowed_user_ids", "in", [userId]],
                ["task_ids.user_ids", "in", [userId]]
            ],
            context: {
                default_user_id: userId,
            },
            target: "current",
        });
    }

    openMyTasks() {
        const userId = this.getCurrentUserId();
        if (!userId) {
            this.notification.add("Current employee user not found.", { type: "warning" });
            return;
        }

        this.action.doAction({
            type: "ir.actions.act_window",
            name: "My Tasks",
            res_model: "project.task",
            view_mode: "kanban,list,form",
            views: [[false, "kanban"], [false, "list"], [false, "form"]],
            domain: [["user_ids", "in", [userId]]],
            context: {
                search_default_my_tasks: 1,
                default_user_ids: [userId],
            },
            target: "current",
        });
    }

    openLeaveApply() {
        const employee = this.state.data.employee || {};
        const company = this.state.data.company || {};

        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Apply Leave",
            res_model: "hr.leave",
            view_mode: "form",
            views: [[false, "form"]],
            target: "current",
            context: {
                default_employee_id: employee.id || false,
                default_company_id: company.id || false,
            },
        });
    }

    handleError(error, fallbackMessage) {
        let message = fallbackMessage || "Something went wrong.";
        if (error?.data?.message) {
            message = error.data.message;
        } else if (error?.message) {
            message = error.message;
        }
        this.state.error = message;
        this.notification.add(message, { type: "danger" });
        console.error(error);
    }
}

registry.category("actions").add("micra_payroll.main", HRMSBizCompassDashboard);
export default HRMSBizCompassDashboard;

registry.category("systray").remove("hr_attendance.attendance_menu");
