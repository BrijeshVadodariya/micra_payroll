/** @odoo-module **/

import { Component, useState, onWillStart, onWillDestroy, useRef, onMounted } from "@odoo/owl";
import { rpc } from "@web/core/network/rpc";
import { loadJS } from "@web/core/assets";

async function sha256(message) {
    const msgBuffer = new TextEncoder().encode(message);
    const hashBuffer = await crypto.subtle.digest('SHA-256', msgBuffer);
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
}

export class FaceLoginScanner extends Component {
    static template = "micra_payroll.FaceLoginScanner";

    setup() {
        this.state = useState({
            status: "Initializing...",
            facesLoaded: 0,
            processing: false,
            matchedEmployee: null,
            showActionButtons: false,
            successPopup: null,
            holidayPopup: null,
            showPasswordPrompt: false,
            passwordInput: "",
        });
        this.videoRef = useRef("video");
        this.overlayCanvasRef = useRef("overlayCanvas");
        this.registeredFaces = [];
        this.faceMatcher = null;
        this._detecting = false;
        this._detectionTimer = null;
        this.errorTimeout = null;
        this.noFaceFrames = 0;
        this.lastMatchTime = 0;
        this.isMobile = /Mobi|Android|iPhone|iPad/i.test(navigator.userAgent);
        this.detectionInputSize = this.isMobile ? 160 : 320;
        this._syncInterval = null;
        this._syncing = false;

        // Retrieve Kiosk Password from localStorage
        this.kioskPassword = localStorage.getItem('micra_kiosk_password') || "";

        onWillStart(async () => {
            const MODEL_URL = '/micra_payroll/static/face-api-model';

            // Step 1: Load face-api CDN library (only on first load, cached after)
            this.state.status = "Loading AI library...";
            if (!window.faceapi) {
                await loadJS("https://cdn.jsdelivr.net/npm/face-api.js@0.22.2/dist/face-api.min.js");
            }
            const faceapi = window.faceapi;

            // Step 2: Load AI models AND fetch employee descriptors IN PARALLEL
            // This cuts load time in half vs doing them sequentially
            this.state.status = "Loading AI models & employee data...";
            let faces;
            try {
                const modelsToLoad = [];
                if (!faceapi.nets.tinyFaceDetector.isLoaded)
                    modelsToLoad.push(faceapi.nets.tinyFaceDetector.loadFromUri(MODEL_URL));
                if (!faceapi.nets.faceLandmark68TinyNet.isLoaded)
                    modelsToLoad.push(faceapi.nets.faceLandmark68TinyNet.loadFromUri(MODEL_URL));
                if (!faceapi.nets.faceRecognitionNet.isLoaded)
                    modelsToLoad.push(faceapi.nets.faceRecognitionNet.loadFromUri(MODEL_URL));

                [, faces] = await Promise.all([
                    Promise.all(modelsToLoad),
                    rpc("/hr_attendance/get_face_descriptors", { token: this.props.token, password: this.kioskPassword }),
                ]);
            } catch (e) {
                this.state.status = "Failed to load. Check your connection and refresh.";
                return;
            }

            // Step 3: Process the descriptor response
            if (faces && faces.error) {
                if (faces.error === 'ip_not_allowed') {
                    this.state.status = `Access Denied: Your IP address (${faces.client_ip}) is not allowed. Please connect to the designated Wi-Fi.`;
                } else if (faces.error === 'invalid_password') {
                    this.state.status = "Authorization Required";
                    this.state.showPasswordPrompt = true;
                } else {
                    this.state.status = "Face Recognition is disabled by your company.";
                }
                this.state.facesLoaded = -1;
                return;
            }

            if (!faces || !Array.isArray(faces)) {
                this.state.status = "Failed to load employee faces.";
                return;
            }

            this.registeredFaces = faces.map(f => ({
                id: f.id,
                name: f.name,
                company_name: f.company_name || this.props.company_name || '',
                descriptor: new Float32Array(f.descriptor),
                attendance_state: f.attendance_state
            }));

            if (this.registeredFaces.length > 0) {
                this.faceMatcher = new window.faceapi.FaceMatcher(
                    this.registeredFaces.map(f => new window.faceapi.LabeledFaceDescriptors(f.id.toString(), [f.descriptor])),
                    0.45
                );
            }
            this.state.facesLoaded = this.registeredFaces.length > 0 ? this.registeredFaces.length : 1; // Fake 1 so it passes the >0 check to show camera
            this.state.status = "Starting camera...";
            // Camera will actually start in onMounted
        });

        onWillDestroy(() => {
            this.stopDetection();
            if (this._syncInterval) {
                clearInterval(this._syncInterval);
                this._syncInterval = null;
            }
            if (this.stream) {
                this.stream.getTracks().forEach(track => track.stop());
            }
            if (this.errorTimeout) {
                clearTimeout(this.errorTimeout);
            }
        });

        onMounted(() => {
            if (this.state.status === "Starting camera..." && !this.state.showPasswordPrompt) {
                this.startCamera();
            }
            // Start background sync loop to keep attendance states and employee list updated in real-time
            if (!this._syncInterval) {
                this._syncInterval = setInterval(() => {
                    this.syncAllAttendanceStates();
                }, 10000);
            }
        });
    }

    onPasswordKeyup(ev) {
        if (ev.key === 'Enter') {
            this.submitPassword();
        }
    }

    async submitPassword() {
        if (!this.state.passwordInput) return;

        this.state.status = "Verifying password...";
        this.state.showPasswordPrompt = false;

        try {
            const passwordHash = await sha256(this.state.passwordInput);
            const faces = await rpc("/hr_attendance/get_face_descriptors", { token: this.props.token, password: passwordHash });

            if (faces && faces.error) {
                if (faces.error === 'invalid_password') {
                    this.state.status = "Incorrect Password. Please try again.";
                    this.state.showPasswordPrompt = true;
                } else if (faces.error === 'ip_not_allowed') {
                    this.state.status = `Access Denied: Your IP address (${faces.client_ip}) is not allowed. Please connect to the designated Wi-Fi.`;
                } else {
                    this.state.status = "Face Recognition is disabled by your company.";
                }
                return;
            }

            // Success! Store the HASH, not the plain text
            localStorage.setItem('micra_kiosk_password', passwordHash);
            this.kioskPassword = passwordHash;

            this.registeredFaces = faces.map(f => ({
                id: f.id,
                name: f.name,
                company_name: f.company_name || this.props.company_name || '',
                descriptor: new Float32Array(f.descriptor),
                attendance_state: f.attendance_state
            }));

            if (this.registeredFaces.length > 0) {
                this.faceMatcher = new window.faceapi.FaceMatcher(
                    this.registeredFaces.map(f => new window.faceapi.LabeledFaceDescriptors(f.id.toString(), [f.descriptor])),
                    0.45
                );
            }
            this.state.facesLoaded = this.registeredFaces.length > 0 ? this.registeredFaces.length : 1;
            this.startCamera();

            if (!this._syncInterval) {
                this._syncInterval = setInterval(() => {
                    this.syncAllAttendanceStates();
                }, 10000);
            }

        } catch (e) {
            this.state.status = "Network error. Please try again.";
            this.state.showPasswordPrompt = true;
        }
    }

    showError(msg) {
        this.state.errorMsg = msg;
        if (this.errorTimeout) {
            clearTimeout(this.errorTimeout);
        }
        this.errorTimeout = setTimeout(() => {
            this.state.errorMsg = null;
        }, 3000);
    }

    async startCamera() {
        try {
            const videoConstraints = this.isMobile
                ? {
                    facingMode: 'user',
                    width: { ideal: 480, max: 640 },
                    height: { ideal: 480, max: 640 },
                }
                : {
                    facingMode: 'user',
                    width: { ideal: 640 },
                    height: { ideal: 480 },
                };

            this.stream = await navigator.mediaDevices.getUserMedia({
                video: videoConstraints
            });
            if (this.videoRef.el) {
                this.videoRef.el.srcObject = this.stream;
                // Wait for video to actually start playing before warm-up
                await new Promise(resolve => {
                    this.videoRef.el.onloadeddata = resolve;
                });

                this.state.status = "Scanning for faces...";
                this.startDetection();
            }
        } catch (e) {
            this.state.status = "Camera access denied or error: " + e.message;
        }
    }

    startDetection() {
        this._detecting = true;
        this._scheduleNextDetection();
    }

    _scheduleNextDetection() {
        if (!this._detecting) return;
        // Throttle detection loop: 120ms on mobile (~7 FPS), 60ms on desktop (~15 FPS)
        const delay = this.isMobile ? 120 : 60;
        this._detectionTimer = setTimeout(async () => {
            if (!this._detecting) return;
            try {
                await this.detectFaces();
            } catch (err) {
                console.error("Face detection loop error:", err);
            } finally {
                this._scheduleNextDetection();
            }
        }, delay);
    }

    stopDetection() {
        this._detecting = false;
        if (this._detectionTimer) {
            clearTimeout(this._detectionTimer);
            this._detectionTimer = null;
        }
    }

    async detectFaces() {
        if (!this.videoRef.el || this.state.processing) return;

        // Use scoreThreshold 0.5 to prevent false positives on background objects/lighting
        const options = new window.faceapi.TinyFaceDetectorOptions({
            inputSize: this.detectionInputSize,
            scoreThreshold: 0.5
        });

        let singleResult = null;
        try {
            singleResult = await window.faceapi.detectSingleFace(this.videoRef.el, options)
                .withFaceLandmarks(true)
                .withFaceDescriptor();
        } catch (e) {
            singleResult = null;
        }

        const detections = singleResult ? [singleResult] : [];

        if (this.overlayCanvasRef.el && this.videoRef.el) {
            const displaySize = { width: this.videoRef.el.videoWidth, height: this.videoRef.el.videoHeight };
            if (displaySize.width > 0 && displaySize.height > 0) {
                if (this.overlayCanvasRef.el.width !== displaySize.width || this.overlayCanvasRef.el.height !== displaySize.height) {
                    window.faceapi.matchDimensions(this.overlayCanvasRef.el, displaySize);
                }
                const resizedDetections = window.faceapi.resizeResults(detections, displaySize);
                const ctx = this.overlayCanvasRef.el.getContext('2d', { willReadFrequently: true });

                if (resizedDetections.length > 0) {
                    this._lastDrawnDetections = resizedDetections;
                    this._emptyCanvasFrames = 0;
                } else {
                    this._emptyCanvasFrames = (this._emptyCanvasFrames || 0) + 1;
                }

                // If no face detected for more than 2 frames, clear overlay immediately
                const detectionsToRender = resizedDetections.length > 0
                    ? resizedDetections
                    : (this._emptyCanvasFrames < 2 ? (this._lastDrawnDetections || []) : []);

                ctx.clearRect(0, 0, this.overlayCanvasRef.el.width, this.overlayCanvasRef.el.height);

                if (detectionsToRender.length > 0) {
                    detectionsToRender.forEach(fd => {
                        let text = "Unknown";
                        let boxColor = '#e93d5b'; // Red for unknown

                        if (fd.descriptor && this.faceMatcher) {
                            const match = this.faceMatcher.findBestMatch(fd.descriptor);
                            if (match.label !== 'unknown') {
                                const employee = this.registeredFaces.find(f => f.id === parseInt(match.label));
                                text = employee ? employee.name : match.label;
                                boxColor = '#22c55e'; // Green for known
                            }
                        }

                        const box = fd.detection ? fd.detection.box : (fd.box || fd);
                        if (box && typeof box.x === 'number') {
                            const mirroredBox = {
                                x: this.overlayCanvasRef.el.width - (box.x + box.width),
                                y: box.y,
                                width: box.width,
                                height: box.height
                            };

                            const drawBox = new window.faceapi.draw.DrawBox(mirroredBox, {
                                label: text,
                                boxColor: boxColor,
                                drawLabelOptions: { fontColor: '#ffffff', fontSize: 18, padding: 6 },
                                lineWidth: 2
                            });
                            drawBox.draw(this.overlayCanvasRef.el);
                        }
                    });
                }
            }
        }

        // When no face is detected in the camera frame
        if (detections.length === 0) {
            if (this.state.showActionButtons) {
                this.noFaceFrames = (this.noFaceFrames || 0) + 1;
                // If no face is detected for 5 consecutive frames (~800ms) or 1.2s since last seen, reset promptly
                if (this.noFaceFrames >= 5 || (this.lastMatchTime && Date.now() - this.lastMatchTime > 1200)) {
                    this.resumeScanning();
                }
            }
            return;
        }

        // A face is detected
        if (singleResult && singleResult.descriptor) {
            let employeeId = null;
            if (this.faceMatcher) {
                const match = this.faceMatcher.findBestMatch(singleResult.descriptor);
                if (match.label !== 'unknown') {
                    employeeId = parseInt(match.label);
                }
            }

            if (employeeId !== null) {
                this.noFaceFrames = 0;
                this.lastMatchTime = Date.now();

                if (!this.state.showActionButtons || !this.state.matchedEmployee || employeeId !== this.state.matchedEmployee.id) {
                    const employee = this.registeredFaces.find(f => f.id === employeeId);
                    if (employee) this.handleMatch(employee);
                }
            } else {
                // Face detected, but not recognized
                if (this.state.showActionButtons) {
                    this.noFaceFrames = (this.noFaceFrames || 0) + 1;
                    if (this.noFaceFrames >= 5 || (this.lastMatchTime && Date.now() - this.lastMatchTime > 1200)) {
                        this.resumeScanning();
                    }
                }
            }
        }
    }

    handleMatch(employee) {
        this.noFaceFrames = 0;
        this.state.matchedEmployee = employee;
        this.state.showActionButtons = true;
        this.state.status = "Action Required";
        this.state.errorMsg = null;
        if (this.errorTimeout) {
            clearTimeout(this.errorTimeout);
            this.errorTimeout = null;
        }
        // Fetch real-time live attendance state for this employee from server immediately
        this.syncLiveEmployeeState(employee.id);
    }

    async syncLiveEmployeeState(employeeId) {
        try {
            const res = await rpc("/hr_attendance/get_attendance_states", {
                token: this.props.token,
                employee_id: employeeId,
                password: this.kioskPassword
            });
            if (res && res.attendance_state) {
                const targetState = res.attendance_state;
                const emp = this.registeredFaces.find(f => f.id === employeeId);
                if (emp) {
                    emp.attendance_state = targetState;
                }
                if (this.state.matchedEmployee && this.state.matchedEmployee.id === employeeId) {
                    this.state.matchedEmployee.attendance_state = targetState;
                }
            }
        } catch (e) {
            // Silently fallback to cached state
        }
    }

    async syncAllAttendanceStates() {
        if (this.state.processing || this._syncing) return;
        this._syncing = true;
        try {
            const res = await rpc("/hr_attendance/get_attendance_states", {
                token: this.props.token,
                password: this.kioskPassword
            });
            if (res && res.states) {
                for (const emp of this.registeredFaces) {
                    if (res.states[emp.id] !== undefined) {
                        emp.attendance_state = res.states[emp.id];
                    }
                }
                if (this.state.matchedEmployee && res.states[this.state.matchedEmployee.id] !== undefined) {
                    this.state.matchedEmployee.attendance_state = res.states[this.state.matchedEmployee.id];
                }
                // If new face was registered in HR or deleted, reload descriptors silently
                if (res.count !== undefined && res.count !== this.registeredFaces.length) {
                    await this.reloadDescriptors();
                }
            }
        } catch (e) {
            // Ignore background sync errors
        } finally {
            this._syncing = false;
        }
    }

    async reloadDescriptors() {
        try {
            const faces = await rpc("/hr_attendance/get_face_descriptors", {
                token: this.props.token,
                password: this.kioskPassword
            });
            if (faces && Array.isArray(faces)) {
                this.registeredFaces = faces.map(f => ({
                    id: f.id,
                    name: f.name,
                    company_name: f.company_name || this.props.company_name || '',
                    descriptor: new Float32Array(f.descriptor),
                    attendance_state: f.attendance_state
                }));
                if (this.registeredFaces.length > 0) {
                    this.faceMatcher = new window.faceapi.FaceMatcher(
                        this.registeredFaces.map(f => new window.faceapi.LabeledFaceDescriptors(f.id.toString(), [f.descriptor])),
                        0.45
                    );
                }
                this.state.facesLoaded = this.registeredFaces.length;
            }
        } catch (e) {
            // Ignore
        }
    }

    onCheckInClick(ev) {
        if (ev) {
            ev.preventDefault();
            ev.stopPropagation();
        }
        if (this.state.processing) return;
        this.confirmAction('check_in');
    }

    onCheckOutClick(ev) {
        if (ev) {
            ev.preventDefault();
            ev.stopPropagation();
        }
        if (this.state.processing) return;
        this.confirmAction('check_out');
    }

    async confirmAction(actionType) {
        if (this.state.processing) return;
        if (!this.state.matchedEmployee) return;

        const currentEmployee = this.state.matchedEmployee;
        this.state.showActionButtons = false;
        this.state.processing = true;
        this.state.status = `Processing ${actionType.replace('_', ' ')}...`;

        // Capture a lightweight, downscaled snapshot for audit (~15-20KB instead of 500KB)
        let imageBase64 = false;
        if (this.videoRef.el && this.videoRef.el.videoWidth > 0) {
            const vWidth = this.videoRef.el.videoWidth;
            const vHeight = this.videoRef.el.videoHeight;
            const scale = Math.min(1, 360 / Math.max(vWidth, vHeight));
            const snap = document.createElement('canvas');
            snap.width = Math.round(vWidth * scale);
            snap.height = Math.round(vHeight * scale);
            const sCtx = snap.getContext('2d');
            sCtx.save();
            sCtx.scale(-1, 1);
            sCtx.drawImage(this.videoRef.el, -snap.width, 0, snap.width, snap.height);
            sCtx.restore();
            imageBase64 = snap.toDataURL('image/jpeg', 0.65);
        }

        try {
            const result = await rpc("/hr_attendance/face_check_in_out", {
                token: this.props.token,
                employee_id: currentEmployee.id,
                action: actionType,
                image: imageBase64,
                password: this.kioskPassword
            });

            if (result && result.error) {
                if (result.error === 'already_checked_in' || result.error === 'not_checked_in') {
                    const targetState = result.error === 'already_checked_in' ? 'checked_in' : 'checked_out';
                    const emp = this.registeredFaces.find(f => f.id === currentEmployee.id);
                    if (emp) {
                        emp.attendance_state = targetState;
                    }
                    currentEmployee.attendance_state = targetState;
                    this.state.matchedEmployee = currentEmployee;
                    this.state.showActionButtons = true;
                    this.state.processing = false;
                    this.state.status = "Action Required";
                    const tip = targetState === 'checked_in'
                        ? 'Already checked in. Please click Check Out.'
                        : 'Not checked in yet. Please click Check In.';
                    this.showError(`${currentEmployee.name}: ${tip}`);
                    return;
                }
                if (result.error === 'validation_error' && result.message) {
                    // Holiday / leave / weekend — show dedicated popup
                    this.state.holidayPopup = {
                        name: currentEmployee.name,
                        message: result.message,
                    };
                    setTimeout(() => {
                        this.state.holidayPopup = null;
                        this.resumeScanning();
                    }, 4000);
                } else {
                    const actionText = actionType === 'check_in' ? 'Check In' : 'Check Out';
                    this.showError(`Cannot ${actionText}: ${result.error.replace(/_/g, ' ')}`);
                    this.resumeScanning();
                }
            } else if (result && (result.employee_name || result.attendance_state)) {
                // Update local state to reflect the new attendance status
                const newState = result.attendance_state || (actionType === 'check_in' ? 'checked_in' : 'checked_out');
                const emp = this.registeredFaces.find(f => f.id === currentEmployee.id);
                if (emp) {
                    emp.attendance_state = newState;
                }
                currentEmployee.attendance_state = newState;

                const actionText = actionType === 'check_in' ? 'Checked in' : 'Checked out';
                const now = new Date();
                const timeStr = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
                const dateStr = now.toLocaleDateString([], { day: 'numeric', month: 'short' });

                this.state.successPopup = {
                    name: result.employee_name,
                    company_name: currentEmployee.company_name || '',
                    action: actionText,
                    time: `${dateStr}, ${timeStr}`
                };

                // Remove popup and resume after 2.5 seconds
                setTimeout(() => {
                    this.state.successPopup = null;
                    this.resumeScanning();
                }, 2500);
            } else {
                this.showError("Failed to record attendance.");
                this.resumeScanning();
            }
        } catch (e) {
            this.showError("Network error during attendance record.");
            this.resumeScanning();
        }
    }

    resumeScanning() {
        this.noFaceFrames = 0;
        this.lastMatchTime = 0;
        this._lastDrawnDetections = null;
        this._emptyCanvasFrames = 0;
        this.state.processing = false;
        this.state.matchedEmployee = null;
        this.state.showActionButtons = false;
        this.state.status = "Scanning for faces...";
        if (this.overlayCanvasRef.el) {
            const ctx = this.overlayCanvasRef.el.getContext('2d', { willReadFrequently: true });
            ctx.clearRect(0, 0, this.overlayCanvasRef.el.width, this.overlayCanvasRef.el.height);
        }
    }
}
