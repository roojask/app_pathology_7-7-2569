document.addEventListener('DOMContentLoaded', function () {
    const btnMicToggle = document.getElementById('btn-mic-toggle');
    const txtTranscription = document.getElementById('sidebar-transcription-box') || document.getElementById('transcription-text');
    const micStatusContainer = document.getElementById('sidebar-dictation-state') || document.getElementById('mic-status-container');

    let recognition;
    let isRecording = false;

    // --- New System Variables ---
    let isCameraRunning = false;
    let cameraInstance = null;
    let mediaRecorder = null;
    let audioChunks = [];
    let recordingTimerInterval = null;
    let recordingStartTime = 0;

    const btnCameraToggle = document.getElementById('btn-camera-toggle');
    const btnRecordAudio = document.getElementById('btn-record-audio');
    const btnStopAudio = document.getElementById('btn-stop-audio');
    const recordingTimer = document.getElementById('recording-timer');
    const audioUploadForm = document.getElementById('audio-upload-form');
    const fileUploadInput = document.getElementById('file-upload');

    function showError(msg) {
        if (micStatusContainer) {
            micStatusContainer.innerHTML = `<span style="color:red; font-weight:bold;">Error: ${msg}</span>`;
        } else {
            alert(msg);
        }
    }

    // Default to 100% English Dictation (en-US) for Medical Pathology
    let currentMicLang = 'en-US';

    // --- Web Audio Chime Synthesizer for Zero-Latency Audio Feedback ---
    function playAudioChime(type) {
        try {
            const AudioCtx = window.AudioContext || window.webkitAudioContext;
            if (!AudioCtx) return;
            const ctx = new AudioCtx();
            
            if (type === 'start') {
                // Beep Up: 880Hz -> 1046Hz
                const osc = ctx.createOscillator();
                const gain = ctx.createGain();
                osc.type = 'sine';
                osc.frequency.setValueAtTime(880, ctx.currentTime);
                osc.frequency.exponentialRampToValueAtTime(1046, ctx.currentTime + 0.12);
                gain.gain.setValueAtTime(0.15, ctx.currentTime);
                gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.15);
                osc.connect(gain); gain.connect(ctx.destination);
                osc.start(); osc.stop(ctx.currentTime + 0.15);
            } else if (type === 'stop') {
                // Beep Down: 880Hz -> 587Hz
                const osc = ctx.createOscillator();
                const gain = ctx.createGain();
                osc.type = 'sine';
                osc.frequency.setValueAtTime(880, ctx.currentTime);
                osc.frequency.exponentialRampToValueAtTime(587, ctx.currentTime + 0.12);
                gain.gain.setValueAtTime(0.15, ctx.currentTime);
                gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.15);
                osc.connect(gain); gain.connect(ctx.destination);
                osc.start(); osc.stop(ctx.currentTime + 0.15);
            } else if (type === 'success') {
                // Success Chime: 523Hz -> 659Hz -> 784Hz Major Chord
                [523.25, 659.25, 783.99].forEach((freq, idx) => {
                    const osc = ctx.createOscillator();
                    const gain = ctx.createGain();
                    osc.type = 'sine';
                    osc.frequency.value = freq;
                    gain.gain.setValueAtTime(0.1, ctx.currentTime + idx * 0.06);
                    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + idx * 0.06 + 0.25);
                    osc.connect(gain); gain.connect(ctx.destination);
                    osc.start(ctx.currentTime + idx * 0.06);
                    osc.stop(ctx.currentTime + idx * 0.06 + 0.25);
                });
            }
        } catch(e) {
            console.log("Chime playback note:", e);
        }
    }

    function updateHandsFreeBadge(statusText, ringColor='#95a5a6', pulse=false) {
        const badgeText = document.getElementById('mic-status-text');
        const pulseRing = document.getElementById('mic-pulse-ring');
        if (badgeText) badgeText.innerText = statusText;
        if (pulseRing) {
            pulseRing.style.background = ringColor;
            if (pulse) {
                pulseRing.style.boxShadow = `0 0 10px ${ringColor}`;
            } else {
                pulseRing.style.boxShadow = 'none';
            }
        }
    }

    if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        recognition = new SpeechRecognition();
        recognition.continuous = true;
        recognition.interimResults = true;
        recognition.lang = currentMicLang;

        recognition.onstart = function () {
            isRecording = true;
            playAudioChime('start');
            updateHandsFreeBadge('Mic Listening...', '#e74c3c', true);

            btnMicToggle.innerHTML = '<i class="fas fa-stop-circle" style="color:red;"></i> หยุดบันทึก (Stop)';
            btnMicToggle.style.backgroundColor = '#ffcccc';

            const boxMic = document.getElementById('box-mic');
            if (boxMic) {
                boxMic.innerText = "MIC ON (Say Stop)";
                boxMic.style.backgroundColor = "rgba(231, 76, 60, 0.8)";
            }

            if (micStatusContainer) micStatusContainer.innerText = 'กำลังฟัง... (Listening...)';
        };

        recognition.onend = function () {
            if (isRecording) {
                // If it ended but isRecording is still true, it was a silence timeout. Restart!
                try {
                    recognition.start();
                    if (micStatusContainer) {
                        micStatusContainer.innerHTML = '<span style="color:#27ae60; font-weight:bold;"><i class="fas fa-redo"></i> กู้คืนช่องสัญญาณไมค์อัตโนมัติ (Mic Auto-reconnected)...</span>';
                    }
                } catch (e) {
                    console.log("Failed to auto-restart speech recognition:", e);
                }
            } else {
                playAudioChime('stop');
                updateHandsFreeBadge('Hands-Free Ready', '#95a5a6', false);
                btnMicToggle.innerHTML = '<i class="fas fa-microphone"></i> เริ่มบันทึกเสียง (Start)';
                btnMicToggle.style.backgroundColor = '#ddd';

                const boxMic = document.getElementById('box-mic');
                if (boxMic) {
                    boxMic.innerText = "MIC OFF";
                    boxMic.style.backgroundColor = "rgba(0, 0, 0, 0.5)";
                    boxMic.style.border = "1px solid rgba(255, 255, 255, 0.3)";
                }
            }
        };

        recognition.onresult = function (event) {
            let finalTranscript = '';
            let interimTranscript = '';

            for (let i = 0; i < event.results.length; ++i) {
                if (event.results[i].isFinal) {
                    finalTranscript += event.results[i][0].transcript;
                } else {
                    interimTranscript += event.results[i][0].transcript;
                }
            }

            const totalText = finalTranscript + interimTranscript;
            
            // --- Text-to-Speech (TTS) & Hands-Free Feedback ---
            let isVoiceFeedbackEnabled = true;
            const btnHandsfreeToggle = document.getElementById('btn-handsfree-toggle');

            function speakFeedback(text, lang = 'th-TH') {
                if (!isVoiceFeedbackEnabled) return;
                if ('speechSynthesis' in window) {
                    window.speechSynthesis.cancel();
                    const utterance = new SpeechSynthesisUtterance(text);
                    utterance.lang = lang;
                    utterance.rate = 1.05;
                    utterance.pitch = 1.0;
                    window.speechSynthesis.speak(utterance);
                }
            }

            if (btnHandsfreeToggle) {
                btnHandsfreeToggle.addEventListener('click', function () {
                    isVoiceFeedbackEnabled = !isVoiceFeedbackEnabled;
                    if (isVoiceFeedbackEnabled) {
                        btnHandsfreeToggle.style.backgroundColor = '#28a745';
                        btnHandsfreeToggle.style.color = 'white';
                        btnHandsfreeToggle.innerHTML = '<i class="fas fa-volume-up"></i> เสียงตอบรับ (Hands-Free): ON';
                        speakFeedback('เปิดระบบเสียงตอบรับเรียบร้อยแล้ว');
                    } else {
                        btnHandsfreeToggle.style.backgroundColor = '#7f8c8d';
                        btnHandsfreeToggle.style.color = 'white';
                        btnHandsfreeToggle.innerHTML = '<i class="fas fa-volume-mute"></i> เสียงตอบรับ (Hands-Free): OFF';
                    }
                });
            }

            // Check for voice commands
            const checkText = totalText.toLowerCase().trim();

            // 1. Voice Command: Reset / Clear Form
            if (checkText.endsWith("clear all") || checkText.endsWith("reset form") || checkText.endsWith("ล้างข้อมูล") || checkText.endsWith("เริ่มเคสใหม่") || checkText.endsWith("ล้างฟอร์ม")) {
                playAudioChime('stop');
                updateHandsFreeBadge('Form Reset', '#f39c12', true);
                txtTranscription.value = "";
                if (typeof unlockAllFields === 'function') unlockAllFields();
                document.querySelectorAll('.patho-form input[type="text"], .patho-form textarea').forEach(el => {
                    el.value = '';
                });
                document.querySelectorAll('.patho-form input[type="checkbox"], .patho-form input[type="radio"]').forEach(el => {
                    el.checked = false;
                });
                if (micStatusContainer) micStatusContainer.innerText = "ล้างฟอร์มเรียบร้อยแล้ว (Form Cleared)";
                speakFeedback("ล้างข้อมูลเตรียมเคสใหม่เรียบร้อยแล้ว");
                recognition.stop();
                setTimeout(() => {
                    try { recognition.start(); } catch(e) {}
                }, 300);
                return;
            }

            // 2. Voice Command: Camera Toggle (เปิดกล้อง / ปิดกล้อง)
            if (checkText.endsWith("เปิดกล้อง") || checkText.endsWith("open camera")) {
                playAudioChime('success');
                updateHandsFreeBadge('Camera ON', '#27ae60', true);
                speakFeedback("เปิดกล้องเรียบร้อยแล้ว");
                const camBtn = document.getElementById('btn-camera-toggle');
                if (camBtn && !isCameraRunning) camBtn.click();
                return;
            }
            if (checkText.endsWith("ปิดกล้อง") || checkText.endsWith("close camera")) {
                playAudioChime('stop');
                updateHandsFreeBadge('Camera OFF', '#7f8c8d', false);
                speakFeedback("ปิดกล้องเรียบร้อยแล้ว");
                const camBtn = document.getElementById('btn-camera-toggle');
                if (camBtn && isCameraRunning) camBtn.click();
                return;
            }

            // 3. Voice Command: Local Extract (สกัดคำ / ดึงข้อมูล)
            if (checkText.endsWith("สกัดคำ") || checkText.endsWith("ดึงข้อมูล") || checkText.endsWith("extract data") || checkText.endsWith("สกัดข้อมูล")) {
                playAudioChime('success');
                updateHandsFreeBadge('AI Extracted!', '#2ecc71', true);
                speakFeedback("สกัดข้อมูลลงแบบฟอร์มสำเร็จ");
                if (micStatusContainer) micStatusContainer.innerText = "กำลังสกัดข้อมูลลงแบบฟอร์ม...";
                const localExtractBtn = document.getElementById('btn-local-extract');
                if (localExtractBtn) localExtractBtn.click();
                return;
            }

            // 4. Voice Command: Generate PDF / Save Report
            if (checkText.endsWith("generate pdf") || checkText.endsWith("save report") || checkText.endsWith("ออกรายงาน") || checkText.endsWith("สร้าง pdf")) {
                playAudioChime('success');
                updateHandsFreeBadge('Generating PDF...', '#3498db', true);
                speakFeedback("กำลังออกรายงาน PDF");
                if (micStatusContainer) micStatusContainer.innerText = "กำลังสร้างรายงาน PDF...";
                const saveBtn = document.getElementById('btn-save-submit');
                if (saveBtn) {
                    setTimeout(() => saveBtn.click(), 800);
                }
                return;
            }

            // 5. Voice Command: Stop Recording
            if (checkText.endsWith("stop record") || checkText.endsWith("หยุดบันทึก") || checkText.endsWith("หยุดอัดเสียง")) {
                isRecording = false;
                playAudioChime('stop');
                updateHandsFreeBadge('Mic Stopped', '#95a5a6', false);
                recognition.stop();
                speakFeedback("หยุดบันทึกเสียงแล้ว");
                return;
            }

            if (txtTranscription) {
                txtTranscription.value = totalText;
                const hiddenTrans = document.getElementById('hidden-transcription');
                if (hiddenTrans) hiddenTrans.value = totalText;
            }

            // --- Smart Direct Focused Field Input (Non-Destructive) ---
            let activeEl = document.activeElement;
            const gestureFocusedEl = document.querySelector('.gesture-focus');
            if (gestureFocusedEl) {
                if (gestureFocusedEl.tagName === 'INPUT' || gestureFocusedEl.tagName === 'TEXTAREA') {
                    activeEl = gestureFocusedEl;
                } else if (gestureFocusedEl.previousElementSibling && (gestureFocusedEl.previousElementSibling.tagName === 'INPUT')) {
                    activeEl = gestureFocusedEl.previousElementSibling;
                } else if (gestureFocusedEl.closest('.form-row, .form-group, label')?.querySelector('input:focus, input')) {
                    activeEl = document.activeElement;
                }
            }

            const normText = normalizeText(totalText);
            const latestSpokenChunk = normalizeText(interimTranscript || finalTranscript);

            if (activeEl && (activeEl.tagName === 'INPUT' || activeEl.tagName === 'TEXTAREA') && activeEl !== txtTranscription) {
                const targetText = latestSpokenChunk.trim() || normText.trim();
                const numMatch = targetText.match(/\b\d+(?:\.\d+)?\b/);
                // Check if spoken phrase is a direct number/value intended for the focused input
                if (numMatch && targetText.split(/\s+/).length <= 4) {
                    activeEl.value = numMatch[0];
                    activeEl.setAttribute('data-manual', 'true');
                    activeEl.style.border = "2.5px solid #27ae60";
                    activeEl.style.backgroundColor = "#e8f8f5";
                    setTimeout(() => {
                        activeEl.style.border = "1.5px dashed #e67e22";
                        activeEl.style.backgroundColor = "";
                    }, 1200);
                    activeEl.dispatchEvent(new Event('input', { bubbles: true }));
                    activeEl.dispatchEvent(new Event('change', { bubbles: true }));
                }
            }

            // If text hasn't changed, don't re-extract
            if (normText === lastExtractedText) return;
            lastExtractedText = normText;
            const extracted = parseTextLocally(normText);
            applyLocalDataToForm(extracted);

            if (micStatusContainer) {
                if (interimTranscript) {
                    micStatusContainer.innerHTML = '<i class="fas fa-wave-square" style="color:#e67e22;"></i> กำลังพูด: <span style="color:#333;">' + interimTranscript + '</span>';
                } else {
                    micStatusContainer.innerHTML = '<span style="color:#27ae60; font-weight:bold;"><i class="fas fa-check-circle"></i> ถอดเสียงเรียลไทม์...</span>';
                }
            }
        };

        recognition.onerror = function (event) {
            if (event.error === 'no-speech') {
                if (micStatusContainer) micStatusContainer.innerHTML = '<span style="color:#e67e22;"><i class="fas fa-clock"></i> พักเสียงพูดชั่วคราว (Silence Detected)...</span>';
                // Do NOT set isRecording = false; to allow auto-restart in onend
                return;
            }

            isRecording = false;
            btnMicToggle.innerHTML = '<i class="fas fa-microphone"></i> เริ่มบันทึกเสียง (Start)';
            btnMicToggle.style.backgroundColor = '#ddd';

            if (event.error === 'not-allowed') {
                showError("ไม่อนุญาตให้ใช้ไมโครโฟน (Not Allowed). กรุณากด 'Allow' ที่แถบ URL หรือตรวจสอบการตั้งค่า");
            } else if (event.error === 'network') {
                showError("เกิดข้อผิดพลาดเครือข่าย (Network). ตรวจสอบอินเทอร์เน็ต หรือหากใช้ Chrome ปัญหาอาจเกิดจากการไม่ได้ใช้ HTTPS");
            } else {
                showError("ข้อผิดพลาด: " + event.error);
            }
        };

        btnMicToggle.addEventListener('click', async function () {
            if (isRecording) {
                isRecording = false; // Set to false first to tell onend not to auto-restart
                try { recognition.stop(); } catch(e) {}
                playAudioChime('stop');
                updateHandsFreeBadge('Hands-Free Ready', '#95a5a6', false);
                btnMicToggle.innerHTML = '<i class="fas fa-microphone"></i> เริ่มบันทึกเสียง (Start)';
                btnMicToggle.style.backgroundColor = '#ddd';
            } else {
                // Request microphone permission if needed
                if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
                    try {
                        const testAudio = await navigator.mediaDevices.getUserMedia({ audio: true });
                        testAudio.getTracks().forEach(t => t.stop());
                    } catch(micErr) {
                        showError("กรุณากด 'อนุญาต (Allow)' ไมโครโฟนในป๊อปอัปของเบราว์เซอร์");
                        return;
                    }
                }

                isRecording = true;
                if (micStatusContainer) micStatusContainer.innerText = 'กำลังเริ่ม... (Starting...)';
                try {
                    recognition.start();
                } catch (e) {
                    console.warn("Speech recognition error, trying Whisper fallback:", e);
                    // Fallback to Whisper recording
                    if (btnRecordAudio) btnRecordAudio.click();
                }
            }
        });

    } else {
        btnMicToggle.style.display = 'none';
        showError("เบราว์เซอร์นี้ไม่รองรับ Web Speech API กรุณาใช้ Chrome หรือ Edge");
    }

    const videoElement = document.querySelector('.input_video');
    const canvasElement = document.querySelector('.output_canvas');
    let canvasCtx = null;

    if (!window.isSecureContext || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        if (window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1') {
            showError(`⚠️ เบราว์เซอร์บล็อกกล้องและไมโครโฟนบน IP (${window.location.hostname}). <a href="https://localhost:7860" style="color:#2980b9; text-decoration:underline; font-weight:bold; font-size:15px; margin-left:6px;">👉 คลิกที่นี่เพื่อเปิดผ่าน https://localhost:7860</a> เพื่อให้กล้องและไมค์ทำงานได้ 100%`);
        } else {
            showError("Camera/Mic Error: Browser API 'navigator.mediaDevices' is missing. Please use Chrome or Edge.");
        }
    }

    if (canvasElement) {
        canvasCtx = canvasElement.getContext('2d');
    }

    let lastActionTime = 0;
    const ACTION_COOLDOWN = 800;
    let lastHandDetectedTime = Date.now();
    let videoFrameCounter = 0;

    function onResults(results) {
        if (!canvasCtx || !canvasElement) return;

        if (results.multiHandLandmarks && results.multiHandLandmarks.length > 0) {
            lastHandDetectedTime = Date.now();
            canvasCtx.save();
            canvasCtx.translate(canvasElement.width, 0);
            canvasCtx.scale(-1, 1);
            for (const landmarks of results.multiHandLandmarks) {
                // Neon Cyan connections and white points with cyan glow
                drawConnectors(canvasCtx, landmarks, HAND_CONNECTIONS, { color: '#00f0ff', lineWidth: 3 });
                drawLandmarks(canvasCtx, landmarks, { color: '#ffffff', fillColor: '#00f0ff', lineWidth: 1, radius: 4 });
                detectGesture(landmarks);
            }
            canvasCtx.restore();
        }
    }

    let smoothCursorX = null;
    let smoothCursorY = null;
    const EMA_ALPHA = 0.40; // Silky smooth jitter suppression filter

    function playGestureChime() {
        try {
            const AudioCtx = window.AudioContext || window.webkitAudioContext;
            if (!AudioCtx) return;
            const ctx = new AudioCtx();
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.type = 'sine';
            osc.frequency.setValueAtTime(880, ctx.currentTime);
            osc.frequency.exponentialRampToValueAtTime(1320, ctx.currentTime + 0.08);
            gain.gain.setValueAtTime(0.06, ctx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.12);
            osc.connect(gain);
            gain.connect(ctx.destination);
            osc.start();
            osc.stop(ctx.currentTime + 0.12);
        } catch(e) {}
    }

    function detectGesture(landmarks) {
        const thumbTip = landmarks[4];
        const indexTip = landmarks[8];

        const distance = Math.sqrt(
            Math.pow(thumbTip.x - indexTip.x, 2) +
            Math.pow(thumbTip.y - indexTip.y, 2)
        );

        const rawX = (thumbTip.x + indexTip.x) / 2;
        const rawY = (thumbTip.y + indexTip.y) / 2;

        if (smoothCursorX === null) {
            smoothCursorX = rawX;
            smoothCursorY = rawY;
        } else {
            smoothCursorX = smoothCursorX * (1 - EMA_ALPHA) + rawX * EMA_ALPHA;
            smoothCursorY = smoothCursorY * (1 - EMA_ALPHA) + rawY * EMA_ALPHA;
        }

        const cursorX_norm = 1 - smoothCursorX;
        const cursorY_norm = smoothCursorY;

        const rect = canvasElement.getBoundingClientRect();
        const clientX = rect.left + (cursorX_norm * rect.width);
        const clientY = rect.top + (cursorY_norm * rect.height);

        const PINCH_THRESHOLD = 0.06;

        canvasCtx.beginPath();
        canvasCtx.arc(smoothCursorX * canvasElement.width, smoothCursorY * canvasElement.height, 6, 0, 2 * Math.PI);
        canvasCtx.fillStyle = distance < PINCH_THRESHOLD ? "#00f0ff" : "rgba(255, 255, 255, 0.6)";
        canvasCtx.fill();

        if (distance < PINCH_THRESHOLD) {
            const element = document.elementFromPoint(clientX, clientY);

            if (element && element.classList.contains('gesture-box')) {
                element.classList.add('active');
                setTimeout(() => element.classList.remove('active'), 200);

                const now = Date.now();
                if (now - lastActionTime > ACTION_COOLDOWN) {
                    playGestureChime();
                    const action = element.getAttribute('data-action');
                    triggerAction(action);
                    lastActionTime = now;
                }
            }
        }
    }

    // --- อัปเดตฟังก์ชันเพื่อค้นหาช่องสี่เหลี่ยม/วงกลมโดยเฉพาะ ---
    function getVisual(el) {
        if (el.type === 'checkbox' || el.type === 'radio') {
            // ดึง element ตัวถัดไป (ซึ่งเราเขียน span จำลองสี่เหลี่ยมไว้ใน HTML)
            if (el.nextElementSibling) {
                return el.nextElementSibling;
            }
            return el.parentElement; // กรณีฉุกเฉิน
        }
        return el; // ถ้าเป็นช่อง Text ให้ล็อคที่ช่อง Text
    }

    function triggerAction(action) {
        switch (action) {
            case 'CLEAR':
                const activeElement = document.activeElement;
                if (activeElement) {
                    if (activeElement.type === 'text' || activeElement.tagName === 'TEXTAREA') {
                        activeElement.value = '';
                    }
                    else if (activeElement.type === 'checkbox' || activeElement.type === 'radio') {
                        activeElement.checked = false;
                        const parent = activeElement.parentElement;
                        if (parent && parent.classList.contains('circle-option')) {
                            const span = parent.querySelector('span');
                            if (span) span.style = "";
                        }
                    }
                    activeElement.classList.remove('low-confidence-highlight');
                    if (activeElement.nextElementSibling && activeElement.nextElementSibling.classList.contains('checkbox-visual')) {
                        activeElement.nextElementSibling.classList.remove('low-confidence-highlight');
                    }
                }
                break;
            case 'SCROLL_UP':
                const canvasUp = document.querySelector('.document-canvas') || document.querySelector('.document-pane');
                if (canvasUp) canvasUp.scrollBy({ top: -250, behavior: 'smooth' });
                break;
            case 'SCROLL_DOWN':
                const canvasDown = document.querySelector('.document-canvas') || document.querySelector('.document-pane');
                if (canvasDown) canvasDown.scrollBy({ top: 250, behavior: 'smooth' });
                break;
            case 'PREV':
                moveFocus(-1);
                break;
            case 'NEXT':
                moveFocus(1);
                break;
            case 'PREV_ROW':
                moveFocusRow(-1);
                break;
            case 'NEXT_ROW':
                moveFocusRow(1);
                break;
            case 'SELECT':
                const active = document.activeElement;
                if (active && (active.type === 'checkbox' || active.type === 'radio')) {
                    active.click();

                    // ให้วงกลมกระพริบที่กรอบสี่เหลี่ยม ไม่ใช่ครอบทั้งประโยค
                    const visualEl = getVisual(active);
                    if (visualEl) {
                        visualEl.classList.add('gesture-focus');
                        setTimeout(() => visualEl.classList.remove('gesture-focus'), 200);
                        setTimeout(() => visualEl.classList.add('gesture-focus'), 400);
                    }
                } else if (txtTranscription) {
                    txtTranscription.select();
                }
                break;
            case 'MIC_TOGGLE':
                const micBtn = document.getElementById('btn-mic-toggle');
                if (micBtn) micBtn.click();
                break;
            case 'SAVE':
                const downloadBtn = document.getElementById('btn-download-pdf');
                const saveBtn = document.getElementById('btn-save-submit');

                if (downloadBtn) {
                    window.location.href = downloadBtn.href;
                } else if (saveBtn) {
                    const form = saveBtn.closest('form');
                    if (form) form.submit();
                    else saveBtn.click();
                }
                break;
        }
    }

    function moveFocusRow(direction) {
        const inputs = Array.from(document.querySelectorAll('input[type="text"], textarea, input[type="checkbox"], input[type="radio"]'));
        const current = document.activeElement;
        const currentIndex = inputs.indexOf(current);

        if (current) {
            const currentVisual = getVisual(current);
            if (currentVisual) currentVisual.classList.remove('gesture-focus');
        }

        if (currentIndex === -1) {
            const target = direction > 0 ? inputs[0] : inputs[inputs.length - 1];
            if (target) {
                target.focus();
                const visual = getVisual(target);
                if (visual) {
                    visual.classList.add('gesture-focus');
                    visual.scrollIntoView({ behavior: 'smooth', block: 'center' });
                }
            }
            return;
        }

        const currentRect = current.getBoundingClientRect();
        const currentY = currentRect.top + currentRect.height / 2;

        let target = null;
        if (direction > 0) {
            for (let i = currentIndex + 1; i < inputs.length; i++) {
                const rect = inputs[i].getBoundingClientRect();
                const midY = rect.top + rect.height / 2;
                if (midY - currentY > 18) {
                    target = inputs[i];
                    break;
                }
            }
            if (!target && inputs.length > 0) target = inputs[0];
        } else {
            for (let i = currentIndex - 1; i >= 0; i--) {
                const rect = inputs[i].getBoundingClientRect();
                const midY = rect.top + rect.height / 2;
                if (currentY - midY > 18) {
                    target = inputs[i];
                    break;
                }
            }
            if (!target && inputs.length > 0) target = inputs[inputs.length - 1];
        }

        if (target) {
            target.focus();
            const targetVisual = getVisual(target);
            if (targetVisual) {
                targetVisual.classList.add('gesture-focus');
                targetVisual.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
        }
    }

    function moveFocus(direction) {
        const inputs = Array.from(document.querySelectorAll('input[type="text"], textarea, input[type="checkbox"], input[type="radio"]'));
        const current = document.activeElement;
        const currentIndex = inputs.indexOf(current);

        // ถอด Focus เดิมออก
        if (current) {
            const currentVisual = getVisual(current);
            if (currentVisual) currentVisual.classList.remove('gesture-focus');
        }

        let nextIndex = 0;
        if (currentIndex !== -1) {
            nextIndex = currentIndex + direction;
        }

        if (nextIndex < 0) nextIndex = inputs.length - 1;
        if (nextIndex >= inputs.length) nextIndex = 0;

        if (nextIndex >= 0 && nextIndex < inputs.length) {
            const target = inputs[nextIndex];
            target.focus(); // โฟกัส Input ซ่อนไว้

            // ล็อคเป้ากรอบแดงไปที่กล่องสี่เหลี่ยม / วงกลม / Text
            const targetVisual = getVisual(target);
            if (targetVisual) {
                targetVisual.classList.add('gesture-focus');
                targetVisual.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
        }
    }

    // --- Real-time Web Audio API Waveform & VU Meter Engine ---
    let audioVisualizerCtx = null;
    let audioVisualizerAnimId = null;

    function startAudioWaveformVisualizer(mediaStream) {
        const canvas = document.getElementById('audio-waveform-canvas');
        const container = document.getElementById('live-waveform-container');
        const vuBar = document.getElementById('audio-vu-bar');
        if (!canvas || !mediaStream) return;

        if (container) container.style.display = 'flex';
        const ctx = canvas.getContext('2d');
        const AudioCtx = window.AudioContext || window.webkitAudioContext;
        try {
            audioVisualizerCtx = new AudioCtx();
            const source = audioVisualizerCtx.createMediaStreamSource(mediaStream);
            const analyser = audioVisualizerCtx.createAnalyser();
            analyser.fftSize = 64;
            source.connect(analyser);

            const bufferLength = analyser.frequencyBinCount;
            const dataArray = new Uint8Array(bufferLength);

            function drawWaveform() {
                audioVisualizerAnimId = requestAnimationFrame(drawWaveform);
                analyser.getByteFrequencyData(dataArray);

                ctx.clearRect(0, 0, canvas.width, canvas.height);
                const barWidth = (canvas.width / bufferLength) * 1.5;
                let x = 0;
                let totalVolume = 0;

                for (let i = 0; i < bufferLength; i++) {
                    const barHeight = (dataArray[i] / 255) * canvas.height;
                    totalVolume += dataArray[i];

                    ctx.fillStyle = `rgb(46, ${Math.min(255, 180 + dataArray[i])}, 235)`;
                    ctx.fillRect(x, canvas.height - barHeight, barWidth - 1, barHeight);
                    x += barWidth + 1;
                }

                if (vuBar) {
                    const avgVol = Math.min(100, Math.round((totalVolume / (bufferLength * 160)) * 100));
                    vuBar.style.width = `${avgVol}%`;
                }
            }
            drawWaveform();
        } catch(e) {
            console.warn("Visualizer note:", e);
        }
    }

    function stopAudioWaveformVisualizer() {
        if (audioVisualizerAnimId) cancelAnimationFrame(audioVisualizerAnimId);
        if (audioVisualizerCtx && audioVisualizerCtx.state !== 'closed') {
            try { audioVisualizerCtx.close(); } catch(e) {}
        }
        const container = document.getElementById('live-waveform-container');
        if (container) container.style.display = 'none';
        const vuBar = document.getElementById('audio-vu-bar');
        if (vuBar) vuBar.style.width = '0%';
    }

    // --- Audio Recording MediaRecorder Implementation ---
    if (btnRecordAudio) {
        btnRecordAudio.addEventListener('click', async function() {
            if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
                showError("ไมโครโฟนไม่รองรับในเว็บเบราว์เซอร์นี้ หรือไม่ได้รันบน HTTPS");
                return;
            }

            try {
                const stream = await navigator.mediaDevices.getUserMedia({ 
                    audio: {
                        echoCancellation: true,
                        noiseSuppression: true,
                        autoGainControl: true
                    } 
                });
                audioChunks = [];
                mediaRecorder = new MediaRecorder(stream);
                
                mediaRecorder.ondataavailable = function(event) {
                    if (event.data.size > 0) {
                        audioChunks.push(event.data);
                    }
                };

                mediaRecorder.onstop = function() {
                    stopAudioWaveformVisualizer();
                    stream.getTracks().forEach(track => track.stop());

                    const audioBlob = new Blob(audioChunks, { type: 'audio/wav' });
                    const file = new File([audioBlob], "recorded_audio.wav", { type: "audio/wav" });
                    
                    const dataTransfer = new DataTransfer();
                    dataTransfer.items.add(file);
                    
                    if (fileUploadInput) {
                        fileUploadInput.files = dataTransfer.files;
                        if (micStatusContainer) {
                            micStatusContainer.innerHTML = '<i class="fas fa-spinner fa-spin" style="color:#27ae60;"></i> กำลังส่งไปถอดเสียงด้วย Whisper (Sending to Whisper)...';
                        }
                        if (audioUploadForm) {
                            audioUploadForm.submit();
                        }
                    }
                };

                mediaRecorder.start();
                startAudioWaveformVisualizer(stream);
                
                btnRecordAudio.style.display = 'none';
                btnStopAudio.style.display = 'inline-block';
                if (recordingTimer) {
                    recordingTimer.style.display = 'inline-block';
                    recordingTimer.innerText = '00:00';
                }

                recordingStartTime = Date.now();
                recordingTimerInterval = setInterval(updateTimer, 1000);

                if (micStatusContainer) {
                    micStatusContainer.innerText = 'กำลังอัดเสียงส่ง Whisper... (Recording for Whisper...)';
                }

            } catch (err) {
                showError("ไม่สามารถเข้าถึงไมโครโฟนได้: " + err.message);
            }
        });
    }

    if (btnStopAudio) {
        btnStopAudio.addEventListener('click', function() {
            if (mediaRecorder && mediaRecorder.state !== 'inactive') {
                mediaRecorder.stop();
            }
            stopAudioWaveformVisualizer();
            clearInterval(recordingTimerInterval);
            btnStopAudio.style.display = 'none';
            btnRecordAudio.style.display = 'inline-block';
            if (recordingTimer) {
                recordingTimer.style.display = 'none';
            }
            // Apply shimmer loading to all pathology form input visuals
            document.querySelectorAll('.patho-form input[type="text"], .patho-form textarea, .patho-form .checkbox-visual, .patho-form .circle-option').forEach(el => {
                el.classList.add('shimmer-loading');
            });
        });
    }

    function updateTimer() {
        const elapsed = Date.now() - recordingStartTime;
        const seconds = Math.floor((elapsed / 1000) % 60);
        const minutes = Math.floor((elapsed / (1000 * 60)) % 60);
        
        const pad = (num) => String(num).padStart(2, '0');
        if (recordingTimer) {
            recordingTimer.innerText = `${pad(minutes)}:${pad(seconds)}`;
        }
    }

    // --- Robust Camera Stream Engine (Direct WebRTC + MediaPipe Support) ---
    const cameraFeedEl = document.querySelector('.camera-feed');
    let localVideoStream = null;
    let handsInstance = null;
    let animFrameId = null;

    if (typeof Hands !== 'undefined') {
        try {
            handsInstance = new Hands({
                locateFile: (file) => `https://cdn.jsdelivr.net/npm/@mediapipe/hands/${file}`
            });
            handsInstance.setOptions({
                maxNumHands: 1,
                modelComplexity: 1,
                minDetectionConfidence: 0.7,
                minTrackingConfidence: 0.7
            });
            handsInstance.onResults(onResults);
        } catch (e) {
            console.warn("Hands init note:", e);
        }
    }

    async function startCameraDirectly() {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            showError("เบราว์เซอร์นี้ไม่รองรับการเปิดกล้อง หรือไม่ได้รันบน HTTPS");
            return false;
        }

        try {
            if (btnCameraToggle) {
                btnCameraToggle.innerHTML = '<i class="fas fa-spinner fa-spin"></i> กำลังเปิดกล้อง...';
            }

            localVideoStream = await navigator.mediaDevices.getUserMedia({
                video: {
                    width: { ideal: 640 },
                    height: { ideal: 480 },
                    facingMode: 'user'
                },
                audio: false
            });

            if (videoElement) {
                videoElement.srcObject = localVideoStream;
                await videoElement.play();
            }

            isCameraRunning = true;
            if (cameraFeedEl) cameraFeedEl.classList.remove('collapsed');
            if (btnCameraToggle) {
                btnCameraToggle.innerHTML = '<i class="fas fa-video-slash"></i> ปิดกล้อง (Stop)';
                btnCameraToggle.style.backgroundColor = '#ffcccc';
            }

            // Start Hands processing loop
            async function processVideoFrame() {
                if (!isCameraRunning) return;
                
                videoFrameCounter++;
                const isIdle = (Date.now() - lastHandDetectedTime) > 6000;
                
                // Mirror and draw webcam video onto canvas every frame
                if (canvasCtx && canvasElement && videoElement && videoElement.readyState >= 2) {
                    canvasCtx.save();
                    canvasCtx.translate(canvasElement.width, 0);
                    canvasCtx.scale(-1, 1);
                    canvasCtx.drawImage(videoElement, 0, 0, canvasElement.width, canvasElement.height);
                    canvasCtx.restore();
                }

                // If no hands detected for 6s, throttle MediaPipe to 15 FPS to conserve 30% CPU
                if (isIdle && (videoFrameCounter % 2 !== 0)) {
                    animFrameId = requestAnimationFrame(processVideoFrame);
                    return;
                }

                if (handsInstance && videoElement && videoElement.readyState >= 2) {
                    try {
                        await handsInstance.send({ image: videoElement });
                    } catch (e) {}
                }
                animFrameId = requestAnimationFrame(processVideoFrame);
            }
            processVideoFrame();

            return true;
        } catch (err) {
            console.error("Camera direct start error:", err);
            isCameraRunning = false;
            if (btnCameraToggle) {
                btnCameraToggle.innerHTML = '<i class="fas fa-video"></i> เปิดกล้อง (Camera)';
                btnCameraToggle.style.backgroundColor = '#ddd';
            }
            showError("ไม่สามารถเปิดกล้องได้ (" + (err.name || err.message) + "). กรุณาตรวจสอบว่าได้กด 'Allow' กล้องแล้ว");
            return false;
        }
    }

    function stopCameraDirectly() {
        isCameraRunning = false;
        if (animFrameId) cancelAnimationFrame(animFrameId);
        if (localVideoStream) {
            localVideoStream.getTracks().forEach(t => t.stop());
            localVideoStream = null;
        }
        if (videoElement) {
            videoElement.srcObject = null;
        }
        if (cameraFeedEl) cameraFeedEl.classList.add('collapsed');
        if (btnCameraToggle) {
            btnCameraToggle.innerHTML = '<i class="fas fa-video"></i> เปิดกล้อง (Camera)';
            btnCameraToggle.style.backgroundColor = '#ddd';
        }
        if (canvasCtx && canvasElement) {
            canvasCtx.clearRect(0, 0, canvasElement.width, canvasElement.height);
        }
    }

    if (btnCameraToggle) {
        btnCameraToggle.addEventListener('click', function() {
            if (isCameraRunning) {
                stopCameraDirectly();
            } else {
                startCameraDirectly();
            }
        });
    }

    // Auto-start camera on page load
    setTimeout(() => {
        if (!isCameraRunning) {
            startCameraDirectly();
        }
    }, 400);

    // Apply shimmer loading state when transcription form is submitted
    const transcriptionForm = document.getElementById('transcription-form');
    if (transcriptionForm) {
        transcriptionForm.addEventListener('submit', function() {
            document.querySelectorAll('.patho-form input[type="text"], .patho-form textarea, .patho-form .checkbox-visual, .patho-form .circle-option').forEach(el => {
                el.classList.add('shimmer-loading');
            });
        });
    }

    // --- Client-Side Local JS Processing Engine ---
    function normalizeText(text) {
        let t = text.toLowerCase();
        
        t = t.replace(/,/g, ' ');
        t = t.replace(/\./g, ' '); // Clean dots to prevent regex disruption
        
        // Thai dictation translation mapping
        const thaiToEnglish = {
            "ข้างขวา": "right",
            "ขวา": "right",
            "ข้างซ้าย": "left",
            "ซ้าย": "left",
            "ตัดเต้านม": "mastectomy",
            "มาสเทค": "mastectomy",
            "รักแร้": "axillary",
            "ต่อมน้ำเหลือง": "lymph node",
            "เซนติเนล": "sentinel",
            "ก้อนเนื้อ": "mass",
            "ขนาด": "",
            "คูณ": "x",
            "ผิวหนัง": "skin",
            "ปกติ": "normal",
            "หัวนม": "nipple",
            "ดึงรั้ง": "inverted",
            "บอด": "inverted",
            "แผลเป็น": "scar",
            "แผลเปื่อย": "ulceration"
        };
        for (const [thai, eng] of Object.entries(thaiToEnglish)) {
            t = t.replace(new RegExp(thai, 'g'), eng);
        }

        // Smart Medical Abbreviation & Typo correction
        const medicalTypos = {
            "max tech to me": "mastectomy",
            "max tech domy": "mastectomy",
            "mastech to me": "mastectomy",
            "modified radical": "modified radical mastectomy",
            "mod rad mas": "modified radical mastectomy",
            "sentinel node": "sentinel lymph node",
            "sentinel lymph": "sentinel lymph node",
            "auxiliary": "axillary",
            "axillary contents": "axillary content",
            "lymph nodes": "lymph node",
            "deep margin": "deep",
            "subareola": "subareolar",
            "skin ellipse": "skin ellipse",
            "ellipse of skin": "skin ellipse",
            "infiltrative mass": "infiltrative",
            "ulceration": "ulceration"
        };
        for (const [typo, correct] of Object.entries(medicalTypos)) {
            t = t.replace(new RegExp(typo, 'g'), correct);
        }

        const numWords = {
            "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
            "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
            "by": "x", "times": "x", "point": "."
        };
        for (const [word, val] of Object.entries(numWords)) {
            t = t.replace(new RegExp(`\\b${word}\\b`, 'g'), val);
        }
        return t;
    }

    function parseTextLocally(text) {
        const t = text;
        const data = {};

        // 1. Surgical Number
        const surgMatch = t.match(/(?:surgical number|specimen|s-)?\s*(?:is\s+)?([sS]?\s*-?\s*\d{2}\s*-?\s*\d+)/i);
        if (surgMatch) {
            let rawS = surgMatch[1].replace(/\s+/g, '').toUpperCase();
            if (!rawS.startsWith("S-")) {
                if (rawS.startsWith("S")) rawS = "S-" + rawS.slice(1);
                else rawS = "S-" + rawS;
            }
            // format digits to S-YY-NNNNN
            if (/^S-\d{5,}$/.test(rawS)) {
                rawS = "S-" + rawS.slice(2, 4) + "-" + rawS.slice(4);
            }
            data["s0_surgical_no"] = rawS;
        }

        // 2. Side
        const rightIdx = t.lastIndexOf("right");
        const leftIdx = t.lastIndexOf("left");
        if (rightIdx !== -1 || leftIdx !== -1) {
            data["s1_side"] = rightIdx > leftIdx ? "right" : "left";
        }

        // 3. Procedure
        if (t.includes("modified radical")) {
            data["s2_proc"] = "modified";
        } else if (t.includes("simple mastectomy")) {
            data["s2_proc"] = "simple";
        } else {
            const procMatch = t.match(/\b(quadrantectomy|lumpectomy|wide excision|excisional biopsy|re-excision|segmentectomy)\b(?:\s+specimen)?/i) || t.match(/procedure\s+is\s+([a-zA-Z\s]+)/i);
            if (procMatch) {
                data["s2_proc"] = "other";
                data["s2_other_text"] = procMatch[1].trim();
            }
        }

        // 4. Dimensions (3D)
        const dims3d = [];
        const dimRegex = /([\d.]+)\s*x\s*([\d.]+)\s*x\s*([\d.]+)/g;
        let match;
        while ((match = dimRegex.exec(t)) !== null) {
            dims3d.push([match[1], match[2], match[3]]);
        }
        
        if (dims3d.length > 0) {
            data["s3_dims"] = dims3d[0];
            if (dims3d.length > 1 && (t.includes("axillary") || t.includes("tail"))) {
                data["s4_check"] = true;
                data["s4_dims"] = dims3d[1];
            }
            // 4A. Previous surgical cavity with residual mass (s10_prev2)
            if (t.includes("previous surgical cavity") && (t.includes("residual") || t.includes("residual mass"))) {
                data["s10_prev2"] = true;
                data["s10_grammar"] = "is a";
                const mCavity = /(?:previous surgical cavity|adjacent fibrous tissue)[\s\S]{0,50}?([\d.]+)\s*x\s*([\d.]+)\s*x\s*([\d.]+)/i.exec(t);
                if (mCavity) {
                    data["s10_prev2_cavity_dims"] = [mCavity[1].replace(/\.$/, ''), mCavity[2].replace(/\.$/, ''), mCavity[3].replace(/\.$/, '')];
                }
                const mRes = /(?:residual mass|residual)[\s\S]{0,50}?([\d.]+)\s*x\s*([\d.]+)\s*x\s*([\d.]+)/i.exec(t);
                if (mRes) {
                    data["s10_prev2_mass_dims"] = [mRes[1].replace(/\.$/, ''), mRes[2].replace(/\.$/, ''), mRes[3].replace(/\.$/, '')];
                }
            }
            // 4B. Previous surgical cavity without residual mass (s10_prev1)
            else if (t.includes("previous surgical cavity")) {
                data["s10_prev1"] = true;
                data["s10_grammar"] = "is a";
                const mCavity = /(?:previous surgical cavity|adjacent fibrous tissue)[\s\S]{0,50}?([\d.]+)\s*x\s*([\d.]+)\s*x\s*([\d.]+)/i.exec(t);
                if (mCavity) {
                    data["s10_prev1_dims"] = [mCavity[1].replace(/\.$/, ''), mCavity[2].replace(/\.$/, ''), mCavity[3].replace(/\.$/, '')];
                }
            }
            // 4C. Well-defined firm white mass with slit-like appearance (s10_well)
            else if (t.includes("well defined") || t.includes("well-defined") || t.includes("slit like") || t.includes("slit-like")) {
                data["s10_well"] = true;
                data["s10_grammar"] = "is a";
                const mWell = /(?:well-defined|well defined|slit like|slit-like)[\s\S]{0,50}?([\d.]+)\s*x\s*([\d.]+)\s*x\s*([\d.]+)/i.exec(t);
                if (mWell) {
                    data["s10_well_dims"] = [mWell[1].replace(/\.$/, ''), mWell[2].replace(/\.$/, ''), mWell[3].replace(/\.$/, '')];
                }
            }
            // 4D. Infiltrative mass (s10_infiltrative)
            else if (t.includes("mass") || t.includes("infiltrative") || t.includes("tumor") || t.includes("lesion")) {
                data["s10_infiltrative"] = true;
                data["s10_grammar"] = t.includes("infiltrative") ? "is an" : "is a";

                if (dims3d.length > 1) {
                    data["s10_inf_dims"] = dims3d[dims3d.length - 1];
                } else if (dims3d.length === 1) {
                    const isWithoutDims = t.includes("without dimension") || t.includes("no dimension");
                    const isSpecimenMeasuring = t.includes("mastectomy") || t.includes("specimen") || t.includes("measuring");
                    if (!isWithoutDims && !isSpecimenMeasuring) {
                        const massKwIdx = Math.max(t.indexOf("mass"), t.indexOf("infiltrative"), t.indexOf("tumor"));
                        const dimRegexSingle = /([\d.]+)\s*x\s*([\d.]+)\s*x\s*([\d.]+)/;
                        const singleMatch = dimRegexSingle.exec(t);
                        if (singleMatch && massKwIdx !== -1 && Math.abs(massKwIdx - singleMatch.index) < 50) {
                            data["s10_inf_dims"] = dims3d[0];
                        }
                    }
                }
            }
        }

        // 5. Skin ellipse dimensions (2D)
        // Strip out all 3D dimension patterns first so 20x30x40 is not partially matched as 20x3
        const textWithout3D = t.replace(/[\d.]+\s*x\s*[\d.]+\s*x\s*[\d.]+/gi, '[3D_DIMS]');
        const dims2d = [];
        const dim2dRegex = /\b([\d.]+)\s*x\s*([\d.]+)\b/g;
        while ((match = dim2dRegex.exec(textWithout3D)) !== null) {
            dims2d.push([match[1], match[2]]);
        }
        // Only set skin ellipse if there is a standalone 2D dimension and skin/ellipse context
        if (dims2d.length > 0 && (t.includes("skin") || t.includes("ellipse"))) {
            data["s5_dims"] = dims2d[0];
        }
        if (t.includes("appears normal") || t.includes("skin normal")) {
            data["s5_appears_normal"] = true;
        }

        // 6. Scar & Ulceration
        if (t.includes("scar")) {
            data["s6_check"] = true;
            const scarLen = t.match(/scar\s+([\d.]+)\s*cm/);
            if (scarLen) data["s7_len"] = scarLen[1];
        }
        if (t.includes("ulceration")) {
            data["s8_check"] = true;
            const ulcerDim = t.match(/ulceration\s+([\d.]+)\s*x\s*([\d.]+)/i);
            if (ulcerDim) {
                data["s8_dims"] = [ulcerDim[1], ulcerDim[2]];
            } else if (dims2d.length > 1) {
                data["s8_dims"] = dims2d[1];
            }
        }

        // 7. Nipple status
        const s9_val = [];
        if (t.includes("everted")) s9_val.push("everted");
        if (t.includes("inverted")) s9_val.push("inverted");
        if (t.includes("ulceration")) s9_val.push("ulceration");
        if (s9_val.length > 0) data["s9_val"] = s9_val;

        // 7.5 Tumor Quadrants (Section 10.5)
        const quadrantVals = [];
        const locMatch = t.match(/(?:upper|lower|central)\s*(?:inner|outer)?\s*quadrant/i);
        if (locMatch) {
            const locText = locMatch[0].toLowerCase();
            if (locText.includes("central")) quadrantVals.push("central");
            else {
                if (locText.includes("upper")) quadrantVals.push("upper");
                if (locText.includes("lower")) quadrantVals.push("lower");
                if (locText.includes("inner")) quadrantVals.push("inner");
                if (locText.includes("outer")) quadrantVals.push("outer");
            }
        }
        if (quadrantVals.length > 0) {
            data["s10_5_quadrant_check"] = true;
            data["s10_5_quadrant_vals"] = quadrantVals;
        } else {
            const otherLocMatch = t.match(/(?:located\s+(?:in|at)|tumor\s+is\s+in|location\s+is)\s+(?:the\s+)?(axillary\s+tail(?:\s+of\s+spence)?|retroareolar|subareolar|chest\s+wall|deep\s+fascia|[a-zA-Z\s]+?(?:region|plane|tail))/i);
            if (otherLocMatch) {
                data["s10_5_other_check"] = true;
                data["s10_5_other"] = otherLocMatch[1].trim();
            }
        }

        // 8. Margins
        const margins = ["deep", "superior", "inferior", "medial", "lateral", "skin"];
        margins.forEach(m => {
            let mMatch = t.match(new RegExp(`([\\d.]+)\\s*cm\\s*(?:from|at)?\\s*${m}\\s*margin`));
            if (!mMatch) mMatch = t.match(new RegExp(`${m}\\s*margin\\s*(?:is)?\\s*([\\d.]+)\\s*cm`));
            if (!mMatch) mMatch = t.match(new RegExp(`([\\d.]+)\\s*cm\\s*from\\s*${m}`));
            if (mMatch) {
                data[`s11_${m}`] = mMatch[1];
            }
        });

        // 8.4 Fat to fibrous ratio (Section 12)
        const ratioMatch = t.match(/(?:fat to fibrous|fat to fiber|parenchyma|ratio).*?(\d+)\s*(?::|to)\s*(\d+)/i);
        if (ratioMatch) {
            data["s12_check"] = true;
            data["s12_val_left"] = ratioMatch[1];
            data["s12_val_right"] = ratioMatch[2];
        }

        // 8.5 Remaining breast tissue (Section 13)
        if (t.includes("unremarkable")) {
            data["s13_type"] = "unremarkable";
        } else {
            const remMatch = t.match(/(?:remaining|other|adjacent|uninvolved|surrounding)\s+(?:of\s+)?(?:the\s+)?(?:breast\s+)?(?:tissue|specimen|parenchyma)\s+(?:shows|is|contains|with)?\s*([a-zA-Z\s,]+?)(?:\.|\n|there\s+are|representative|$)/i);
            if (remMatch && !remMatch[1].toLowerCase().includes("unremarkable")) {
                data["s13_type"] = "other";
                data["s13_text"] = remMatch[1].trim();
            }
        }

        // 9. Lymph nodes (Section 14)
        const lymphSentence = t.match(/[^.!?]*\b(?:lymph|node|nodes)\b[^.!?]*/i);
        if (lymphSentence && !lymphSentence[0].includes("not found") && !lymphSentence[0].includes("no lymph")) {
            data["s14_check"] = true;
            const rangeMatch = lymphSentence[0].match(/ranging\s+from\s+([\d.]+)\s*(?:cm\s*)?(?:to|-)\s*([\d.]+)\s*cm/i);
            if (rangeMatch) {
                data["s14_min"] = rangeMatch[1];
                data["s14_max"] = rangeMatch[2];
            } else {
                const sizes = lymphSentence[0].match(/\b(\d+(?:\.\d+)?)\b/g);
                if (sizes && sizes.length >= 2) {
                    const sizesFloat = sizes.map(Number).filter(n => n <= 10.0);
                    if (sizesFloat.length >= 2) {
                        data["s14_min"] = Math.min(...sizesFloat).toString();
                        data["s14_max"] = Math.max(...sizesFloat).toString();
                    }
                }
            }
            const countMatch = lymphSentence[0].match(/(\d+)\s+(?:lymph\s+)?node/i);
            if (countMatch) data["s14_num"] = countMatch[1];
        }

        // 10. Sections Mapping
        const sectionMap = {
            "sec_nipple": ["nipple"],
            "sec_mass": ["mass"],
            "sec_old_biopsy": ["fibrosis", "biopsy cavity", "old biopsy"],
            "sec_deep_margin": ["deep resected", "deep margin", "the resected"],
            "sec_nearest_margin": ["nearest resected", "nearest margin", "inferior resected", "superior resected"],
            "sec_upper_inner": ["upper inner", "superior inner"],
            "sec_upper_outer": ["upper outer", "superior outer"],
            "sec_lower_inner": ["lower inner", "inferior inner"],
            "sec_lower_outer": ["lower outer", "inferior outer"],
            "sec_central": ["central"],
            "sec_axillary": ["axillary"]
        };

        data["sections"] = {};
        for (const [key, keywords] of Object.entries(sectionMap)) {
            for (const kw of keywords) {
                const pat1 = new RegExp(`((?:[a-zA-Z]\\s?-?\\s?\\d+(?:[-\\s]?\\d+)*(?:\\s*(?:to|and|-|,)\\s*)*)+)(?:\\s*(?:=|equals?|is|-|old|sampling|submitted as|with))*\\s*${kw}`);
                const pat2 = new RegExp(`${kw}(?:\\s*(?:=|equals?|is|-|old|sampling|submitted as|with))*\\s*((?:[a-zA-Z]\\s?-?\\s?\\d+(?:[-\\s]?\\d+)*(?:\\s*(?:to|and|-|,)\\s*)*)+)`);
                
                let m = t.match(pat1) || t.match(pat2);
                if (m) {
                    let clean = m[1].replace(/\b(old|is|sampling|with)\b/gi, '').trim().toUpperCase();
                    clean = clean.replace(/[^A-Z0-9-]/g, '');
                    let extra = "";
                    if (key.includes("nearest")) {
                        const extraMatch = t.match(/(?:nearest\s+resected|nearest\s+margin)[\s\S]{0,40}?(?:margin\s+)?(?:with\s+|,?\s*)(inferior|superior|medial|lateral|deep|anterior|posterior|skin)/i);
                        if (extraMatch) extra = extraMatch[1];
                    }
                    data["sections"][key] = { code: clean, extra: extra };
                    break;
                }
            }
        }

        return data;
    }

    function applyLocalDataToForm(data) {
        function setVal(selector, val) {
            const el = document.querySelector(selector);
            if (el) {
                el.removeAttribute('data-manual');
                el.style.border = "";
                if (val !== undefined && val !== null) {
                    el.value = val;
                    el.classList.remove('field-updated');
                    void el.offsetWidth; // Trigger reflow
                    el.classList.add('field-updated');
                }
            }
        }
        function setCheck(selector, isChecked) {
            const el = document.querySelector(selector);
            if (el) {
                el.removeAttribute('data-manual');
                el.checked = isChecked;
                if (el.parentElement) {
                    el.parentElement.classList.remove('field-updated');
                    void el.parentElement.offsetWidth;
                    el.parentElement.classList.add('field-updated');
                }
            }
        }

        // 1. Surgical Number
        if (data.s0_surgical_no) {
            setVal('[name="s0_surgical_no"]', data.s0_surgical_no);
        }
        // 2. Side
        if (data.s1_side) {
            const oppSide = data.s1_side === 'right' ? 'left' : 'right';
            setCheck(`[name="s1_side"][value="${oppSide}"]`, false);
            setCheck(`[name="s1_side"][value="${data.s1_side}"]`, true);
        }
        // 3. Procedure
        if (data.s2_proc) {
            ['modified', 'simple', 'other'].forEach(p => {
                if (p !== data.s2_proc) setCheck(`[name="s2_proc"][value="${p}"]`, false);
            });
            setCheck(`[name="s2_proc"][value="${data.s2_proc}"]`, true);
            if (data.s2_proc === 'other' && data.s2_other_text) {
                setVal('[name="s2_other_text"]', data.s2_other_text);
            }
        }
        // 4. Dimensions (3D)
        if (data.s3_dims) {
            setVal('[name="s3_dims_0"]', data.s3_dims[0]);
            setVal('[name="s3_dims_1"]', data.s3_dims[1]);
            setVal('[name="s3_dims_2"]', data.s3_dims[2]);
        }
        // Axillary Check
        if (data.s4_check) {
            setCheck('[name="s4_check"]', true);
            if (data.s4_dims) {
                setVal('[name="s4_dims_0"]', data.s4_dims[0]);
                setVal('[name="s4_dims_1"]', data.s4_dims[1]);
                setVal('[name="s4_dims_2"]', data.s4_dims[2]);
            }
        }
        // Skin ellipse
        if (data.s5_dims) {
            setVal('[name="s5_dims_0"]', data.s5_dims[0]);
            setVal('[name="s5_dims_1"]', data.s5_dims[1]);
        }
        if (data.s5_appears_normal) {
            setCheck('[name="s5_appears_normal"]', true);
        }
        // Scar
        if (data.s6_check) {
            setCheck('[name="s6_check"]', true);
            if (data.s7_len) setVal('[name="s7_len"]', data.s7_len);
        }
        // Ulcer
        if (data.s8_check) {
            setCheck('[name="s8_check"]', true);
            if (data.s8_dims) {
                setVal('[name="s8_dims_0"]', data.s8_dims[0]);
                setVal('[name="s8_dims_1"]', data.s8_dims[1]);
            }
        }
        // Nipple
        if (data.s9_val) {
            data.s9_val.forEach(v => {
                setCheck(`[name="s9_val"][value="${v}"]`, true);
            });
        }
        // Infiltrative mass
        if (data.s10_infiltrative) {
            setCheck('[name="s10_infiltrative"]', true);
            setCheck(`[name="s10_grammar"][value="${data.s10_grammar || 'is an'}"]`, true);
            if (data.s10_inf_dims) {
                setVal('[name="s10_inf_dims_0"]', data.s10_inf_dims[0]);
                setVal('[name="s10_inf_dims_1"]', data.s10_inf_dims[1]);
                setVal('[name="s10_inf_dims_2"]', data.s10_inf_dims[2]);
            }
        }
        // Well-defined mass with slit-like appearance
        if (data.s10_well) {
            setCheck('[name="s10_well"]', true);
            setCheck(`[name="s10_grammar"][value="${data.s10_grammar || 'is a'}"]`, true);
            if (data.s10_well_dims) {
                setVal('[name="s10_well_dims_0"]', data.s10_well_dims[0]);
                setVal('[name="s10_well_dims_1"]', data.s10_well_dims[1]);
                setVal('[name="s10_well_dims_2"]', data.s10_well_dims[2]);
            }
        }
        // Previous surgical cavity without residual mass
        if (data.s10_prev1) {
            setCheck('[name="s10_prev1"]', true);
            setCheck(`[name="s10_grammar"][value="${data.s10_grammar || 'is a'}"]`, true);
            if (data.s10_prev1_dims) {
                setVal('[name="s10_prev1_dims_0"]', data.s10_prev1_dims[0]);
                setVal('[name="s10_prev1_dims_1"]', data.s10_prev1_dims[1]);
                setVal('[name="s10_prev1_dims_2"]', data.s10_prev1_dims[2]);
            }
        }
        // Previous surgical cavity with residual mass
        if (data.s10_prev2) {
            setCheck('[name="s10_prev2"]', true);
            setCheck(`[name="s10_grammar"][value="${data.s10_grammar || 'is a'}"]`, true);
            if (data.s10_prev2_cavity_dims) {
                setVal('[name="s10_prev2_cavity_dims_0"]', data.s10_prev2_cavity_dims[0]);
                setVal('[name="s10_prev2_cavity_dims_1"]', data.s10_prev2_cavity_dims[1]);
                setVal('[name="s10_prev2_cavity_dims_2"]', data.s10_prev2_cavity_dims[2]);
            }
            if (data.s10_prev2_mass_dims) {
                setVal('[name="s10_prev2_mass_dims_0"]', data.s10_prev2_mass_dims[0]);
                setVal('[name="s10_prev2_mass_dims_1"]', data.s10_prev2_mass_dims[1]);
                setVal('[name="s10_prev2_mass_dims_2"]', data.s10_prev2_mass_dims[2]);
            }
        }
        // Tumor Quadrants (10.5)
        if (data.s10_5_quadrant_check && data.s10_5_quadrant_vals) {
            setCheck('[name="s10_5_quadrant_check"]', true);
            data.s10_5_quadrant_vals.forEach(q => {
                setCheck(`[name="s10_5_quadrant_vals"][value="${q}"]`, true);
            });
        if (data.s10_5_other || data.s10_5_other_check) {
            setCheck('[name="s10_5_other_check"]', true);
            if (data.s10_5_other) setVal('[name="s10_5_other"]', data.s10_5_other);
        }
        // Margins (Section 11)
        const margins = ["deep", "superior", "inferior", "medial", "lateral", "skin"];
        margins.forEach(m => {
            if (data[`s11_${m}`]) {
                setVal(`[name="s11_${m}"]`, data[`s11_${m}`]);
            }
        });
        // Fat to fibrous ratio (Section 12)
        if (data.s12_check || data.s12_val_left || data.s12_val_right) {
            setCheck('[name="s12_check"]', true);
            if (data.s12_val_left) setVal('[name="s12_val_left"]', data.s12_val_left);
            if (data.s12_val_right) setVal('[name="s12_val_right"]', data.s12_val_right);
        }
        // Remaining Breast Tissue (Section 13)
        if (data.s13_type === 'unremarkable') {
            setCheck('[name="s13_type"][value="unremarkable"]', true);
            setCheck('[name="s13_type"][value="other"]', false);
        } else if (data.s13_type === 'other' || data.s13_text) {
            setCheck('[name="s13_type"][value="other"]', true);
            setCheck('[name="s13_type"][value="unremarkable"]', false);
            if (data.s13_text) setVal('[name="s13_text"]', data.s13_text);
        }
        // Lymph nodes (Section 14)
        if (data.s14_check) {
            setCheck('[name="s14_check"]', true);
            if (data.s14_num) setVal('[name="s14_num"]', data.s14_num);
            if (data.s14_min) setVal('[name="s14_min"]', data.s14_min);
            if (data.s14_max) setVal('[name="s14_max"]', data.s14_max);
        }
        // Sections (Section 15)
        if (data.sections) {
            for (const [key, codeObj] of Object.entries(data.sections)) {
                const codeVal = typeof codeObj === 'object' ? codeObj.code : codeObj;
                setVal(`[name="${key}"]`, codeVal);
            }
        }

        // Live Count Filled Sections
        let filledCount = 0;
        if (document.querySelector('[name="s0_surgical_no"]')?.value) filledCount++;
        if (document.querySelector('[name="s1_side"]:checked')) filledCount++;
        if (document.querySelector('[name="s2_proc"]:checked')) filledCount++;
        if (document.querySelector('[name="s3_dims_0"]')?.value) filledCount++;
        if (document.querySelector('[name="s4_check"]:checked')) filledCount++;
        if (document.querySelector('[name="s5_dims_0"]')?.value || document.querySelector('[name="s5_appears_normal"]:checked')) filledCount++;
        if (document.querySelector('[name="s6_check"]:checked')) filledCount++;
        if (document.querySelector('[name="s8_check"]:checked')) filledCount++;
        if (document.querySelector('[name="s9_val"]:checked')) filledCount++;
        if (document.querySelector('[name="s10_infiltrative"]:checked')) filledCount++;
        if (document.querySelector('[name="s11_deep"]')?.value || document.querySelector('[name="s11_superior"]')?.value) filledCount++;
        if (document.querySelector('[name="s14_check"]:checked')) filledCount++;
        if (document.querySelector('[name="sec_nipple"]')?.value || document.querySelector('[name="sec_mass"]')?.value) filledCount++;

        const micStatus = document.getElementById('mic-status-container');
        if (micStatus && filledCount > 0) {
            micStatus.innerHTML = `<span style="color:#27ae60; font-weight:bold;"><i class="fas fa-magic"></i> สกัดข้อมูลเรียลไทม์สำเร็จแล้ว (${filledCount} / 15 หัวข้อ)</span>`;
        }
    }

    // --- Live Textarea Sync (Keyboard edits update form real-time) ---
    if (txtTranscription) {
        txtTranscription.addEventListener('input', function() {
            const rawText = txtTranscription.value;
            const normText = normalizeText(rawText);
            const extracted = parseTextLocally(normText);
            applyLocalDataToForm(extracted);
            validateFormData();
            if (micStatusContainer) {
                micStatusContainer.innerHTML = '<span style="color:#27ae60;"><i class="fas fa-keyboard"></i> พิมพ์แก้ไข: ปรับปรุงฟอร์มเรียลไทม์สำเร็จ</span>';
            }
        });
    }

    // --- Smart Clinical Validation Warning Engine ---
    function validateFormData() {
        const warnings = [];
        
        // Helper to get input float value
        function getFloatVal(name) {
            const el = document.querySelector(`[name="${name}"]`);
            return el ? parseFloat(el.value) || 0 : 0;
        }

        // 0. Check Surgical Number (Critical Patient Identifier)
        const s0Input = document.querySelector('[name="s0_surgical_no"]');
        const rawTranscription = txtTranscription ? txtTranscription.value.trim() : '';
        if (s0Input) {
            if (rawTranscription.length > 10 && !s0Input.value.trim()) {
                warnings.push(`⚠️ <strong>Missing Surgical Number:</strong> ไม่พบรหัสสิ่งส่งตรวจในข้อความบรรยาย กรุณาระบุรหัสเคส (เช่น S-24-XXXX) เพื่อความปลอดภัยของเวชระเบียน`);
                s0Input.style.border = "2px solid #e67e22";
                s0Input.style.backgroundColor = "#fef9e7";
                s0Input.style.boxShadow = "0 0 8px rgba(230, 126, 34, 0.4)";
            } else {
                s0Input.style.border = "";
                s0Input.style.backgroundColor = "";
                s0Input.style.boxShadow = "";
            }
        }

        // 1. Check Side Selection (Left / Right)
        const sideRight = document.querySelector('[name="s1_side"][value="right"]')?.checked;
        const sideLeft = document.querySelector('[name="s1_side"][value="left"]')?.checked;
        if (rawTranscription.length > 20 && !sideRight && !sideLeft) {
            warnings.push(`⚠️ <strong>Missing Breast Side:</strong> ยังไม่ได้ระบุข้างของเต้านม (Left หรือ Right)`);
        }

        // 2. Check Specimen 3D Dimensions Completeness
        const specX = getFloatVal('s3_dims_0');
        const specY = getFloatVal('s3_dims_1');
        const specZ = getFloatVal('s3_dims_2');
        const specInputs = [document.querySelector('[name="s3_dims_0"]'), document.querySelector('[name="s3_dims_1"]'), document.querySelector('[name="s3_dims_2"]')];
        
        if (rawTranscription.length > 20 && (specX === 0 || specY === 0 || specZ === 0)) {
            warnings.push(`⚠️ <strong>Incomplete Specimen Dimensions:</strong> ขนาดชิ้นเนื้อเต้านม (Measuring) ยังระบุไม่ครบ 3 มิติ (กว้าง x ยาว x สูง)`);
            specInputs.forEach(inp => {
                if (inp && (!inp.value || inp.value === '0')) {
                    inp.style.border = "1.5px solid #e67e22";
                    inp.style.backgroundColor = "#fef9e7";
                } else if (inp) {
                    inp.style.border = "";
                    inp.style.backgroundColor = "";
                }
            });
        } else {
            specInputs.forEach(inp => { if (inp) { inp.style.border = ""; inp.style.backgroundColor = ""; } });
        }

        // 3. Compare Tumor dimensions with Specimen dimensions (Physical Feasibility)
        const tumorX = getFloatVal('s10_inf_dims_0');
        const tumorY = getFloatVal('s10_inf_dims_1');
        const tumorZ = getFloatVal('s10_inf_dims_2');
        const specMax = Math.max(specX, specY, specZ);
        const tumorMax = Math.max(tumorX, tumorY, tumorZ);

        if (tumorMax > 0 && specMax > 0 && tumorMax > specMax) {
            warnings.push(`⚠️ <strong>Physical Contradiction:</strong> ขนาดก้อนมะเร็งใหญ่สุด (${tumorMax} cm) มีขนาดใหญ่กว่าขนาดชิ้นเนื้อเต้านมที่ตัดมา (${specMax} cm) ซึ่งขัดแย้งทางกายภาพ`);
        }

        // 4. Check Mass Dimensions when Mass Type is checked
        const hasInfiltrative = document.querySelector('[name="s10_infiltrative"]')?.checked;
        const hasWell = document.querySelector('[name="s10_well"]')?.checked;
        if (hasInfiltrative && (tumorX === 0 || tumorY === 0 || tumorZ === 0)) {
            warnings.push(`⚠️ <strong>Missing Tumor Dimensions:</strong> ติ๊กเลือกพบก้อนมะเร็ง (Infiltrative mass) แต่ยังไม่ได้ระบุขนาดก้อน 3 มิติครบถ้วน`);
        }

        // 5. Check MRM procedure completeness (Modified Radical Mastectomy)
        const isModified = document.querySelector('[name="s2_proc"][value="modified"]')?.checked;
        const axillaryCheck = document.querySelector('[name="s4_check"]')?.checked;
        const lymphCheck = document.querySelector('[name="s14_check"]')?.checked;

        if (isModified) {
            if (!axillaryCheck && !lymphCheck) {
                warnings.push(`⚠️ <strong>Clinical Procedure Check:</strong> เลือกการผ่าตัดแบบ MRM แต่ยังไม่ได้ระบุส่วน "Axillary Content" หรือ "Lymph Nodes" ของชิ้นเนื้อรักแร้`);
            }
        }

        // Display warnings in the UI warning box
        const warnBox = document.getElementById('clinical-warning-box');
        const warnText = document.getElementById('clinical-warning-text');
        
        if (warnBox && warnText) {
            if (warnings.length > 0) {
                warnText.innerHTML = warnings.join('<br><br>');
                warnBox.style.display = 'block';
            } else {
                warnBox.style.display = 'none';
            }
        }
    }

    // --- Manual Field Locking Helpers ---
    function unlockAllFields() {
        document.querySelectorAll('.patho-form input, .patho-form textarea, .patho-form select').forEach(el => {
            el.removeAttribute('data-manual');
            el.style.border = "";
        });
        validateFormData();
    }

    function initManualFieldLocking() {
        document.querySelectorAll('.patho-form input, .patho-form textarea, .patho-form select').forEach(el => {
            if (el.name === 'transcription' || el.name === 'audio_filename') return;

            const lockHandler = function() {
                el.setAttribute('data-manual', 'true');
                el.style.border = "1px dashed #e67e22"; // visual indicator for manual overwrite
                validateFormData(); // Recalculate validation when user manual edits
            };

            el.addEventListener('change', lockHandler);
            el.addEventListener('input', lockHandler);
        });
    }

    // Initialize Manual Lock listeners
    initManualFieldLocking();
    validateFormData(); // Initial validation check

    const btnLocalExtract = document.getElementById('btn-local-extract');
    if (btnLocalExtract) {
        btnLocalExtract.addEventListener('click', function() {
            const rawText = txtTranscription.value;
            if (!rawText || rawText.trim() === "") {
                alert("กรุณากรอกหรืออัดข้อความก่อนสกัดคำ (Please input or record text first)");
                return;
            }

            // Apply shimmer class for 300ms to show visual feedback
            document.querySelectorAll('.patho-form input[type="text"], .patho-form textarea, .patho-form .checkbox-visual, .patho-form .circle-option').forEach(el => {
                el.classList.add('shimmer-loading');
            });

            setTimeout(() => {
                const normText = normalizeText(rawText);
                const extracted = parseTextLocally(normText);
                applyLocalDataToForm(extracted);
                validateFormData();

                // Remove shimmer class
                document.querySelectorAll('.patho-form input[type="text"], .patho-form textarea, .patho-form .checkbox-visual, .patho-form .circle-option').forEach(el => {
                    el.classList.remove('shimmer-loading');
                });

                // Show status
                if (micStatusContainer) {
                    micStatusContainer.innerHTML = '<span style="color:#e67e22; font-weight:bold;"><i class="fas fa-bolt"></i> สกัดคำในบราวเซอร์สำเร็จแล้ว! (Client-Side Local Extraction completed)</span>';
                }
                autoSaveDraft();
            }, 300);
        });
    }

    // Connect Sidebar 'Fill again' button and real-time syncing
    const btnReextractSide = document.getElementById('btn-reextract-side');
    const sidebarTranscriptionBox = document.getElementById('sidebar-transcription-box');

    if (btnReextractSide) {
        btnReextractSide.addEventListener('click', function() {
            const rawText = sidebarTranscriptionBox ? sidebarTranscriptionBox.value : (txtTranscription ? txtTranscription.value : '');
            if (!rawText || rawText.trim() === "") {
                alert("ไม่มีข้อความเสียงสำหรับการสกัดคำ (No transcript text to extract)");
                return;
            }

            if (txtTranscription) txtTranscription.value = rawText;

            // Flash effect
            document.querySelectorAll('.patho-form input[type="text"], .patho-form textarea, .patho-form .checkbox-visual, .patho-form .circle-option').forEach(el => {
                el.classList.add('shimmer-loading');
            });

            setTimeout(() => {
                const normText = normalizeText(rawText);
                const extracted = parseTextLocally(normText);
                applyLocalDataToForm(extracted);
                validateFormData();

                document.querySelectorAll('.patho-form input[type="text"], .patho-form textarea, .patho-form .checkbox-visual, .patho-form .circle-option').forEach(el => {
                    el.classList.remove('shimmer-loading');
                });

                if (micStatusContainer) {
                    micStatusContainer.innerHTML = '<span style="color:#10b981; font-weight:bold;"><i class="fas fa-check-circle"></i> สกัดคำและเติมลงฟอร์มเรียบร้อยแล้ว!</span>';
                }
                autoSaveDraft();
            }, 250);
        });
    }

    if (sidebarTranscriptionBox && txtTranscription) {
        sidebarTranscriptionBox.addEventListener('input', function() {
            txtTranscription.value = sidebarTranscriptionBox.value;
            autoSaveDraft();
        });
        txtTranscription.addEventListener('input', function() {
            sidebarTranscriptionBox.value = txtTranscription.value;
        });
    }

    // --- Enterprise Local Draft Auto-Save & Crash Recovery Engine ---
    const DRAFT_STORAGE_KEY = 'patho_form_draft_v1';
    let draftSaveTimeout = null;

    function autoSaveDraft() {
        if (draftSaveTimeout) clearTimeout(draftSaveTimeout);
        draftSaveTimeout = setTimeout(() => {
            try {
                const formData = {};
                document.querySelectorAll('.patho-form input, .patho-form select, .patho-form textarea').forEach(el => {
                    if (!el.name || el.name === 'audio_file') return;
                    if (el.type === 'radio' || el.type === 'checkbox') {
                        if (el.checked) formData[el.name] = el.value;
                    } else {
                        if (el.value) formData[el.name] = el.value;
                    }
                });
                if (Object.keys(formData).length > 0) {
                    localStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify({
                        data: formData,
                        savedAt: new Date().toISOString()
                    }));
                }
            } catch(e) {}
        }, 500);
    }

    function restoreDraftIfAvailable() {
        try {
            const saved = localStorage.getItem(DRAFT_STORAGE_KEY);
            if (!saved) return;
            const parsed = JSON.parse(saved);
            if (!parsed || !parsed.data) return;

            const currentSurgNo = document.querySelector('[name="s0_surgical_no"]')?.value;
            // Only restore if form is empty
            if (!currentSurgNo || currentSurgNo.trim() === '') {
                Object.entries(parsed.data).forEach(([name, val]) => {
                    const inputs = document.querySelectorAll(`[name="${name}"]`);
                    if (inputs.length > 0 && (inputs[0].type === 'radio' || inputs[0].type === 'checkbox')) {
                        inputs.forEach(r => {
                            if (r.value === val) r.checked = true;
                        });
                    } else if (inputs.length > 0) {
                        inputs[0].value = val;
                    }
                });
                validateFormData();
                if (micStatusContainer) {
                    micStatusContainer.innerHTML = '<span style="color:#2980b9;"><i class="fas fa-history"></i> กู้คืนข้อมูลร่างล่าสุดอัตโนมัติ (Draft Auto-Restored)</span>';
                }
            }
        } catch(e) {}
    }

    function clearLocalDraft() {
        try {
            localStorage.removeItem(DRAFT_STORAGE_KEY);
        } catch(e) {}
    }

    // Auto-save on every input change
    document.querySelectorAll('.patho-form input, .patho-form select, .patho-form textarea').forEach(el => {
        el.addEventListener('input', autoSaveDraft);
        el.addEventListener('change', autoSaveDraft);
    });

    // Clear draft when successfully submitting PDF
    const formElement = document.querySelector('.patho-form');
    if (formElement) {
        formElement.addEventListener('submit', () => clearLocalDraft());
    }

    // --- Interactive Paper Zoom Controller (- 100% +) ---
    let currentDocZoom = 1.0;
    const paperSheetElement = document.querySelector('.paper-sheet');
    const zoomTextElement = document.getElementById('zoom-level-text');
    const btnZoomIn = document.getElementById('btn-zoom-in');
    const btnZoomOut = document.getElementById('btn-zoom-out');

    function setPaperZoom(newZoom) {
        currentDocZoom = Math.min(Math.max(newZoom, 0.55), 1.5);
        if (paperSheetElement) {
            paperSheetElement.style.transform = `scale(${currentDocZoom})`;
            paperSheetElement.style.transformOrigin = 'top center';
        }
        if (zoomTextElement) {
            zoomTextElement.textContent = `${Math.round(currentDocZoom * 100)}%`;
        }
    }

    if (btnZoomIn) {
        btnZoomIn.addEventListener('click', (e) => {
            e.preventDefault();
            setPaperZoom(currentDocZoom + 0.1);
        });
    }

    if (btnZoomOut) {
        btnZoomOut.addEventListener('click', (e) => {
            e.preventDefault();
            setPaperZoom(currentDocZoom - 0.1);
        });
    }

    // Restore draft on load
    restoreDraftIfAvailable();
}
});
