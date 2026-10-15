/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import publicKioskApp from "@hr_attendance/public_kiosk/public_kiosk_app";
import { FaceLoginScanner } from "./face_login_scanner";

const { kioskAttendanceApp } = publicKioskApp;

kioskAttendanceApp.components = {
    ...kioskAttendanceApp.components,
    FaceLoginScanner,
};

patch(kioskAttendanceApp.prototype, {
    setup() {
        super.setup();
        this.isFaceKioskOnly = window.location.pathname.includes('/face_kiosk/');
        if (this.isFaceKioskOnly) {
            this.state.active_display = 'face_login';
            document.body.classList.add('o_face_kiosk_only');
            
            // Dynamic premium fonts injection to avoid CSS bundle @import warning
            if (!document.getElementById('kiosk-premium-fonts')) {
                const fontLink = document.createElement('link');
                fontLink.id = 'kiosk-premium-fonts';
                fontLink.rel = 'stylesheet';
                fontLink.href = 'https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&family=Orbitron:wght@500;700;900&display=swap';
                document.head.appendChild(fontLink);
            }
        }
    },

    switchDisplay(screen) {
        if (screen === 'face_login') {
            this.state.active_display = 'face_login';
        } else {
            super.switchDisplay(screen);
        }
    },

    async setSetting(mode) {
        if (mode === 'face_login') {
            await this.env.services.rpc("/hr_attendance/set_settings", {
                token: this.props.token,
                mode: mode,
            });
            this.props.kioskMode = mode;
            this.manualKioskMode = false;
            this.state.active_display = "main";
        } else {
            return super.setSetting(mode);
        }
    },

    kioskReturn() {
        if (this.isFaceKioskOnly) {
            this.switchDisplay('face_login');
        } else if (this.state.active_display === 'face_login') {
            this.switchDisplay('main');
        } else {
            super.kioskReturn();
        }
    }
});
