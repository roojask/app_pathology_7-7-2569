document.addEventListener('DOMContentLoaded', function () {
    const btnMicToggle = document.getElementById('btn-mic-toggle');
    const txtTranscription = document.getElementById('transcription-text');
    const micStatusContainer = document.getElementById('mic-status-container');

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

    let currentMicLang = 'th-TH';
    const btnLangToggle = document.getElementById('btn-lang-toggle');

    if (btnLangToggle) {
        btnLangToggle.addEventListener('click', function () {
            if (currentMicLang === 'th-TH') {
                currentMicLang = 'en-US';
                btnLangToggle.style.backgroundColor = '#8e44ad';
                btnLangToggle.innerHTML = '<i class="fas fa-language"></i> ไมค์: Eng (en-US)';
            } else {
                currentMicLang = 'th-TH';
                btnLangToggle.style.backgroundColor = '#3498db';
                btnLangToggle.innerHTML = '<i class="fas fa-language"></i> ไมค์: ไทย (th-TH)';
            }
            if (recognition) {
                recognition.lang = currentMicLang;
                if (isRecording) {
                    recognition.stop();
                    setTimeout(() => { try { recognition.start(); } catch(e) {} }, 200);
                }
            }
        });
    }

    if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        recognition = new SpeechRecognition();
        recognition.continuous = true;
        recognition.interimResults = true;
        recognition.lang = currentMicLang;

        recognition.onstart = function () {
            isRecording = true;
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
            if (checkText.endsWith("clear all") || checkText.endsWith("reset form") || checkText.endsWith("ล้างข้อมูล")) {
                txtTranscription.value = "";
                if (typeof unlockAllFields === 'function') unlockAllFields();
                document.querySelectorAll('.patho-form input[type="text"], .patho-form textarea').forEach(el => {
                    el.value = '';
                });
                document.querySelectorAll('.patho-form input[type="checkbox"], .patho-form input[type="radio"]').forEach(el => {
                    el.checked = false;
                });
                if (micStatusContainer) micStatusContainer.innerText = "ล้างฟอร์มเรียบร้อยแล้ว (Form Cleared)";
                speakFeedback("ล้างข้อมูลเรียบร้อยแล้ว");
                recognition.stop();
                setTimeout(() => {
                    try { recognition.start(); } catch(e) {}
                }, 200);
                return;
            }

            // 2. Voice Command: Generate PDF / Save Report
            if (checkText.endsWith("generate pdf") || checkText.endsWith("save report") || checkText.endsWith("ออกรายงาน") || checkText.endsWith("สร้าง pdf")) {
                speakFeedback("กำลังออกรายงาน PDF");
                if (micStatusContainer) micStatusContainer.innerText = "กำลังสร้างรายงาน PDF...";
                const saveBtn = document.getElementById('btn-save-submit');
                if (saveBtn) {
                    setTimeout(() => saveBtn.click(), 800);
                }
                return;
            }

            // 3. Voice Command: Stop Recording
            if (checkText.endsWith("stop record") || checkText.endsWith("หยุดบันทึก") || checkText.endsWith("หยุดอัดเสียง")) {
                isRecording = false;
                recognition.stop();
                speakFeedback("หยุดบันทึกเสียงแล้ว");
                return;
            }

            // 4. Voice Command: Extract Data
            if (checkText.endsWith("extract data") || checkText.endsWith("สกัดข้อมูล")) {
                speakFeedback("กำลังสกัดข้อมูลลงแบบฟอร์ม");
                if (micStatusContainer) micStatusContainer.innerText = "กำลังสกัดข้อมูลลงแบบฟอร์ม...";
                const extractBtn = document.querySelector('button[type="submit"].btn-generate');
                if (extractBtn) extractBtn.click();
                return;
            }

            if (txtTranscription) {
                txtTranscription.value = totalText;
            }

            // Real-time local extraction!
            const normText = normalizeText(totalText);
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

        btnMicToggle.addEventListener('click', function () {
            if (isRecording) {
                isRecording = false; // Set to false first to tell onend not to auto-restart
                recognition.stop();
            } else {
                isRecording = true;
                if (micStatusContainer) micStatusContainer.innerText = 'กำลังเริ่ม... (Starting...)';
                try {
                    recognition.start();
                } catch (e) {
                    showError("ไม่สามารถเริ่มไมค์ได้: " + e.message);
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

    if (!window.isSecureContext) {
        showError("Camera Error: App is NOT running in a Secure Context (HTTPS).");
    } else if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        showError("Camera Error: Browser API 'navigator.mediaDevices' is missing.");
    }

    if (canvasElement) {
        canvasCtx = canvasElement.getContext('2d');
    }

    let lastActionTime = 0;
    const ACTION_COOLDOWN = 800;

    function onResults(results) {
        if (!canvasCtx) return;

        canvasCtx.save();
        canvasCtx.translate(canvasElement.width, 0);
        canvasCtx.scale(-1, 1);
        canvasCtx.clearRect(0, 0, canvasElement.width, canvasElement.height);
        canvasCtx.drawImage(results.image, 0, 0, canvasElement.width, canvasElement.height);

        if (results.multiHandLandmarks) {
            for (const landmarks of results.multiHandLandmarks) {
                // Neon Cyan connections and white points with cyan glow
                drawConnectors(canvasCtx, landmarks, HAND_CONNECTIONS, { color: '#00f0ff', lineWidth: 3 });
                drawLandmarks(canvasCtx, landmarks, { color: '#ffffff', fillColor: '#00f0ff', lineWidth: 1, radius: 4 });
                detectGesture(landmarks);
            }
        }
        canvasCtx.restore();
    }

    function detectGesture(landmarks) {
        const thumbTip = landmarks[4];
        const indexTip = landmarks[8];

        const distance = Math.sqrt(
            Math.pow(thumbTip.x - indexTip.x, 2) +
            Math.pow(thumbTip.y - indexTip.y, 2)
        );

        const cursorX_norm = 1 - ((thumbTip.x + indexTip.x) / 2);
        const cursorY_norm = (thumbTip.y + indexTip.y) / 2;

        const rect = canvasElement.getBoundingClientRect();
        const clientX = rect.left + (cursorX_norm * rect.width);
        const clientY = rect.top + (cursorY_norm * rect.height);

        const midX = (thumbTip.x + indexTip.x) / 2;
        const midY = (thumbTip.y + indexTip.y) / 2;

        const PINCH_THRESHOLD = 0.06;

        canvasCtx.beginPath();
        canvasCtx.arc(midX * canvasElement.width, midY * canvasElement.height, 6, 0, 2 * Math.PI);
        canvasCtx.fillStyle = distance < PINCH_THRESHOLD ? "#00f0ff" : "rgba(255, 255, 255, 0.6)";
        canvasCtx.fill();

        if (distance < PINCH_THRESHOLD) {
            const element = document.elementFromPoint(clientX, clientY);

            if (element && element.classList.contains('gesture-box')) {
                element.classList.add('active');
                setTimeout(() => element.classList.remove('active'), 200);

                const now = Date.now();
                if (now - lastActionTime > ACTION_COOLDOWN) {
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
                document.querySelector('.document-pane').scrollBy({ top: -200, behavior: 'smooth' });
                break;
            case 'SCROLL_DOWN':
                document.querySelector('.document-pane').scrollBy({ top: 200, behavior: 'smooth' });
                break;
            case 'PREV':
                moveFocus(-1);
                break;
            case 'NEXT':
                moveFocus(1);
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
                
                btnRecordAudio.style.display = 'none';
                btnStopAudio.style.display = 'inline-block';
                if (recordingTimer) {
                    recordingTimer.style.display = 'inline-block';
                    recordingTimer.innerText = '00:00';
                }
                const waveformAnim = document.getElementById('waveform-animation');
                if (waveformAnim) {
                    waveformAnim.style.display = 'flex';
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
            clearInterval(recordingTimerInterval);
            btnStopAudio.style.display = 'none';
            btnRecordAudio.style.display = 'inline-block';
            if (recordingTimer) {
                recordingTimer.style.display = 'none';
            }
            const waveformAnim = document.getElementById('waveform-animation');
            if (waveformAnim) {
                waveformAnim.style.display = 'none';
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

    // --- Camera Toggle Controls ---
    const cameraFeedEl = document.querySelector('.camera-feed');

    if (btnCameraToggle) {
        btnCameraToggle.addEventListener('click', function() {
            if (!cameraInstance) return;
            
            if (isCameraRunning) {
                cameraInstance.stop();
                isCameraRunning = false;
                if (cameraFeedEl) cameraFeedEl.classList.add('collapsed');
                btnCameraToggle.innerHTML = '<i class="fas fa-video"></i> เปิดกล้อง (Camera)';
                btnCameraToggle.style.backgroundColor = '#ddd';
                if (canvasCtx) {
                    canvasCtx.clearRect(0, 0, canvasElement.width, canvasElement.height);
                }
            } else {
                btnCameraToggle.innerHTML = '<i class="fas fa-spinner fa-spin"></i> กำลังเปิด...';
                cameraInstance.start()
                    .then(() => {
                        isCameraRunning = true;
                        if (cameraFeedEl) cameraFeedEl.classList.remove('collapsed');
                        btnCameraToggle.innerHTML = '<i class="fas fa-video-slash"></i> ปิดกล้อง (Stop)';
                        btnCameraToggle.style.backgroundColor = '#ffcccc';
                    })
                    .catch(err => {
                        isCameraRunning = false;
                        if (cameraFeedEl) cameraFeedEl.classList.add('collapsed');
                        btnCameraToggle.innerHTML = '<i class="fas fa-video"></i> เปิดกล้อง (Camera)';
                        btnCameraToggle.style.backgroundColor = '#ddd';
                        showError("Camera Error: " + err.message);
                    });
            }
        });
    }

    if (typeof Hands !== 'undefined') {
        const hands = new Hands({
            locateFile: (file) => {
                return `https://cdn.jsdelivr.net/npm/@mediapipe/hands/${file}`;
            }
        });

        hands.setOptions({
            maxNumHands: 1,
            modelComplexity: 1,
            minDetectionConfidence: 0.7,
            minTrackingConfidence: 0.7
        });

        hands.onResults(onResults);

        if (videoElement) {
            cameraInstance = new Camera(videoElement, {
                onFrame: async () => {
                    if (isCameraRunning) {
                        await hands.send({ image: videoElement });
                    }
                },
                width: 480,
                height: 360
            });
            
            // Auto-start camera
            cameraInstance.start()
                .then(() => {
                    isCameraRunning = true;
                    if (cameraFeedEl) cameraFeedEl.classList.remove('collapsed');
                    if (btnCameraToggle) {
                        btnCameraToggle.innerHTML = '<i class="fas fa-video-slash"></i> ปิดกล้อง (Stop)';
                        btnCameraToggle.style.backgroundColor = '#ffcccc';
                    }
                })
                .catch(err => {
                    isCameraRunning = false;
                    if (cameraFeedEl) cameraFeedEl.classList.add('collapsed');
                    if (btnCameraToggle) {
                        btnCameraToggle.innerHTML = '<i class="fas fa-video"></i> เปิดกล้อง (Camera)';
                        btnCameraToggle.style.backgroundColor = '#ddd';
                    }
                    const overlay = document.querySelector('.camera-overlay-text');
                    if (overlay) {
                        overlay.innerHTML = `<span style="color: red; font-weight: bold;">Camera Error: ${err.message || err.name}. Please allow camera access.</span>`;
                    }
                    showError("Camera Error: " + (err.message || err.name));
                });
        }
    } else {

        console.warn("MediaPipe Hands library not loaded.");
    }

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
            const procMatch = t.match(/procedure is ([a-zA-Z\s]+)/);
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
            if (t.includes("mass") || t.includes("infiltrative")) {
                data["s10_infiltrative"] = true;
                data["s10_inf_dims"] = dims3d[dims3d.length - 1];
                data["s10_grammar"] = "is a";
            }
        }

        // 5. Skin ellipse dimensions (2D)
        const dims2d = [];
        const dim2dRegex = /([\d.]+)\s*x\s*([\d.]+)(?!\s*x)/g;
        while ((match = dim2dRegex.exec(t)) !== null) {
            dims2d.push([match[1], match[2]]);
        }
        if (dims2d.length > 0) {
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
            if (dims2d.length > 1) {
                data["s8_dims"] = dims2d[1];
            }
        }

        // 7. Nipple status
        const s9_val = [];
        if (t.includes("everted")) s9_val.push("everted");
        if (t.includes("inverted")) s9_val.push("inverted");
        if (t.includes("ulceration")) s9_val.push("ulceration");
        if (s9_val.length > 0) data["s9_val"] = s9_val;

        // 8. Margins
        const margins = ["deep", "superior", "inferior", "medial", "lateral", "skin"];
        margins.forEach(m => {
            let mMatch = t.match(new RegExp(`([\\d.]+)\\s*cm\\s*(?:from|at)?\\s*${m}\\s*margin`));
            if (!mMatch) mMatch = t.match(new RegExp(`${m}\\s*margin\\s*(?:is)?\\s*([\\d.]+)\\s*cm`));
            if (mMatch) {
                data[`s11_${m}`] = mMatch[1];
            }
        });

        // 9. Lymph nodes
        if ((t.includes("lymph node") || t.includes("nodes")) && !t.includes("not found") && !t.includes("no lymph")) {
            data["s14_check"] = true;
            const sizes = t.match(/\b(\d+(?:\.\d+)?)\b/g);
            if (sizes && sizes.length >= 2) {
                const sizesFloat = sizes.map(Number);
                data["s14_min"] = Math.min(...sizesFloat).toString();
                data["s14_max"] = Math.max(...sizesFloat).toString();
            }
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
                    data["sections"][key] = clean;
                    break;
                }
            }
        }

        return data;
    }

    function applyLocalDataToForm(data) {
        function setVal(selector, val) {
            const el = document.querySelector(selector);
            if (el && !el.hasAttribute('data-manual')) el.value = val || '';
        }
        function setCheck(selector, isChecked) {
            const el = document.querySelector(selector);
            if (el && !el.hasAttribute('data-manual')) el.checked = isChecked;
        }

        // Reset check status for all checkboxes / radios first (only if not manual)
        document.querySelectorAll('.patho-form input[type="checkbox"], .patho-form input[type="radio"]').forEach(el => {
            if (!el.hasAttribute('data-manual')) el.checked = false;
        });

        // 1. Surgical Number
        if (data.s0_surgical_no) {
            setVal('[name="s0_surgical_no"]', data.s0_surgical_no);
        }
        // 2. Side
        if (data.s1_side) {
            setCheck(`[name="s1_side"][value="${data.s1_side}"]`, true);
        }
        // 3. Procedure
        if (data.s2_proc) {
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
            setCheck(`[name="s10_grammar"][value="${data.s10_grammar || 'is a'}"]`, true);
            if (data.s10_inf_dims) {
                setVal('[name="s10_inf_dims_0"]', data.s10_inf_dims[0]);
                setVal('[name="s10_inf_dims_1"]', data.s10_inf_dims[1]);
                setVal('[name="s10_inf_dims_2"]', data.s10_inf_dims[2]);
            }
        }
        // Margins
        const margins = ["deep", "superior", "inferior", "medial", "lateral", "skin"];
        margins.forEach(m => {
            if (data[`s11_${m}`]) {
                setVal(`[name="s11_${m}"]`, data[`s11_${m}`]);
            }
        });
        // Lymph nodes
        if (data.s14_check) {
            setCheck('[name="s14_check"]', true);
            if (data.s14_min) setVal('[name="s14_min"]', data.s14_min);
            if (data.s14_max) setVal('[name="s14_max"]', data.s14_max);
        }
        // Sections
        if (data.sections) {
            for (const [key, code] of Object.entries(data.sections)) {
                setVal(`[name="${key}"]`, code);
            }
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

        // 1. Compare Tumor dimensions with Specimen dimensions
        const specX = getFloatVal('s3_dims_0');
        const specY = getFloatVal('s3_dims_1');
        const specZ = getFloatVal('s3_dims_2');
        const tumorX = getFloatVal('s10_inf_dims_0');
        const tumorY = getFloatVal('s10_inf_dims_1');
        const tumorZ = getFloatVal('s10_inf_dims_2');

        const specMax = Math.max(specX, specY, specZ);
        const tumorMax = Math.max(tumorX, tumorY, tumorZ);

        if (tumorMax > 0 && specMax > 0 && tumorMax > specMax) {
            warnings.push(`ขนาดก้อนมะเร็งใหญ่สุด (${tumorMax} cm) มีขนาดใหญ่กว่าขนาดชิ้นเนื้อเต้านมที่ตัดมา (${specMax} cm) ซึ่งขัดแย้งทางกายภาพ`);
        }

        // 2. Check MRM procedure completeness (Modified Radical Mastectomy)
        const isModified = document.querySelector('[name="s2_proc"][value="modified"]')?.checked;
        const axillaryCheck = document.querySelector('[name="s4_check"]')?.checked;
        const lymphCheck = document.querySelector('[name="s14_check"]')?.checked;

        if (isModified) {
            if (!axillaryCheck && !lymphCheck) {
                warnings.push(`แจ้งเตือน: เลือกการผ่าตัดแบบ MRM แต่ยังไม่ได้ติ๊กเลือก "Axillary Content" หรือ "Sentinel Lymph Node" ของชิ้นเนื้อรักแร้`);
            }
        }

        // Display warnings in the UI warning box
        const warnBox = document.getElementById('clinical-warning-box');
        const warnText = document.getElementById('clinical-warning-text');
        
        if (warnBox && warnText) {
            if (warnings.length > 0) {
                warnText.innerHTML = warnings.join('<br>');
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
            }, 300);
        });
    }
});