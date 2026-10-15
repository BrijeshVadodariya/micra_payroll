/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onWillStart, onWillDestroy, useRef, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { loadJS } from "@web/core/assets";

export class FaceCaptureAction extends Component {
    static template = "micra_payroll.FaceCaptureAction";
    
    setup() {
        this.action = useService("action");
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.videoRef = useRef("video");
        this.state = useState({ processing: false });
        
        onWillStart(async () => {
            // Load face-api from CDN as a plain global script
            if (!window.faceapi) {
                await loadJS("https://cdn.jsdelivr.net/npm/face-api.js@0.22.2/dist/face-api.min.js");
            }
            const MODEL_URL = '/micra_payroll/static/face-api-model';
            await Promise.all([
                window.faceapi.nets.tinyFaceDetector.loadFromUri(MODEL_URL),
                window.faceapi.nets.faceLandmark68TinyNet.loadFromUri(MODEL_URL),
                window.faceapi.nets.faceRecognitionNet.loadFromUri(MODEL_URL)
            ]);
            this.startCamera();
        });

        onWillDestroy(() => {
            if (this.stream) {
                this.stream.getTracks().forEach(track => track.stop());
            }
        });
    }

    async startCamera() {
        try {
            this.stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user' } });
            if (this.videoRef.el) {
                this.videoRef.el.srcObject = this.stream;
            }
        } catch (e) {
            this.notification.add("Camera error: " + e.message, { type: "danger" });
        }
    }

    async captureFace() {
        if (!this.videoRef.el || this.state.processing) return;
        this.state.processing = true;

        const detection = await window.faceapi.detectSingleFace(this.videoRef.el, new window.faceapi.TinyFaceDetectorOptions())
                                       .withFaceLandmarks(true)
                                       .withFaceDescriptor();
        if (!detection) {
            this.notification.add("No face detected. Please try again.", { type: "danger" });
            this.state.processing = false;
            return;
        }

        const descriptorArray = Array.from(detection.descriptor);
        
        // Capture image snapshot from the video element
        const snap = document.createElement('canvas');
        snap.width = this.videoRef.el.videoWidth || 640;
        snap.height = this.videoRef.el.videoHeight || 480;
        const sCtx = snap.getContext('2d', { willReadFrequently: true });
        sCtx.save();
        sCtx.scale(-1, 1);
        sCtx.drawImage(this.videoRef.el, -snap.width, 0, snap.width, snap.height);
        sCtx.restore();
        const imageData = snap.toDataURL('image/jpeg', 0.85);
        const base64Image = imageData.split(',')[1];

        try {
            await this.orm.write("hr.employee", [this.props.action.params.employee_id], {
                face_descriptor: JSON.stringify(descriptorArray),
                registered_face_image: base64Image
            });
            this.notification.add("Face registered successfully!", { type: "success" });
            this.action.doAction({ type: "ir.actions.act_window_close" });
            this.action.doAction({ type: 'ir.actions.client', tag: 'soft_reload' }); // Soft reload the form instantly
        } catch (e) {
            this.notification.add("Failed to save descriptor and image.", { type: "danger" });
            this.state.processing = false;
        }
    }

    close() {
        this.action.doAction({ type: "ir.actions.act_window_close" });
    }
}

registry.category("actions").add("micra_payroll.face_capture_client_action", FaceCaptureAction);
