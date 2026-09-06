document.addEventListener('DOMContentLoaded', function () {
    const btnMicToggle = document.getElementById('btn-mic-toggle');
    const txtTranscription = document.getElementById('sidebar-transcription-box') || document.getElementById('transcription-text');
    const micStatusContainer = document.getElementById('sidebar-dictation-state') || document.getElementById('mic-status-container');

    let recognition;
    let isRecording = false;
    let accumulatedTranscript = '';
    let currentSessionFinal = '';
    let serverExtractDebounceTimer = null;
    let lastExtractedText = '';

    if (txtTranscription) {
        txtTranscription.addEventListener('input', function () {
            accumulatedTranscript = txtTranscription.value;
            currentSessionFinal = '';
        });
    }

    // Debounced Backend NLP Extractor fallback (/api/extract)
    function requestBackendExtraction(textToExtract) {
        if (!textToExtract || textToExtract.trim().length < 5) return;
        clearTimeout(serverExtractDebounceTimer);
        serverExtractDebounceTimer = setTimeout(() => {
            fetch('/api/extract', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text: textToExtract })
            })
            .then(res => res.json())
            .then(result => {
                if (result && result.success && result.data) {
                    applyLocalDataToForm(result.data);
                    if (typeof validateFormData === 'function') validateFormData();
                }
            })
            .catch(err => {
                console.log("Backend extraction notice:", err);
            });
        }, 750);
    }

    // --- New System Variables ---
    let isCameraRunning = false;
    let cameraInstance = null;
    let mediaRecorder = null;
    let audioChunks = [];
    let activeAudioStream = null;
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

    // --- Speech Recognition Language Engine (Default to English en-US per user instruction) ---
    let currentMicLang = 'en-US';
    localStorage.setItem('patho_mic_lang', 'en-US');

    function updateMicLangUI() {
        const btn = document.getElementById('btn-mic-lang-toggle');
        const label = document.getElementById('mic-lang-label');
        if (!btn || !label) return;
        if (currentMicLang === 'th-TH') {
            label.textContent = 'TH (ไทย)';
            btn.className = 'btn-lang-badge lang-th';
            btn.title = 'ภาษาพูดปัจจุบัน: ไทย (th-TH) - แตะเพื่อสลับเป็น English';
        } else {
            label.textContent = 'EN (Eng)';
            btn.className = 'btn-lang-badge lang-en';
            btn.title = 'Current Speech Language: English (en-US) - Tap to switch to Thai';
        }
    }

    const btnMicLangToggle = document.getElementById('btn-mic-lang-toggle');
    if (btnMicLangToggle) {
        btnMicLangToggle.addEventListener('click', function () {
            currentMicLang = (currentMicLang === 'th-TH') ? 'en-US' : 'th-TH';
            localStorage.setItem('patho_mic_lang', currentMicLang);
            updateMicLangUI();
            if (recognition) {
                recognition.lang = currentMicLang;
                if (isRecording) {
                    try { recognition.stop(); } catch(e) {}
                    setTimeout(() => {
                        if (isRecording) {
                            try { recognition.start(); } catch(e) {}
                        }
                    }, 200);
                }
            }
        });
        updateMicLangUI();
    }

    // --- Text-to-Speech (TTS) & Hands-Free Feedback Engine ---
    let isVoiceFeedbackEnabled = true;
    const btnHandsfreeToggle = document.getElementById('btn-handsfree-toggle');

    function speakFeedback(text, lang = (currentMicLang === 'th-TH' ? 'th-TH' : 'en-US')) {
        if (!isVoiceFeedbackEnabled) return;
        if ('speechSynthesis' in window) {
            try {
                window.speechSynthesis.cancel();
                const utterance = new SpeechSynthesisUtterance(text);
                utterance.lang = lang;
                utterance.rate = 1.05;
                utterance.pitch = 1.0;
                window.speechSynthesis.speak(utterance);
            } catch(ttsErr) {
                console.warn("TTS Error:", ttsErr);
            }
        }
    }

    if (btnHandsfreeToggle) {
        btnHandsfreeToggle.addEventListener('click', function () {
            isVoiceFeedbackEnabled = !isVoiceFeedbackEnabled;
            if (isVoiceFeedbackEnabled) {
                btnHandsfreeToggle.style.backgroundColor = '#28a745';
                btnHandsfreeToggle.style.color = 'white';
                btnHandsfreeToggle.innerHTML = '<i class="fas fa-volume-up"></i> เสียงตอบรับ: ON';
                speakFeedback('เปิดระบบเสียงตอบรับเรียบร้อยแล้ว');
            } else {
                btnHandsfreeToggle.style.backgroundColor = '#7f8c8d';
                btnHandsfreeToggle.style.color = 'white';
                btnHandsfreeToggle.innerHTML = '<i class="fas fa-volume-mute"></i> เสียงตอบรับ: OFF';
            }
        });
    }

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

    function updateHandsFreeBadge(statusText, dotColor='#22c55e', pulse=false) {
        const badgeText = document.getElementById('mic-status-text');
        const statusDot = document.getElementById('mic-status-dot');
        if (badgeText) badgeText.innerText = statusText;
        if (statusDot) {
            statusDot.style.backgroundColor = dotColor;
        }
    }

    function updateGestureBadge(statusText, dotColor='#9ca3af') {
        const badgeText = document.getElementById('gesture-status-text');
        const statusDot = document.getElementById('gesture-status-dot');
        if (badgeText) badgeText.innerText = statusText;
        if (statusDot) {
            statusDot.style.backgroundColor = dotColor;
        }
    }

    if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        recognition = new SpeechRecognition();
        recognition.continuous = true;
        recognition.interimResults = true;
        recognition.lang = currentMicLang;

        recognition.onstart = function () {
            const wasAlreadyRecording = isRecording;
            isRecording = true;
            if (!wasAlreadyRecording) {
                playAudioChime('start');
            }
            updateHandsFreeBadge('Mic: Listening...', '#22c55e', true);

            if (btnMicToggle) {
                btnMicToggle.innerHTML = '<span class="btn-dot-red"></span> Stop';
                btnMicToggle.classList.add('active');
            }

            const micCircle = document.getElementById('mic-pulse-circle');
            if (micCircle) micCircle.classList.add('recording');

            const statusLabel = document.getElementById('sidebar-dictation-state');
            if (statusLabel) statusLabel.innerText = 'Dictating...';
            if (micStatusContainer) micStatusContainer.innerText = 'Dictating...';
        };

        recognition.onend = function () {
            if (currentSessionFinal) {
                accumulatedTranscript = accumulatedTranscript 
                    ? (accumulatedTranscript + ' ' + currentSessionFinal) 
                    : currentSessionFinal;
                currentSessionFinal = '';
            }

            if (isRecording) {
                // If it ended but isRecording is still true, it was a silence timeout.
                // Use a short delay for iPadOS/Safari audio engine cleanup before auto-restart
                setTimeout(() => {
                    if (isRecording) {
                        try {
                            recognition.lang = currentMicLang;
                            recognition.start();
                            if (micStatusContainer) {
                                micStatusContainer.innerText = 'Dictating...';
                            }
                        } catch (e) {
                            console.log("Auto-restart speech recognition retry:", e);
                        }
                    }
                }, 150);
            } else {
                playAudioChime('stop');
                updateHandsFreeBadge('Mic: Ready', '#22c55e', false);
                if (btnMicToggle) {
                    btnMicToggle.innerHTML = '<span class="btn-dot-red"></span> Record';
                    btnMicToggle.classList.remove('active');
                    btnMicToggle.style.backgroundColor = '';
                }

                const micCircle = document.getElementById('mic-pulse-circle');
                if (micCircle) micCircle.classList.remove('recording');

                if (micStatusContainer) micStatusContainer.innerText = 'Ready';
            }
        };

        recognition.onresult = function (event) {
            let sessionFinal = '';
            let sessionInterim = '';

            for (let i = 0; i < event.results.length; ++i) {
                if (event.results[i].isFinal) {
                    sessionFinal += event.results[i][0].transcript + ' ';
                } else {
                    sessionInterim += event.results[i][0].transcript;
                }
            }
            currentSessionFinal = sessionFinal.trim();

            let combinedBase = accumulatedTranscript;
            if (currentSessionFinal) {
                combinedBase = combinedBase ? (combinedBase + ' ' + currentSessionFinal) : currentSessionFinal;
            }
            const totalText = (combinedBase + (sessionInterim ? ' ' + sessionInterim : '')).trim();

            // Check for voice commands
            const checkText = totalText.toLowerCase().trim();

            // 1. Voice Command: Reset / Clear Form
            if (checkText.endsWith("clear all") || checkText.endsWith("reset form") || checkText.endsWith("ล้างข้อมูล") || checkText.endsWith("เริ่มเคสใหม่") || checkText.endsWith("ล้างฟอร์ม")) {
                accumulatedTranscript = '';
                currentSessionFinal = '';
                lastExtractedText = '';
                playAudioChime('stop');
                updateHandsFreeBadge('Form Reset', '#f39c12', true);
                if (txtTranscription) txtTranscription.value = "";
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

            // 2.1 Voice Command: Capture Photo (ถ่ายภาพ / ถ่ายรูป)
            if (checkText.endsWith("ถ่ายภาพ") || checkText.endsWith("ถ่ายรูป") || checkText.endsWith("take photo") || checkText.endsWith("capture photo")) {
                playAudioChime('success');
                updateHandsFreeBadge('Photo Taken', '#3b82f6', true);
                speakFeedback("ถ่ายภาพชิ้นเนื้อเรียบร้อยแล้ว");
                captureSpecimenPhoto();
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
                if (typeof stopRecordingSession === 'function') {
                    stopRecordingSession();
                } else {
                    isRecording = false;
                    try { recognition.stop(); } catch(e) {}
                }
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
            const latestSpokenChunk = normalizeText(sessionInterim || sessionFinal);

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

            // Instant Client-Side Extraction on text change
            if (normText !== lastExtractedText) {
                lastExtractedText = normText;
                const extracted = parseTextLocally(normText);
                applyLocalDataToForm(extracted);
                if (typeof validateFormData === 'function') validateFormData();
            }

            // Debounced Backend NLP Extraction Fallback for complete parity
            requestBackendExtraction(totalText);

            if (micStatusContainer) {
                if (sessionInterim) {
                    micStatusContainer.innerHTML = '<i class="fas fa-wave-square" style="color:#e67e22;"></i> กำลังพูด: <span style="color:#333;">' + sessionInterim + '</span>';
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

            stopRecordingSession();

            if (event.error === 'not-allowed') {
                showError("ไม่อนุญาตให้ใช้ไมโครโฟน (Not Allowed). กรุณากด 'Allow' ที่แถบ URL หรือตรวจสอบการตั้งค่า");
            } else if (event.error === 'network') {
                showError("เกิดข้อผิดพลาดเครือข่าย (Network). ตรวจสอบอินเทอร์เน็ต หรือหากใช้ Chrome ปัญหาอาจเกิดจากการไม่ได้ใช้ HTTPS");
            } else {
                showError("ข้อผิดพลาด: " + event.error);
            }
        };

        async function stopRecordingSession() {
            if (!isRecording && (!mediaRecorder || mediaRecorder.state === 'inactive')) return;
            isRecording = false; // Set to false first to tell onend not to auto-restart
            if (currentSessionFinal) {
                accumulatedTranscript = accumulatedTranscript 
                    ? (accumulatedTranscript + ' ' + currentSessionFinal) 
                    : currentSessionFinal;
                currentSessionFinal = '';
            }
            try { recognition.stop(); } catch(e) {}
            if (mediaRecorder && mediaRecorder.state !== 'inactive') {
                try { mediaRecorder.stop(); } catch(e) {}
            }
            if (typeof stopAudioWaveformVisualizer === 'function') {
                stopAudioWaveformVisualizer();
            }
            playAudioChime('stop');
            updateHandsFreeBadge('Mic: Ready', '#22c55e', false);
            if (btnMicToggle) {
                btnMicToggle.innerHTML = '<span class="btn-dot-red"></span> Record';
                btnMicToggle.classList.remove('active');
                btnMicToggle.style.backgroundColor = '';
            }
            const micCircle = document.getElementById('mic-pulse-circle');
            if (micCircle) micCircle.classList.remove('recording');
            const statusLabel = document.getElementById('sidebar-dictation-state');
            if (statusLabel) statusLabel.innerText = 'Ready';
            if (micStatusContainer) micStatusContainer.innerText = 'Ready';
        }
        window.stopRecordingSession = stopRecordingSession;

        async function startRecordingSession() {
            // 1. Acquire active microphone audio stream
            if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
                try {
                    activeAudioStream = await navigator.mediaDevices.getUserMedia({
                        audio: {
                            echoCancellation: true,
                            noiseSuppression: true,
                            autoGainControl: true
                        }
                    });
                } catch(micErr) {
                    showError("กรุณากด 'อนุญาต (Allow)' ไมโครโฟนในป๊อปอัปของเบราว์เซอร์");
                    return;
                }
            }

            // 2. Setup simultaneous physical MediaRecorder
            if (activeAudioStream && typeof MediaRecorder !== 'undefined') {
                try {
                    audioChunks = [];
                    let mimeType = 'audio/webm;codecs=opus';
                    if (!MediaRecorder.isTypeSupported(mimeType)) {
                        if (MediaRecorder.isTypeSupported('audio/webm')) mimeType = 'audio/webm';
                        else if (MediaRecorder.isTypeSupported('audio/mp4')) mimeType = 'audio/mp4';
                        else mimeType = '';
                    }

                    mediaRecorder = mimeType ? new MediaRecorder(activeAudioStream, { mimeType }) : new MediaRecorder(activeAudioStream);
                    
                    mediaRecorder.ondataavailable = function(e) {
                        if (e.data && e.data.size > 0) {
                            audioChunks.push(e.data);
                        }
                    };

                    mediaRecorder.onstop = async function() {
                        try {
                            if (activeAudioStream) {
                                activeAudioStream.getTracks().forEach(t => t.stop());
                                activeAudioStream = null;
                            }

                            if (audioChunks.length > 0) {
                                const finalMime = mediaRecorder.mimeType || 'audio/webm';
                                const audioBlob = new Blob(audioChunks, { type: finalMime });
                                const localAudioUrl = URL.createObjectURL(audioBlob);

                                // Immediately show and update sidebar audio player
                                const sidebarAudioBox = document.getElementById('sidebar-audio-playback-container');
                                const sidebarPlayer = document.getElementById('sidebar-audio-player');
                                if (sidebarPlayer) {
                                    sidebarPlayer.src = localAudioUrl;
                                    sidebarPlayer.load();
                                }
                                if (sidebarAudioBox) {
                                    sidebarAudioBox.style.display = 'flex';
                                }

                                if (micStatusContainer) {
                                    micStatusContainer.innerHTML = '<span style="color:#2563eb;"><i class="fas fa-spinner fa-spin"></i> กำลังบันทึกไฟล์เสียง...</span>';
                                }

                                const formData = new FormData();
                                let ext = 'webm';
                                if (finalMime.includes('mp4')) ext = 'm4a';
                                else if (finalMime.includes('ogg')) ext = 'ogg';
                                else if (finalMime.includes('wav')) ext = 'wav';

                                formData.append('audio', audioBlob, `mic_record_${Date.now()}.${ext}`);

                                const uploadRes = await fetch('/api/upload_audio', {
                                    method: 'POST',
                                    body: formData
                                });
                                const uploadData = await uploadRes.json();
                                if (uploadData.success && uploadData.audio_filename) {
                                    const now = new Date();
                                    const timeStr = now.getHours().toString().padStart(2, '0') + ':' + now.getMinutes().toString().padStart(2, '0');
                                    const clipNumber = currentAudioClips.length + 1;
                                    const audioUrl = uploadData.audio_url || (uploadData.audio_filename.startsWith('http') ? uploadData.audio_filename : `/uploads/${encodeURIComponent(uploadData.audio_filename)}`);

                                    currentAudioClips.push({
                                        filename: uploadData.audio_filename,
                                        url: audioUrl,
                                        label: `คลิปที่ ${clipNumber}`,
                                        timestamp: timeStr
                                    });

                                    syncAudioInputs();
                                    renderAudioPlaylist(currentAudioClips.length - 1);

                                    if (micStatusContainer) {
                                        micStatusContainer.innerHTML = '<span style="color:#16a34a; font-weight:bold;"><i class="fas fa-check-circle"></i> บันทึกเสียงและถอดข้อความเรียบร้อย</span>';
                                    }
                                    if (typeof autoSaveDraft === 'function') autoSaveDraft();
                                }
                            }
                        } catch (err) {
                            console.error('[Dual-Engine Audio Save Error]', err);
                        }
                    };

                    mediaRecorder.start(1000); // Record in 1s timeslices
                    if (typeof startAudioWaveformVisualizer === 'function') {
                        startAudioWaveformVisualizer(activeAudioStream);
                    }
                } catch(recErr) {
                    console.warn("MediaRecorder init warning:", recErr);
                }
            }

            // 3. Preserve accumulated text
            if (!accumulatedTranscript && txtTranscription && txtTranscription.value.trim()) {
                accumulatedTranscript = txtTranscription.value.trim();
            }
            currentSessionFinal = '';

            // 4. Start Speech Recognition
            isRecording = true;
            playAudioChime('start');
            updateHandsFreeBadge('Mic: Listening...', '#22c55e', true);
            if (btnMicToggle) {
                btnMicToggle.innerHTML = '<span class="btn-dot-red"></span> Stop';
                btnMicToggle.classList.add('active');
            }
            const micCircle = document.getElementById('mic-pulse-circle');
            if (micCircle) micCircle.classList.add('recording');

            const statusLabel = document.getElementById('sidebar-dictation-state');
            if (statusLabel) statusLabel.innerText = 'Dictating...';
            if (micStatusContainer) micStatusContainer.innerText = 'Dictating...';

            try {
                recognition.lang = currentMicLang;
                recognition.start();
            } catch (e) {
                console.warn("Speech recognition start warning:", e);
                if (btnRecordAudio) btnRecordAudio.click();
            }
        }
        window.startRecordingSession = startRecordingSession;

        btnMicToggle.addEventListener('click', async function () {
            if (isRecording || (mediaRecorder && mediaRecorder.state === 'recording')) {
                await stopRecordingSession();
            } else {
                await startRecordingSession();
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
    const ACTION_COOLDOWN = 400; // Responsive 400ms cooldown for snappy box navigation
    let lastHandDetectedTime = 0;
    let videoFrameCounter = 0;

    let cachedVideoBounds = null;
    let cachedFeedRect = null;
    let cachedBoxRects = [];

    function updateCachedGeometry() {
        const feedBox = document.querySelector('.camera-feed-box');
        if (!feedBox) return;

        const cWidth = feedBox.clientWidth || 354;
        const cHeight = feedBox.clientHeight || 270;
        const vWidth = (videoElement && videoElement.videoWidth) ? videoElement.videoWidth : 1280;
        const vHeight = (videoElement && videoElement.videoHeight) ? videoElement.videoHeight : 720;
        const containerAspect = cWidth / cHeight;
        const videoAspect = vWidth / vHeight;

        // Cover mode: video scales to fill the container completely without black bars
        let renderW = cWidth;
        let renderH = cHeight;
        let offsetX = 0;
        let offsetY = 0;

        if (containerAspect > videoAspect) {
            // Container is wider than video: video scales to width, overflows top/bottom
            renderW = cWidth;
            renderH = cWidth / videoAspect;
            offsetY = (cHeight - renderH) / 2;
        } else {
            // Container is taller/narrower than video: video scales to height, overflows left/right
            renderH = cHeight;
            renderW = cHeight * videoAspect;
            offsetX = (cWidth - renderW) / 2;
        }

        cachedVideoBounds = {
            width: renderW,
            height: renderH,
            left: offsetX,
            top: offsetY,
            containerWidth: cWidth,
            containerHeight: cHeight
        };

        cachedFeedRect = feedBox.getBoundingClientRect();

        // The gesture overlay grid fills the entire container so buttons are spacious and easy to hit
        const gestureOverlay = document.querySelector('.gesture-controls');
        if (gestureOverlay) {
            gestureOverlay.style.position = 'absolute';
            gestureOverlay.style.left = '0px';
            gestureOverlay.style.top = '0px';
            gestureOverlay.style.width = '100%';
            gestureOverlay.style.height = '100%';
        }

        // Cache all gesture box bounding client rects to eliminate forced reflows during frame rendering
        const boxes = document.querySelectorAll('.gesture-box');
        cachedBoxRects = Array.from(boxes).map(box => ({
            box,
            rect: box.getBoundingClientRect(),
            action: box.getAttribute('data-action')
        }));
    }

    window.addEventListener('resize', updateCachedGeometry, { passive: true });
    window.addEventListener('orientationchange', updateCachedGeometry, { passive: true });

    let validHandFrameCount = 0;

    function onResults(results) {
        if (!canvasCtx || !canvasElement) return;

        canvasCtx.clearRect(0, 0, canvasElement.width, canvasElement.height);

        const gestureOverlay = document.querySelector('.gesture-controls');
        const btnCameraGrid = document.getElementById('btn-camera-grid');

        if (!cachedVideoBounds || cachedBoxRects.length === 0) {
            updateCachedGeometry();
        }

        // Strict Hand Validation:
        // Filter out false positives caused by clothing folds, wrinkles, face/neck skin, or background clutter.
        let validLandmarks = null;
        if (results.multiHandLandmarks && results.multiHandLandmarks.length > 0) {
            const candidateLandmarks = results.multiHandLandmarks[0];
            const handedness = (results.multiHandedness && results.multiHandedness[0]) || null;
            const handConfidence = handedness ? handedness.score : 1.0;

            // 1. Hand Scale Check: Measure span from wrist (0) to middle finger knuckle (9)
            const wrist = candidateLandmarks[0];
            const middleMCP = candidateLandmarks[9];
            const handScale = Math.hypot(middleMCP.x - wrist.x, middleMCP.y - wrist.y);

            // 2. Reject noise:
            // - Reject if confidence score is low (< 0.70)
            // - Reject if hand scale is tiny (< 0.085 of frame, representing distant objects or clothing folds)
            if (handConfidence >= 0.70 && handScale >= 0.085) {
                validLandmarks = candidateLandmarks;
            }
        }

        if (validLandmarks) {
            validHandFrameCount++;
        } else {
            validHandFrameCount = 0;
        }

        // Require at least 2 consecutive valid frames to eliminate 1-frame transient noise/flicker
        if (validLandmarks && validHandFrameCount >= 2) {
            lastHandDetectedTime = Date.now();
            updateGestureBadge('Gesture: Active', '#22c55e');
            if (gestureOverlay) {
                gestureOverlay.classList.add('visible');
            }
            if (btnCameraGrid) {
                btnCameraGrid.classList.add('active');
            }
            canvasCtx.save();
            if (currentFacingMode === 'user') {
                canvasCtx.translate(canvasElement.width, 0);
                canvasCtx.scale(-1, 1);
            }
            if (typeof drawConnectors === 'function' && typeof HAND_CONNECTIONS !== 'undefined') {
                drawConnectors(canvasCtx, validLandmarks, HAND_CONNECTIONS, { color: '#00f0ff', lineWidth: 3 });
            }
            if (typeof drawLandmarks === 'function') {
                drawLandmarks(canvasCtx, validLandmarks, { color: '#ffffff', fillColor: '#00f0ff', lineWidth: 1, radius: 4 });
            }
            detectGesture(validLandmarks);
            canvasCtx.restore();
        } else {
            // Hand not detected: clean up hover states immediately
            for (let i = 0; i < cachedBoxRects.length; i++) {
                cachedBoxRects[i].box.classList.remove('hovered');
            }
            smoothCursorX = null;
            smoothCursorY = null;
            lockedTargetBox = null;
            isPinchState = false;
            hasClickedThisPinch = false;
            pinchFrameCount = 0;

            if (Date.now() - lastHandDetectedTime > 1200) {
                updateGestureBadge('Gesture: No Hand', '#9ca3af');
                if (gestureOverlay && !gestureOverlay.hasAttribute('data-manual-keep')) {
                    gestureOverlay.classList.remove('visible');
                    if (btnCameraGrid) {
                        btnCameraGrid.classList.remove('active');
                    }
                }
            }
        }
    }

    let smoothCursorX = null;
    let smoothCursorY = null;

    // Gesture control state machine: STRICT PINCH-ONLY (Index finger + Thumb)
    let isPinchState = false;
    let hasClickedThisPinch = false;
    let pinchFrameCount = 0;
    let lockedTargetBox = null;

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
        const wrist = landmarks[0];
        const middleMCP = landmarks[9];

        // Hand scale to normalize pinch distance across various camera distances
        const handScale = Math.hypot(middleMCP.x - wrist.x, middleMCP.y - wrist.y) || 0.25;
        const pinchDistance = Math.hypot(thumbTip.x - indexTip.x, thumbTip.y - indexTip.y);
        const normalizedPinch = pinchDistance / handScale;

        // Strict pinch detection with Schmitt trigger hysteresis:
        // - To engage pinch: index and thumb tips must actually touch (< 0.22)
        // - To disengage pinch: fingers must open back up (> 0.32)
        const PINCH_START_THRESH = 0.22;
        const PINCH_RELEASE_THRESH = 0.32;

        if (!isPinchState) {
            if (normalizedPinch < PINCH_START_THRESH || pinchDistance < 0.042) {
                pinchFrameCount++;
                if (pinchFrameCount >= 2) { // Must hold for 2 consecutive frames to eliminate camera noise
                    isPinchState = true;
                    hasClickedThisPinch = false;
                }
            } else {
                pinchFrameCount = 0;
            }
        } else {
            if (normalizedPinch > PINCH_RELEASE_THRESH && pinchDistance > 0.055) {
                // User opened hand: allow subsequent clicks
                isPinchState = false;
                hasClickedThisPinch = false;
                pinchFrameCount = 0;
            }
        }

        // Use index finger tip as the pointer (or midpoint when pinching to keep cursor steady)
        const rawX = isPinchState ? (thumbTip.x + indexTip.x) / 2 : indexTip.x;
        const rawY = isPinchState ? (thumbTip.y + indexTip.y) / 2 : indexTip.y;

        // Adaptive velocity filter: Zero lag when moving, smooth stability when hovering
        if (smoothCursorX === null) {
            smoothCursorX = rawX;
            smoothCursorY = rawY;
        } else {
            const moveSpeed = Math.hypot(rawX - smoothCursorX, rawY - smoothCursorY);
            // Dynamic alpha: fast movements get alpha ~0.88 (instant tracking), hovering gets alpha ~0.50 (anti-jitter)
            const dynamicAlpha = Math.min(0.88, Math.max(0.50, 0.50 + (moveSpeed * 3.5)));
            smoothCursorX = smoothCursorX * (1 - dynamicAlpha) + rawX * dynamicAlpha;
            smoothCursorY = smoothCursorY * (1 - dynamicAlpha) + rawY * dynamicAlpha;
        }

        // Map smoothed cursor to physical screen coordinates on the rendered video frame
        if (!cachedVideoBounds || !cachedFeedRect) {
            updateCachedGeometry();
        }
        const bounds = cachedVideoBounds;
        const feedRect = cachedFeedRect;

        const cursorX_norm = (currentFacingMode === 'user') ? (1 - smoothCursorX) : smoothCursorX;
        const cursorY_norm = smoothCursorY;

        const rawClientX = feedRect.left + bounds.left + (cursorX_norm * bounds.width);
        const rawClientY = feedRect.top + bounds.top + (cursorY_norm * bounds.height);
        const clientX = Math.max(feedRect.left + 2, Math.min(feedRect.right - 2, rawClientX));
        const clientY = Math.max(feedRect.top + 2, Math.min(feedRect.bottom - 2, rawClientY));

        // Sticky target magnetism (Hysteresis): expands active box by 12px to prevent accidental jumping
        let newTargetBox = null;
        const STICKY_MARGIN = 12;

        if (lockedTargetBox) {
            const item = cachedBoxRects.find(i => i.box === lockedTargetBox);
            if (item) {
                const r = item.rect;
                if (clientX >= (r.left - STICKY_MARGIN) && clientX <= (r.right + STICKY_MARGIN) &&
                    clientY >= (r.top - STICKY_MARGIN) && clientY <= (r.bottom + STICKY_MARGIN)) {
                    newTargetBox = lockedTargetBox;
                }
            }
        }

        if (!newTargetBox) {
            for (let i = 0; i < cachedBoxRects.length; i++) {
                const item = cachedBoxRects[i];
                const r = item.rect;
                if (clientX >= r.left && clientX <= r.right &&
                    clientY >= r.top && clientY <= r.bottom) {
                    newTargetBox = item.box;
                    break;
                }
            }
        }

        const now = Date.now();
        if (newTargetBox !== lockedTargetBox) {
            lockedTargetBox = newTargetBox;
        }

        // Update hover visual classes on DOM
        for (let i = 0; i < cachedBoxRects.length; i++) {
            const b = cachedBoxRects[i].box;
            if (b === newTargetBox) {
                if (!b.classList.contains('hovered')) b.classList.add('hovered');
            } else {
                if (b.classList.contains('hovered')) b.classList.remove('hovered');
            }
        }

        // STRICT PINCH-ONLY TRIGGER:
        // Clicks ONLY when index finger and thumb physically touch each other (Pinch).
        // Fires EXACTLY ONCE per physical pinch down (Single-Click Latch).
        // User MUST open fingers apart before another click can occur.
        // Hovering / holding still will NEVER auto-click.
        if (isPinchState && !hasClickedThisPinch && newTargetBox && (now - lastActionTime > ACTION_COOLDOWN)) {
            hasClickedThisPinch = true; // Lock until user explicitly opens fingers
            lastActionTime = now;

            newTargetBox.classList.add('active');
            setTimeout(() => newTargetBox.classList.remove('active'), 250);

            playGestureChime();
            const action = newTargetBox.getAttribute('data-action');
            triggerAction(action);

            updateGestureBadge('Pinch: ' + action, '#22c55e');
            setTimeout(() => {
                if (isCameraRunning) updateGestureBadge('Gesture: Active', '#22c55e');
            }, 600);
        }

        // Visual indicator on canvas
        const cursorCanvasX = smoothCursorX * canvasElement.width;
        const cursorCanvasY = smoothCursorY * canvasElement.height;

        // Dynamic pinch ring indicator: contracts as index and thumb approach each other
        const pinchProximity = Math.max(0, Math.min(1, 1 - (normalizedPinch / 0.40)));
        const baseRadius = 24 - (pinchProximity * 14);

        canvasCtx.beginPath();
        canvasCtx.arc(cursorCanvasX, cursorCanvasY, baseRadius, 0, 2 * Math.PI);
        canvasCtx.lineWidth = isPinchState ? 4 : (newTargetBox ? 2.5 : 1.5);
        canvasCtx.strokeStyle = isPinchState ? "#22c55e" : (newTargetBox ? "#00f0ff" : "rgba(255, 255, 255, 0.65)");
        canvasCtx.stroke();

        // Connective ray between thumb and index finger tips when close, visually showing pinch readiness
        const thumbCanvasX = thumbTip.x * canvasElement.width;
        const thumbCanvasY = thumbTip.y * canvasElement.height;
        const indexCanvasX = indexTip.x * canvasElement.width;
        const indexCanvasY = indexTip.y * canvasElement.height;

        if (pinchProximity > 0.35) {
            canvasCtx.beginPath();
            canvasCtx.moveTo(thumbCanvasX, thumbCanvasY);
            canvasCtx.lineTo(indexCanvasX, indexCanvasY);
            canvasCtx.lineWidth = isPinchState ? 3.5 : 1.5;
            canvasCtx.strokeStyle = isPinchState ? "#22c55e" : "rgba(0, 240, 255, 0.6)";
            canvasCtx.stroke();
        }

        // Center pinpoint
        canvasCtx.beginPath();
        canvasCtx.arc(cursorCanvasX, cursorCanvasY, isPinchState ? 6 : 4, 0, 2 * Math.PI);
        canvasCtx.fillStyle = isPinchState ? "#22c55e" : (newTargetBox ? "#00f0ff" : "#ffffff");
        canvasCtx.fill();
    }

    // --- อัปเดตฟังก์ชันเพื่อค้นหาช่องสี่เหลี่ยม/วงกลมโดยเฉพาะ ---
    // ==========================================================================
    // Gesture Focus Engine & Active Field Highlighting
    // ==========================================================================
    let currentFocusedInputIndex = -1;

    function getFormInputs() {
        const form = document.querySelector('.patho-form') || document.querySelector('.paper-sheet');
        if (!form) {
            return Array.from(document.querySelectorAll('input:not([type="hidden"]):not([type="file"]):not([disabled]), textarea:not([disabled])'));
        }
        return Array.from(form.querySelectorAll('input:not([type="hidden"]):not([type="file"]):not([disabled]), textarea:not([disabled])'));
    }

    function getVisual(el) {
        if (!el) return null;
        if (el.type === 'checkbox' || el.type === 'radio') {
            // If inside circle-option pill, target the span pill
            const circleSpan = el.closest('.circle-option')?.querySelector('span');
            if (circleSpan) return circleSpan;

            // Otherwise target the custom checkbox visual square
            if (el.nextElementSibling && el.nextElementSibling.classList.contains('checkbox-visual')) {
                return el.nextElementSibling;
            }
            const parentVisual = el.parentElement?.querySelector('.checkbox-visual');
            if (parentVisual) return parentVisual;

            return el.parentElement; // fallback to label
        }
        return el; // text input
    }

    function getFieldLabel(input) {
        if (!input) return "";

        const name = input.name || "";
        const val = (input.value || "").toLowerCase();

        if (name === "s0_surgical_no") return "Surgical Number S (เลขตรวจชิ้นเนื้อ)";
        if (name === "s1_side") return `Side: ${val.toUpperCase()} (ข้าง${val === 'right' ? 'ขวา' : 'ซ้าย'})`;
        if (name === "s2_proc") {
            if (val === "modified") return "Procedure: Modified radical mastectomy";
            if (val === "simple") return "Procedure: Simple mastectomy";
            if (val === "other") return "Procedure: Other";
        }
        if (name === "s2_other_text") return "Procedure: Other description";
        if (name === "s3_dims_0") return "Specimen: Length (ความยาว cm)";
        if (name === "s3_dims_1") return "Specimen: Width (ความกว้าง cm)";
        if (name === "s3_dims_2") return "Specimen: Thickness (ความหนา cm)";
        if (name === "s4_check") return "With axillary content (ชิ้นเนื้อรักแร้)";
        if (name === "s4_dims_0") return "Axillary content: Length (cm)";
        if (name === "s4_dims_1") return "Axillary content: Width (cm)";
        if (name === "s4_dims_2") return "Axillary content: Thickness (cm)";
        if (name === "s5_dims_0") return "Skin ellipse: Length (cm)";
        if (name === "s5_dims_1") return "Skin ellipse: Width (cm)";
        if (name === "s5_appears_normal") return "Skin: Appears normal (ผิวหนังปกติ)";
        if (name === "s6_check") return "Shows old surgical scar (รอยแผลเป็น)";
        if (name === "s7_len") return "Scar: Length (ความยาวแผล cm)";
        if (name === "s7_locs") return `Scar Location: ${val} (ตำแหน่งแผลเป็น)`;
        if (name === "s8_check") return "Shows ulceration (แผลเปื่อย)";
        if (name === "s8_dims_0") return "Ulceration: Length (cm)";
        if (name === "s8_dims_1") return "Ulceration: Width (cm)";
        if (name === "s8_locs") return `Ulceration Location: ${val} (ตำแหน่งแผลเปื่อย)`;
        if (name === "s9_val") return `Nipple: ${val} (หัวนม)`;
        if (name === "s9_ulcer_text") return "Nipple: Ulceration description";
        if (name === "s10_grammar") return `Tumor Quantifier: ${val} (ไวยากรณ์ก้อน)`;
        if (name === "s10_infiltrative") return "Mass: Infiltrative firm mass (ก้อนแทรกซึม)";
        if (name.startsWith("s10_inf_dims")) {
            const dims = ["Length", "Width", "Thickness"];
            const idx = parseInt(name.split("_").pop()) || 0;
            return `Infiltrative Mass: ${dims[idx] || ""} (cm)`;
        }
        if (name === "s10_well") return "Mass: Well-defined firm mass (ก้อนขอบชัด)";
        if (name.startsWith("s10_well_dims")) {
            const dims = ["Length", "Width", "Thickness"];
            const idx = parseInt(name.split("_").pop()) || 0;
            return `Well-defined Mass: ${dims[idx] || ""} (cm)`;
        }
        if (name === "s10_prev1") return "Mass: Previous surgical cavity (โพรงผ่าตัดเดิม)";
        if (name.startsWith("s10_prev1_dims")) {
            const dims = ["Length", "Width", "Thickness"];
            const idx = parseInt(name.split("_").pop()) || 0;
            return `Cavity: ${dims[idx] || ""} (cm)`;
        }
        if (name === "s10_prev2") return "Mass: Cavity with residual mass (โพรงเดิมมีก้อนค้าง)";
        if (name.startsWith("s10_prev2_cavity_dims")) {
            const dims = ["Length", "Width", "Thickness"];
            const idx = parseInt(name.split("_").pop()) || 0;
            return `Cavity: ${dims[idx] || ""} (cm)`;
        }
        if (name.startsWith("s10_prev2_mass_dims")) {
            const dims = ["Length", "Width", "Thickness"];
            const idx = parseInt(name.split("_").pop()) || 0;
            return `Residual Mass: ${dims[idx] || ""} (cm)`;
        }
        if (name === "s10_5_nipple") return "Location: Beneath nipple (ใต้หัวนม)";
        if (name === "s10_5_scar") return "Location: Beneath scar (ใต้แผลเป็น)";
        if (name === "s10_5_central") return "Location: Central portion (ส่วนกลางเต้านม)";
        if (name === "s10_5_quadrant_check") return "Location: In quadrant (ในควอดแรนต์)";
        if (name === "s10_5_quadrant_vals") return `Quadrant: ${val} (ควอดแรนต์)`;
        if (name === "s10_5_other_check") return "Location: Other (ตำแหน่งอื่นๆ)";
        if (name === "s10_5_other") return "Location: Other description";
        if (name === "s11_deep") return "Margin: Deep (ขอบลึก cm)";
        if (name === "s11_superior") return "Margin: Superior (ขอบบน cm)";
        if (name === "s11_inferior") return "Margin: Inferior (ขอบล่าง cm)";
        if (name === "s11_medial") return "Margin: Medial (ขอบใน cm)";
        if (name === "s11_lateral") return "Margin: Lateral (ขอบนอก cm)";
        if (name === "s11_skin") return "Margin: From skin (ห่างจากผิวหนัง cm)";
        if (name === "s12_check") return "Parenchyma fat to fibrous ratio";
        if (name === "s12_val_left") return "Ratio: Fat (ส่วนไขมัน)";
        if (name === "s12_val_right") return "Ratio: Fibrous (ส่วนพังผืด)";
        if (name === "s13_type" || name === "s13_unremarkable") return `Remaining tissue: ${val || "unremarkable"}`;
        if (name === "s13_text") return "Remaining tissue description";
        if (name === "s14_check") return "Lymph nodes (ต่อมน้ำเหลือง)";
        if (name === "s14_min") return "Lymph node: Min diameter (cm)";
        if (name === "s14_max") return "Lymph node: Max diameter (cm)";
        if (name.startsWith("sec_")) {
            const secKey = name.replace("sec_", "").replace(/_/g, " ");
            return `Section: ${secKey}`;
        }
        if (name === "footer_prosecutor") return "Prosecutor (ผู้ตรวจชิ้นเนื้อ)";
        if (name === "footer_date") return "Date (วันที่)";

        const label = input.closest('label');
        if (label) {
            const text = label.textContent.trim().replace(/\s+/g, ' ');
            if (text) return text.substring(0, 40);
        }
        return input.placeholder || name || "Form Box";
    }

    function updateActiveBoxHUD(input) {
        const hud = document.getElementById('active-box-hud');
        const hudTitle = document.getElementById('hud-box-name');
        if (!hud || !hudTitle) return;

        if (!input) {
            hud.classList.remove('has-focus');
            hudTitle.textContent = 'ยังไม่ได้เลือกช่อง (คลิกหรือ NEXT BOX)';
            return;
        }

        hud.classList.add('has-focus');
        const label = getFieldLabel(input);
        hudTitle.textContent = label;

        const subtext = document.querySelector('.dictation-subtext');
        if (subtext) {
            subtext.innerHTML = `ช่องปัจจุบัน: <strong style="color: #2563eb;">${label}</strong>`;
        }
    }

    function updateFloatingFocusBadge(visual, input) {
        const paper = document.querySelector('.paper-sheet');
        if (!paper || !visual) return;

        let badge = document.getElementById('gesture-focus-badge');
        if (!badge) {
            badge = document.createElement('div');
            badge.id = 'gesture-focus-badge';
            badge.className = 'gesture-focus-badge';
            paper.appendChild(badge);
        }

        const paperRect = paper.getBoundingClientRect();
        const visualRect = visual.getBoundingClientRect();
        const zoomScale = parseFloat(paper.getAttribute('data-zoom') || '1') || 1;

        const relTop = (visualRect.top - paperRect.top) / zoomScale;
        const relLeft = (visualRect.left - paperRect.left) / zoomScale;
        const visualWidth = visualRect.width / zoomScale;

        const label = getFieldLabel(input);
        badge.innerHTML = `<span class="badge-dot"></span><span>${label}</span><div class="badge-arrow"></div>`;

        badge.style.top = `${Math.max(6, relTop - 34)}px`;
        badge.style.left = `${relLeft + (visualWidth / 2)}px`;
        badge.classList.add('visible');
    }

    function applyGestureFocus(target) {
        if (!target) return;
        const inputs = getFormInputs();
        const idx = inputs.indexOf(target);
        if (idx !== -1) {
            currentFocusedInputIndex = idx;
        }

        // 1. Remove previous gesture focus
        document.querySelectorAll('.gesture-focus').forEach(el => el.classList.remove('gesture-focus'));
        document.querySelectorAll('.active-gesture-row').forEach(el => el.classList.remove('active-gesture-row'));

        // 2. Focus native target WITHOUT opening mobile/tablet virtual keyboard
        if (document.activeElement && document.activeElement !== target && typeof document.activeElement.blur === 'function') {
            document.activeElement.blur();
        }

        const prevInputMode = target.getAttribute('inputmode');
        // Setting inputmode='none' instructs mobile/tablet browsers NOT to summon the software keyboard
        target.setAttribute('inputmode', 'none');
        try {
            target.focus({ preventScroll: true });
        } catch (e) {}

        if (target.type === 'text' && typeof target.select === 'function') {
            try { target.select(); } catch (e) {}
        }

        // Restore normal inputmode when user physically touches or clicks the input to type
        const restoreInputMode = function() {
            if (prevInputMode !== null) {
                target.setAttribute('inputmode', prevInputMode);
            } else {
                target.removeAttribute('inputmode');
            }
            target.removeEventListener('pointerdown', restoreInputMode);
            target.removeEventListener('touchstart', restoreInputMode);
            target.removeEventListener('keydown', restoreInputMode);
        };
        target.addEventListener('pointerdown', restoreInputMode, { once: true });
        target.addEventListener('touchstart', restoreInputMode, { once: true });
        target.addEventListener('keydown', restoreInputMode, { once: true });

        // 3. Highlight visual element
        const visual = getVisual(target);
        if (visual) {
            visual.classList.add('gesture-focus');
            visual.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'nearest' });
            updateFloatingFocusBadge(visual, target);
        }

        // 4. Highlight parent form row
        const parentRow = target.closest('.form-row, .table-row, tr, .form-group');
        if (parentRow) {
            parentRow.classList.add('active-gesture-row');
        }

        // 5. Update Sidebar HUD
        updateActiveBoxHUD(target);
    }

    // Global listener: If user physically touches an input with finger/stylus, allow on-screen keyboard
    document.addEventListener('pointerdown', function(e) {
        const input = e.target;
        if (input && (input.tagName === 'INPUT' || input.tagName === 'TEXTAREA')) {
            if (input.getAttribute('inputmode') === 'none') {
                input.removeAttribute('inputmode');
            }
        }
    }, true);

    function triggerAction(action) {
        switch (action) {
            case 'CLEAR':
                let activeClear = document.activeElement;
                const inputs = getFormInputs();
                if ((!activeClear || !inputs.includes(activeClear)) && currentFocusedInputIndex !== -1) {
                    activeClear = inputs[currentFocusedInputIndex];
                }
                if (activeClear) {
                    if (activeClear.type === 'text' || activeClear.tagName === 'TEXTAREA') {
                        activeClear.value = '';
                    } else if (activeClear.type === 'checkbox' || activeClear.type === 'radio') {
                        activeClear.checked = false;
                        const parent = activeClear.parentElement;
                        if (parent && parent.classList.contains('circle-option')) {
                            const span = parent.querySelector('span');
                            if (span) span.style = "";
                        }
                    }
                    activeClear.classList.remove('low-confidence-highlight');
                    if (activeClear.nextElementSibling && activeClear.nextElementSibling.classList.contains('checkbox-visual')) {
                        activeClear.nextElementSibling.classList.remove('low-confidence-highlight');
                    }
                    updateActiveBoxHUD(activeClear);
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
                let activeSel = document.activeElement;
                const formInps = getFormInputs();
                if ((!activeSel || !formInps.includes(activeSel)) && currentFocusedInputIndex !== -1) {
                    activeSel = formInps[currentFocusedInputIndex];
                }
                if (activeSel && (activeSel.type === 'checkbox' || activeSel.type === 'radio')) {
                    activeSel.click();

                    const visualEl = getVisual(activeSel);
                    if (visualEl) {
                        visualEl.classList.add('select-success');
                        setTimeout(() => visualEl.classList.remove('select-success'), 500);
                    }
                    updateActiveBoxHUD(activeSel);
                } else if (activeSel && (activeSel.type === 'text' || activeSel.tagName === 'TEXTAREA')) {
                    if (typeof activeSel.select === 'function') activeSel.select();
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

    // Allow clicking or tapping on gesture boxes directly without stealing focus
    document.querySelectorAll('.gesture-box').forEach(box => {
        box.addEventListener('mousedown', function(e) {
            e.preventDefault();
        });
        box.addEventListener('click', function(e) {
            e.stopPropagation();
            const action = this.getAttribute('data-action');
            this.classList.add('active');
            setTimeout(() => this.classList.remove('active'), 200);
            playGestureChime();
            triggerAction(action);
        });
    });

    function moveFocusRow(direction) {
        const inputs = getFormInputs();
        if (!inputs.length) return;

        let currentIndex = currentFocusedInputIndex;
        if (currentIndex === -1 || currentIndex >= inputs.length) {
            const active = document.activeElement;
            currentIndex = inputs.indexOf(active);
        }

        if (currentIndex === -1) {
            const target = direction > 0 ? inputs[0] : inputs[inputs.length - 1];
            applyGestureFocus(target);
            return;
        }

        const current = inputs[currentIndex];
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
            applyGestureFocus(target);
        }
    }

    function moveFocus(direction) {
        const inputs = getFormInputs();
        if (!inputs.length) return;

        let currentIndex = currentFocusedInputIndex;
        if (currentIndex === -1 || currentIndex >= inputs.length) {
            const active = document.activeElement;
            currentIndex = inputs.indexOf(active);
        }

        let nextIndex = 0;
        if (currentIndex !== -1) {
            nextIndex = currentIndex + direction;
        } else {
            nextIndex = direction > 0 ? 0 : inputs.length - 1;
        }

        if (nextIndex < 0) nextIndex = inputs.length - 1;
        if (nextIndex >= inputs.length) nextIndex = 0;

        const target = inputs[nextIndex];
        applyGestureFocus(target);
    }

    // Connect form click and focus events to automatically update gesture focus
    const pathoForm = document.querySelector('.patho-form') || document.querySelector('.paper-sheet');
    if (pathoForm) {
        pathoForm.addEventListener('focusin', function(e) {
            if (e.target.matches('input, textarea')) {
                applyGestureFocus(e.target);
            }
        });
        pathoForm.addEventListener('click', function(e) {
            const target = e.target.closest('label')?.querySelector('input') || (e.target.matches('input, textarea') ? e.target : null);
            if (target) {
                applyGestureFocus(target);
            }
        });
    }

    // Keyboard navigation helper
    document.addEventListener('keydown', function(e) {
        const active = document.activeElement;
        const isTyping = active && (active.type === 'text' || active.tagName === 'TEXTAREA') && !active.readOnly;
        
        if (!isTyping) {
            if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
                e.preventDefault();
                moveFocus(1);
            } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
                e.preventDefault();
                moveFocus(-1);
            } else if (e.key === ' ' || e.key === 'Enter') {
                if (active && (active.type === 'checkbox' || active.type === 'radio')) {
                    e.preventDefault();
                    triggerAction('SELECT');
                }
            }
        }
    });

    // --- Real-time Web Audio API Waveform & VU Meter Engine ---
    let audioVisualizerCtx = null;
    let audioVisualizerAnimId = null;

    function startAudioWaveformVisualizer(mediaStream) {
        const canvas = document.getElementById('audio-waveform-canvas');
        const container = document.getElementById('live-waveform-container') || document.getElementById('active-recording-waveform');
        const vuBar = document.getElementById('audio-vu-bar') || document.getElementById('audio-vu-meter');
        const dbText = document.getElementById('audio-db-text');
        if (!canvas || !mediaStream) return;

        if (container) container.style.display = 'block';
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

                if (dbText) {
                    const rms = Math.sqrt(totalVolume / bufferLength);
                    const db = Math.round(20 * Math.log10(Math.max(1, rms)));
                    dbText.textContent = `${db} dB`;
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
        const container = document.getElementById('live-waveform-container') || document.getElementById('active-recording-waveform');
        if (container) container.style.display = 'none';
        const vuBar = document.getElementById('audio-vu-bar') || document.getElementById('audio-vu-meter');
        if (vuBar) vuBar.style.width = '0%';
        const dbText = document.getElementById('audio-db-text');
        if (dbText) dbText.textContent = '0 dB';
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
    const cameraFeedEl = document.querySelector('.camera-feed-box');
    let localVideoStream = null;
    let handsInstance = null;
    let animFrameId = null;
    let isMediaPipeBusy = false;
    let offscreenCanvas = null;
    let offscreenCtx = null;
    let currentFacingMode = 'user';

    function initMediaPipeHands() {
        if (handsInstance) return true;
        if (typeof Hands === 'undefined') {
            return false;
        }
        try {
            handsInstance = new Hands({
                locateFile: (file) => `https://cdn.jsdelivr.net/npm/@mediapipe/hands@0.4.1675469240/${file}`
            });
            handsInstance.setOptions({
                maxNumHands: 1,
                modelComplexity: 0, // 0 = Lite (Optimized for iPad & Mobile WebKit Wasm)
                minDetectionConfidence: 0.70, // 0.70 rejects background noise, clothing folds and distant artifacts
                minTrackingConfidence: 0.65  // 0.65 ensures hand remains locked on genuine hands only
            });
            handsInstance.onResults(onResults);
            console.log("MediaPipe Hands initialized successfully with Lite model.");
            return true;
        } catch (e) {
            console.warn("MediaPipe Hands init note:", e);
            return false;
        }
    }

    // Attempt init immediately and set up retry interval if library script is downloading
    if (!initMediaPipeHands()) {
        let retries = 0;
        const initInterval = setInterval(() => {
            retries++;
            if (initMediaPipeHands() || retries > 25) {
                clearInterval(initInterval);
            }
        }, 200);
    }

    async function startCameraDirectly() {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            showError("เบราว์เซอร์นี้ไม่รองรับการเปิดกล้อง หรือไม่ได้รันบน HTTPS");
            return false;
        }

        try {
            if (btnCameraToggle) {
                btnCameraToggle.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Photo';
            }

            if (!handsInstance) {
                initMediaPipeHands();
            }

            localVideoStream = await navigator.mediaDevices.getUserMedia({
                video: {
                    width: { ideal: 1280 },
                    height: { ideal: 720 },
                    frameRate: { ideal: 30, max: 30 },
                    facingMode: { ideal: currentFacingMode }
                },
                audio: false
            });

            if (videoElement) {
                videoElement.srcObject = localVideoStream;
                videoElement.muted = true;
                videoElement.playsInline = true;
                if (currentFacingMode === 'environment') {
                    videoElement.classList.add('unmirrored');
                } else {
                    videoElement.classList.remove('unmirrored');
                }
                try {
                    await videoElement.play();
                } catch (playErr) {
                    console.warn("video.play note:", playErr);
                }
            }

            isCameraRunning = true;
            const camPlaceholder = document.getElementById('camera-placeholder');
            if (camPlaceholder) camPlaceholder.style.display = 'none';
            const gestureOverlay = document.querySelector('.gesture-controls');
            if (gestureOverlay && !gestureOverlay.hasAttribute('data-manual-keep')) {
                gestureOverlay.classList.remove('visible');
            }
            if (btnCameraToggle) {
                btnCameraToggle.innerHTML = '<i class="fa-solid fa-camera"></i> Photo';
                btnCameraToggle.classList.add('active');
            }

            const badgeLeft = document.querySelector('.camera-badge-left');
            if (badgeLeft) {
                badgeLeft.textContent = currentFacingMode === 'environment' ? 'BACK CAMERA' : 'FRONT CAMERA';
            }

            const captureBtn = document.getElementById('btn-camera-capture');
            if (captureBtn) captureBtn.style.display = 'inline-flex';
            const topCaptureBtn = document.getElementById('btn-camera-top-capture');
            if (topCaptureBtn) topCaptureBtn.style.display = 'inline-flex';

            // Start Hands processing loop
            async function processVideoFrame() {
                if (!isCameraRunning) return;
                
                videoFrameCounter++;
                const isIdle = (Date.now() - lastHandDetectedTime) > 6000;

                // Dynamically sync canvas dimensions and container dimensions
                if (videoElement && videoElement.videoWidth && videoElement.videoHeight) {
                    if (canvasElement) {
                        const maxCanvasDim = 640;
                        let cW = videoElement.videoWidth;
                        let cH = videoElement.videoHeight;
                        if (cW > maxCanvasDim) {
                            cH = Math.round((cH * maxCanvasDim) / cW);
                            cW = maxCanvasDim;
                        }
                        if (canvasElement.width !== cW || canvasElement.height !== cH) {
                            canvasElement.width = cW;
                            canvasElement.height = cH;
                            updateCachedGeometry();
                        }
                    }
                    if (cameraFeedEl && !cameraFeedEl._heightApplied) {
                        const isExp = cameraFeedEl.classList.contains('camera-expanded');
                        cameraFeedEl.style.height = isExp ? '440px' : '270px';
                        cameraFeedEl.style.aspectRatio = 'auto';
                        cameraFeedEl._heightApplied = true;
                        updateCachedGeometry();
                    }
                }

                // If no hands detected for 6s, throttle MediaPipe to 15 FPS to conserve CPU/battery
                if (isIdle && (videoFrameCounter % 2 !== 0)) {
                    animFrameId = requestAnimationFrame(processVideoFrame);
                    return;
                }

                if (handsInstance && videoElement && videoElement.readyState >= 2 && !isMediaPipeBusy) {
                    isMediaPipeBusy = true;
                    try {
                        if (!offscreenCanvas) {
                            offscreenCanvas = document.createElement('canvas');
                        }
                        const vWidth = videoElement.videoWidth;
                        const vHeight = videoElement.videoHeight;
                        if (vWidth && vHeight) {
                            // Downscale video frame to optimal MediaPipe input size (max 480px)
                            // MediaPipe neural network internally uses 256x256. 
                            // Passing 480px reduces Wasm memory copy by 86% and cuts 70ms of latency!
                            const maxAiDim = 480;
                            let aiW = vWidth;
                            let aiH = vHeight;
                            if (aiW > maxAiDim || aiH > maxAiDim) {
                                if (aiW >= aiH) {
                                    aiH = Math.round((aiH * maxAiDim) / aiW);
                                    aiW = maxAiDim;
                                } else {
                                    aiW = Math.round((aiW * maxAiDim) / aiH);
                                    aiH = maxAiDim;
                                }
                            }
                            if (offscreenCanvas.width !== aiW || offscreenCanvas.height !== aiH) {
                                offscreenCanvas.width = aiW;
                                offscreenCanvas.height = aiH;
                                offscreenCtx = offscreenCanvas.getContext('2d', { willReadFrequently: true });
                            }
                            if (offscreenCtx) {
                                offscreenCtx.drawImage(videoElement, 0, 0, aiW, aiH);
                                await handsInstance.send({ image: offscreenCanvas });
                            } else {
                                await handsInstance.send({ image: videoElement });
                            }
                        }
                    } catch (sendErr) {
                        console.warn("MediaPipe frame send error:", sendErr);
                    } finally {
                        isMediaPipeBusy = false;
                    }
                }
                animFrameId = requestAnimationFrame(processVideoFrame);
            }
            processVideoFrame();

            return true;
        } catch (err) {
            console.error("Camera direct start error:", err);
            isCameraRunning = false;
            const camPlaceholder = document.getElementById('camera-placeholder');
            if (camPlaceholder) {
                camPlaceholder.style.display = 'flex';
                camPlaceholder.innerHTML = `
                    <div style="width: 44px; height: 44px; border-radius: 50%; background: rgba(239, 68, 68, 0.15); display: flex; align-items: center; justify-content: center; margin-bottom: 8px; border: 1px solid rgba(239, 68, 68, 0.4);">
                        <i class="fa-solid fa-triangle-exclamation" style="font-size: 18px; color: #ef4444;"></i>
                    </div>
                    <span style="font-size: 12.5px; font-weight: 700; color: #f87171;">ไม่สามารถเปิดกล้องได้</span>
                    <span style="font-size: 11px; color: #94a3b8; margin-top: 4px; text-align: center; max-width: 250px;">กรุณากด 'Allow' สิทธิ์กล้องในเบราว์เซอร์ แล้วคลิกที่นี่อีกครั้ง</span>
                `;
            }
            if (btnCameraToggle) {
                btnCameraToggle.innerHTML = '<i class="fa-solid fa-camera"></i> Photo';
                btnCameraToggle.classList.remove('active');
            }
            showError("ไม่สามารถเปิดกล้องได้ (" + (err.name || err.message) + "). กรุณาตรวจสอบว่าได้กด 'Allow' สิทธิ์กล้องในเบราว์เซอร์แล้ว");
            return false;
        }
    }

    function stopCameraDirectly() {
        isCameraRunning = false;
        isMediaPipeBusy = false;
        if (animFrameId) cancelAnimationFrame(animFrameId);
        if (localVideoStream) {
            localVideoStream.getTracks().forEach(t => t.stop());
            localVideoStream = null;
        }
        if (videoElement) {
            videoElement.srcObject = null;
        }
        const gestureOverlay = document.querySelector('.gesture-controls');
        if (gestureOverlay) {
            gestureOverlay.classList.remove('visible');
            gestureOverlay.removeAttribute('data-manual-keep');
        }
        const btnCameraGrid = document.getElementById('btn-camera-grid');
        if (btnCameraGrid) btnCameraGrid.classList.remove('active');
        const captureBtn = document.getElementById('btn-camera-capture');
        if (captureBtn) captureBtn.style.display = 'none';
        const topCaptureBtn = document.getElementById('btn-camera-top-capture');
        if (topCaptureBtn) topCaptureBtn.style.display = 'none';

        const camPlaceholder = document.getElementById('camera-placeholder');
        if (camPlaceholder) {
            camPlaceholder.style.display = 'flex';
            camPlaceholder.innerHTML = `
                <div class="cam-icon-circle"><i class="fa-solid fa-camera"></i></div>
                <span class="cam-prompt-text">คลิกเปิดกล้อง (Start Camera)</span>
            `;
        }
        if (btnCameraToggle) {
            btnCameraToggle.innerHTML = '<i class="fa-solid fa-camera"></i> Photo';
            btnCameraToggle.classList.remove('active');
        }
        if (canvasCtx && canvasElement) {
            canvasCtx.clearRect(0, 0, canvasElement.width, canvasElement.height);
        }
        if (cameraFeedEl) {
            cameraFeedEl._aspectRatioApplied = false;
        }
        updateGestureBadge('Gesture: Off', '#9ca3af');
    }

    if (btnCameraToggle) {
        btnCameraToggle.addEventListener('click', function() {
            if (isCameraRunning) {
                stopCameraDirectly();
            } else {
                startCameraDirectly();
            }
        });

        // Automatically start camera if user already granted permission
        if (navigator.permissions && navigator.permissions.query) {
            navigator.permissions.query({ name: 'camera' }).then(function(res) {
                if (res.state === 'granted' && !isCameraRunning) {
                    startCameraDirectly();
                }
            }).catch(function() {});
        }
    }

    const btnCameraFlip = document.getElementById('btn-camera-flip');
    if (btnCameraFlip) {
        btnCameraFlip.addEventListener('click', function(e) {
            e.stopPropagation();
            currentFacingMode = currentFacingMode === 'user' ? 'environment' : 'user';
            
            const badgeLeft = document.querySelector('.camera-badge-left');
            if (badgeLeft) {
                badgeLeft.textContent = currentFacingMode === 'environment' ? 'BACK CAMERA' : 'FRONT CAMERA';
            }

            if (isCameraRunning) {
                stopCameraDirectly();
                setTimeout(() => startCameraDirectly(), 250);
            }
        });
    }

    const btnCameraCapture = document.getElementById('btn-camera-capture');
    if (btnCameraCapture) {
        btnCameraCapture.addEventListener('click', function(e) {
            e.stopPropagation();
            captureSpecimenPhoto();
        });
    }

    const btnCameraTopCapture = document.getElementById('btn-camera-top-capture');
    if (btnCameraTopCapture) {
        btnCameraTopCapture.addEventListener('click', function(e) {
            e.stopPropagation();
            captureSpecimenPhoto();
        });
    }

    // --- Specimen Photo Gallery Engine (Multi-Photo) ---
    let currentPhotos = [];
    let currentModalPhotoIndex = 0;

    function initPhotos() {
        const hiddenPhotos = document.getElementById('hidden-photos-json');
        const hiddenPhotoData = document.getElementById('hidden-photo-data');
        if (hiddenPhotos && hiddenPhotos.value && hiddenPhotos.value.trim().startsWith('[')) {
            try {
                currentPhotos = JSON.parse(hiddenPhotos.value);
                if (!Array.isArray(currentPhotos)) currentPhotos = [];
            } catch(e) {
                currentPhotos = [];
            }
        }
        if (currentPhotos.length === 0 && hiddenPhotoData && hiddenPhotoData.value && hiddenPhotoData.value.trim().length > 20) {
            currentPhotos = [hiddenPhotoData.value.trim()];
        }
        renderPhotoGallery(0);
    }

    function syncPhotoInputs() {
        const hiddenPhotos = document.getElementById('hidden-photos-json');
        const hiddenPhotoData = document.getElementById('hidden-photo-data');
        const hiddenPhotoCleared = document.getElementById('hidden-photo-cleared');

        if (hiddenPhotos) {
            hiddenPhotos.value = JSON.stringify(currentPhotos);
        }
        if (currentPhotos.length > 0) {
            if (hiddenPhotoData) hiddenPhotoData.value = currentPhotos[0];
            if (hiddenPhotoCleared) hiddenPhotoCleared.value = 'false';
        } else {
            if (hiddenPhotoData) hiddenPhotoData.value = '';
            if (hiddenPhotoCleared) hiddenPhotoCleared.value = 'true';
        }
    }

    function renderPhotoGallery(activeIdx = 0) {
        const photoContainer = document.getElementById('specimen-photo-container');
        const countBadge = document.getElementById('photo-gallery-count');
        const previewImg = document.getElementById('specimen-preview-img');
        const galleryStrip = document.getElementById('specimen-gallery-strip');

        if (!photoContainer) return;

        if (currentPhotos.length === 0) {
            photoContainer.style.display = 'none';
            if (previewImg) previewImg.src = '';
            if (countBadge) countBadge.textContent = '0 รูป';
            if (galleryStrip) {
                galleryStrip.innerHTML = '';
                galleryStrip.style.display = 'none';
            }
            return;
        }

        photoContainer.style.display = 'block';
        if (countBadge) countBadge.textContent = `${currentPhotos.length} รูป`;

        const safeIdx = Math.max(0, Math.min(activeIdx, currentPhotos.length - 1));
        if (previewImg) {
            previewImg.src = currentPhotos[safeIdx];
        }

        const primaryPreview = document.getElementById('specimen-primary-preview');
        if (primaryPreview) {
            primaryPreview.onclick = () => openPhotoModalByIndex(safeIdx);
        }

        if (galleryStrip) {
            if (currentPhotos.length > 1) {
                galleryStrip.style.display = 'flex';
                galleryStrip.innerHTML = '';
                currentPhotos.forEach((p, idx) => {
                    const thumbItem = document.createElement('div');
                    thumbItem.className = `gallery-thumb-item ${idx === safeIdx ? 'active' : ''}`;
                    thumbItem.title = `รูปที่ ${idx + 1} (คลิกเพื่อสลับดู)`;
                    thumbItem.onclick = () => selectGalleryThumb(idx);

                    const img = document.createElement('img');
                    img.src = p;
                    img.alt = `Thumb ${idx + 1}`;

                    const badge = document.createElement('span');
                    badge.className = 'gallery-thumb-num';
                    badge.textContent = idx === 0 ? 'หลัก' : (idx + 1);

                    const delBtn = document.createElement('button');
                    delBtn.type = 'button';
                    delBtn.className = 'gallery-thumb-del';
                    delBtn.title = 'ลบรูปนี้';
                    delBtn.innerHTML = '&times;';
                    delBtn.onclick = (e) => {
                        e.stopPropagation();
                        deletePhotoAtIndex(idx);
                    };

                    thumbItem.appendChild(img);
                    thumbItem.appendChild(badge);
                    thumbItem.appendChild(delBtn);
                    galleryStrip.appendChild(thumbItem);
                });
            } else {
                galleryStrip.style.display = 'none';
                galleryStrip.innerHTML = '';
            }
        }
    }

    function selectGalleryThumb(index) {
        renderPhotoGallery(index);
    }
    window.selectGalleryThumb = selectGalleryThumb;

    function deletePhotoAtIndex(index) {
        if (index < 0 || index >= currentPhotos.length) return;
        if (confirm(`ต้องการลบรูปที่ ${index + 1} หรือไม่?`)) {
            currentPhotos.splice(index, 1);
            syncPhotoInputs();
            renderPhotoGallery(Math.max(0, index - 1));
            if (typeof autoSaveDraft === 'function') autoSaveDraft();
            showAppToast("ลบภาพถ่ายเรียบร้อยแล้ว");
        }
    }
    window.deletePhotoAtIndex = deletePhotoAtIndex;

    function openPhotoModalByIndex(index) {
        if (currentPhotos.length === 0) return;
        currentModalPhotoIndex = Math.max(0, Math.min(index, currentPhotos.length - 1));
        const modal = document.getElementById('formPhotoModal');
        const modalImg = document.getElementById('formPhotoModalImg');
        const counter = document.getElementById('formPhotoModalCounter');
        const btnPrev = document.getElementById('btnPhotoModalPrev');
        const btnNext = document.getElementById('btnPhotoModalNext');
        const downloadBtn = document.getElementById('formPhotoModalDownload');

        if (!modal || !modalImg) return;

        modalImg.src = currentPhotos[currentModalPhotoIndex];
        if (counter) {
            counter.textContent = `(รูปที่ ${currentModalPhotoIndex + 1} จาก ${currentPhotos.length})`;
        }
        if (btnPrev) {
            btnPrev.disabled = currentModalPhotoIndex <= 0;
        }
        if (btnNext) {
            btnNext.disabled = currentModalPhotoIndex >= currentPhotos.length - 1;
        }
        if (downloadBtn) {
            downloadBtn.href = currentPhotos[currentModalPhotoIndex];
            const sNo = document.querySelector('input[name="s0_surgical_no"]')?.value?.trim() || 'case';
            downloadBtn.download = `specimen_${sNo}_photo${currentModalPhotoIndex + 1}.jpg`;
        }
        modal.style.display = 'flex';
    }
    window.openPhotoModalByIndex = openPhotoModalByIndex;

    function navigatePhotoModal(step) {
        const nextIdx = currentModalPhotoIndex + step;
        if (nextIdx >= 0 && nextIdx < currentPhotos.length) {
            openPhotoModalByIndex(nextIdx);
        }
    }
    window.navigatePhotoModal = navigatePhotoModal;

    function deleteCurrentModalPhoto() {
        if (currentPhotos.length === 0) return;
        if (confirm(`ต้องการลบรูปที่ ${currentModalPhotoIndex + 1} หรือไม่?`)) {
            currentPhotos.splice(currentModalPhotoIndex, 1);
            syncPhotoInputs();
            if (currentPhotos.length === 0) {
                closeFormPhotoModal();
                renderPhotoGallery(0);
            } else {
                const nextIdx = Math.min(currentModalPhotoIndex, currentPhotos.length - 1);
                renderPhotoGallery(nextIdx);
                openPhotoModalByIndex(nextIdx);
            }
            if (typeof autoSaveDraft === 'function') autoSaveDraft();
            showAppToast("ลบภาพถ่ายเรียบร้อยแล้ว");
        }
    }
    window.deleteCurrentModalPhoto = deleteCurrentModalPhoto;

    document.addEventListener('keydown', function(e) {
        const modal = document.getElementById('formPhotoModal');
        if (modal && modal.style.display === 'flex') {
            if (e.key === 'ArrowLeft') {
                navigatePhotoModal(-1);
            } else if (e.key === 'ArrowRight') {
                navigatePhotoModal(1);
            } else if (e.key === 'Escape') {
                closeFormPhotoModal();
            }
        }
    });

    function captureSpecimenPhoto() {
        if (!isCameraRunning || !videoElement || videoElement.readyState < 2) {
            showError("กรุณาเปิดกล้องก่อนทำการถ่ายภาพ");
            return;
        }

        if (currentPhotos.length >= 8) {
            showAppToast("สามารถบันทึกได้สูงสุด 8 รูป (โปรดลบรูปเดิมก่อนถ่ายใหม่)");
            return;
        }

        try {
            const snapCanvas = document.createElement('canvas');
            const vWidth = videoElement.videoWidth || 640;
            const vHeight = videoElement.videoHeight || 480;

            const maxDim = 1280;
            let targetW = vWidth;
            let targetH = vHeight;
            if (targetW > maxDim || targetH > maxDim) {
                if (targetW >= targetH) {
                    targetH = Math.round((targetH * maxDim) / targetW);
                    targetW = maxDim;
                } else {
                    targetW = Math.round((targetW * maxDim) / targetH);
                    targetH = maxDim;
                }
            }

            snapCanvas.width = targetW;
            snapCanvas.height = targetH;
            const sCtx = snapCanvas.getContext('2d');

            if (currentFacingMode === 'user') {
                sCtx.translate(targetW, 0);
                sCtx.scale(-1, 1);
            }

            sCtx.drawImage(videoElement, 0, 0, targetW, targetH);

            const photoDataUrl = snapCanvas.toDataURL('image/jpeg', 0.85);

            currentPhotos.push(photoDataUrl);
            syncPhotoInputs();
            renderPhotoGallery(currentPhotos.length - 1);

            const photoContainer = document.getElementById('specimen-photo-container');
            if (photoContainer) {
                photoContainer.classList.add('photo-flash-anim');
                setTimeout(() => photoContainer.classList.remove('photo-flash-anim'), 600);
            }

            if (typeof autoSaveDraft === 'function') autoSaveDraft();

            showAppToast(`📸 ถ่ายภาพชิ้นเนื้อสำเร็จ (รูปที่ ${currentPhotos.length})`);
        } catch (err) {
            console.error("Photo capture error:", err);
            showError("เกิดข้อผิดพลาดในการถ่ายภาพ: " + (err.message || err));
        }
    }

    const btnClearPhoto = document.getElementById('btn-clear-photo');
    if (btnClearPhoto) {
        btnClearPhoto.addEventListener('click', function(e) {
            e.stopPropagation();
            if (currentPhotos.length === 0) return;
            if (confirm("ต้องการลบภาพถ่ายชิ้นเนื้อทั้งหมดหรือไม่?")) {
                currentPhotos = [];
                syncPhotoInputs();
                renderPhotoGallery(0);
                if (typeof autoSaveDraft === 'function') autoSaveDraft();
                showAppToast("ลบภาพถ่ายชิ้นเนื้อทั้งหมดเรียบร้อยแล้ว");
            }
        });
    }

    function showAppToast(msg) {
        let toast = document.getElementById('app-floating-toast');
        if (!toast) {
            toast = document.createElement('div');
            toast.id = 'app-floating-toast';
            toast.className = 'app-toast-pill';
            document.body.appendChild(toast);
        }
        toast.innerHTML = msg;
        toast.classList.add('show');
        clearTimeout(toast._timer);
        toast._timer = setTimeout(() => {
            toast.classList.remove('show');
        }, 3000);
    }

    const btnCameraGrid = document.getElementById('btn-camera-grid');
    if (btnCameraGrid) {
        btnCameraGrid.addEventListener('click', function(e) {
            e.stopPropagation();
            const gestureOverlay = document.querySelector('.gesture-controls');
            if (gestureOverlay) {
                const isCurrentlyVisible = gestureOverlay.classList.contains('visible');
                if (isCurrentlyVisible) {
                    gestureOverlay.classList.remove('visible');
                    gestureOverlay.removeAttribute('data-manual-keep');
                    btnCameraGrid.classList.remove('active');
                } else {
                    gestureOverlay.classList.add('visible');
                    gestureOverlay.setAttribute('data-manual-keep', 'true');
                    btnCameraGrid.classList.add('active');
                }
            }
        });
    }

    const btnCameraExpand = document.getElementById('btn-camera-expand');
    if (btnCameraExpand) {
        btnCameraExpand.addEventListener('click', function(e) {
            e.stopPropagation();
            const feedContainer = document.getElementById('camera-feed-container');
            if (feedContainer) {
                feedContainer.classList.toggle('camera-expanded');
                const isExpanded = feedContainer.classList.contains('camera-expanded');
                feedContainer.style.aspectRatio = 'auto';
                feedContainer.style.height = isExpanded ? '440px' : '270px';
                btnCameraExpand.classList.toggle('active', isExpanded);
                updateCachedGeometry();
                setTimeout(updateCachedGeometry, 320);
                showAppToast(isExpanded ? "ขยายขนาดช่องสั่งการเรียบร้อย (Expanded Grid)" : "ย่อขนาดช่องสั่งการ (Compact Grid)");
            }
        });
    }

    window.exportDocxDirectly = function() {
        const form = document.querySelector('.patho-form');
        if (!form) return;
        const formData = new FormData(form);
        const sNo = form.querySelector('input[name="s0_surgical_no"]')?.value?.trim() || 'case';
        
        fetch('/export_docx', {
            method: 'POST',
            body: formData
        })
        .then(res => {
            if (!res.ok) throw new Error('Export request failed');
            return res.blob();
        })
        .then(blob => {
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.style.display = 'none';
            a.href = url;
            a.download = `pathology_breast_gross_${sNo}.docx`;
            document.body.appendChild(a);
            a.click();
            setTimeout(() => {
                window.URL.revokeObjectURL(url);
                document.body.removeChild(a);
            }, 2000);
        })
        .catch(err => {
            console.warn('DOCX export error, submitting form fallback:', err);
            const origAction = form.action;
            const origTarget = form.target;
            form.action = '/export_docx';
            form.target = '_blank';
            form.submit();
            form.action = origAction;
            form.target = origTarget;
        });
    };

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
        if (!text) return "";
        let t = text.toLowerCase();
        
        t = t.replace(/,/g, ' ');
        // Clean dots only when NOT between digits (preserves decimal numbers like 11.4 x 14.9 x 7.8)
        t = t.replace(/(?<!\d)\.|\.(?!\d)/g, ' ');
        
        // 1. Convert multiplication words and symbols
        t = t.replace(/[×*]/g, ' x ');
        t = t.replace(/คูณ/g, ' x ');
        t = t.replace(/\bby\b/gi, ' x ');
        t = t.replace(/\btimes\b/gi, ' x ');

        // 2. Normalize units & punctuation
        t = t.replace(/เซนติเมตร/g, ' cm ');
        t = t.replace(/เซน/g, ' cm ');
        t = t.replace(/ซม\.?/g, ' cm ');
        t = t.replace(/มิลลิเมตร/g, ' mm ');
        t = t.replace(/มิล/g, ' mm ');
        t = t.replace(/มม\.?/g, ' mm ');
        t = t.replace(/จุด/g, '.');

        // 3. Thai numbers (ordered replacement to handle compound numbers like สิบห้า before สิบ)
        const thaiNums = [
            ["ยี่สิบเก้า", "29"], ["ยี่สิบแปด", "28"], ["ยี่สิบเจ็ด", "27"], ["ยี่สิบหก", "26"], ["ยี่สิบห้า", "25"],
            ["ยี่สิบสี่", "24"], ["ยี่สิบสาม", "23"], ["ยี่สิบสอง", "22"], ["ยี่สิบเอ็ด", "21"], ["ยี่สิบ", "20"],
            ["สิบเก้า", "19"], ["สิบแปด", "18"], ["สิบเจ็ด", "17"], ["สิบหก", "16"], ["สิบห้า", "15"],
            ["สิบสี่", "14"], ["สิบสาม", "13"], ["สิบสอง", "12"], ["สิบเอ็ด", "11"], ["สิบ", "10"],
            ["เก้าสิบ", "90"], ["แปดสิบ", "80"], ["เจ็ดสิบ", "70"], ["หกสิบ", "60"], ["ห้าสิบ", "50"],
            ["สี่สิบ", "40"], ["สามสิบ", "30"], ["หนึ่งร้อย", "100"], ["ร้อย", "100"],
            ["ศูนย์", "0"], ["หนึ่ง", "1"], ["สอง", "2"], ["สาม", "3"], ["สี่", "4"],
            ["ห้า", "5"], ["หก", "6"], ["เจ็ด", "7"], ["แปด", "8"], ["เก้า", "9"]
        ];
        for (const [w, v] of thaiNums) {
            t = t.replaceAll(w, v);
        }
        t = t.replace(/(\d+)\s*\.\s*(\d+)/g, (m, g1, g2) => g1 + '.' + g2);

        // English number words
        const numWords = {
            "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
            "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10"
        };
        for (const [word, val] of Object.entries(numWords)) {
            t = t.replace(new RegExp(`\\b${word}\\b`, 'g'), val);
        }

        // Thai dictation translation mapping
        const thaiToEnglish = {
            "ข้างขวา": " right ",
            "เต้าขวา": " right ",
            "ขวา": " right ",
            "ข้างซ้าย": " left ",
            "เต้าซ้าย": " left ",
            "ซ้าย": " left ",
            "ตัดเต้านม": " mastectomy ",
            "มาสเทค": " mastectomy ",
            "มอดิฟายด์": "modified",
            "มอดิฟาย": "modified",
            "โมดิฟายด์": "modified",
            "โมดิฟาย": "modified",
            "เรดิคัล": "radical",
            "แรดิคัล": "radical",
            "ซิมเปิล": "simple",
            "ซิมเปิ้ล": "simple",
            "รักแร้": " axillary ",
            "หางรักแร้": " axillary tail ",
            "ต่อมน้ำเหลือง": " lymph node ",
            "ต่อม": " nodes ",
            "เซนติเนล": "sentinel",
            "ก้อนเนื้อ": " mass ",
            "ก้อน": " mass ",
            "แมส": " mass ",
            "รอยโรค": " mass ",
            "บนนอก": " upper outer ",
            "บนใน": " upper inner ",
            "ล่างนอก": " lower outer ",
            "ล่างใน": " lower inner ",
            "กึ่งกลาง": " central ",
            "ส่วนกลาง": " central ",
            "ใต้ลานนม": "subareolar",
            "หลังลานนม": "retroareolar",
            "ขอบตัด": " margin ",
            "ขอบลึก": " deep margin ",
            "ขอบบน": " superior margin ",
            "ขอบล่าง": " inferior margin ",
            "ขอบใน": " medial margin ",
            "ขอบนอก": " lateral margin ",
            "ขอบผิวหนัง": " skin margin ",
            "ห่างจาก": " from ",
            "ขนาด": " measuring ",
            "ผิวหนัง": " skin ",
            "ปกติ": " appears normal ",
            "เรียบปกติ": " appears normal ",
            "หัวนม": " nipple ",
            "ดึงรั้ง": " inverted ",
            "บอด": " inverted ",
            "นูน": " everted ",
            "คว่ำ": " inverted ",
            "แผลเป็น": " scar ",
            "แผลผ่าตัด": " scar ",
            "แผลเปื่อย": " ulceration ",
            "มีแผล": " ulceration ",
            "เนื้อเต้านมที่เหลือ": "remaining breast tissue",
            "เนื้อเต้านมส่วนที่เหลือ": "remaining breast tissue",
            "เนื้อนมที่เหลือ": "remaining breast tissue",
            "ไม่พบความผิดปกติ": "unremarkable",
            "ปกติไม่มีอะไร": "unremarkable",
            "ถึง": " to ",
            "ตั้งแต่": " ranging from ",
            "เท่ากับ": "=",
            "คือ": "=",
            "โพรงผ่าตัดเดิม": "previous surgical cavity",
            "โพรงแผลเดิม": "previous surgical cavity"
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

        return t;
    }

    function parseTextLocally(text) {
        if (!text) return {};
        const t = text;
        const data = {};

        // 1. Surgical Number
        const surgMatch = t.match(/(?:surgical number|specimen|เคส|รหัสเคส|รหัสสิ่งส่งตรวจ|s-)?\s*(?:is\s+)?([sS]?\s*-?\s*\d{2}\s*[-\s]?\s*\d+)/i);
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
        if (t.includes("modified")) {
            data["s2_proc"] = "modified";
        } else if (t.includes("simple")) {
            data["s2_proc"] = "simple";
        } else {
            const procMatch = t.match(/\b(quadrantectomy|lumpectomy|wide excision|excisional biopsy|re-excision|segmentectomy)\b(?:\s+specimen)?/i) || t.match(/procedure\s+is\s+([a-zA-Z\s]+)/i);
            if (procMatch) {
                data["s2_proc"] = "other";
                data["s2_other_text"] = procMatch[1].trim();
            }
        }

        // 4. Dimensions (3D) Context-Aware Extraction
        const dim3dRegex = /([\d.]+)\s*(?:cm|mm)?\s*x\s*([\d.]+)\s*(?:cm|mm)?\s*x\s*([\d.]+)/gi;
        const all3D = [];
        let match;
        while ((match = dim3dRegex.exec(t)) !== null) {
            all3D.push({
                dims: [match[1].replace(/\.$/, ''), match[2].replace(/\.$/, ''), match[3].replace(/\.$/, '')],
                start: match.index,
                end: match.index + match[0].length,
                assigned: false
            });
        }

        if (all3D.length > 0) {
            // STEP 4A: Specimen Overall Dimensions (FIRST)
            for (const item of all3D) {
                const pre = t.slice(Math.max(0, item.start - 60), item.start).toLowerCase();
                if (pre.includes("specimen") || pre.includes("mastectomy") || pre.includes("measuring") || pre.includes("overall") || pre.includes("ชิ้นเนื้อ") || pre.includes("เต้านม")) {
                    const lastSpecKw = Math.max(pre.lastIndexOf("specimen"), pre.lastIndexOf("mastectomy"), pre.lastIndexOf("measuring"), pre.lastIndexOf("overall"), pre.lastIndexOf("ชิ้นเนื้อ"), pre.lastIndexOf("เต้านม"));
                    const lastMassKw = Math.max(pre.lastIndexOf("mass"), pre.lastIndexOf("tumor"), pre.lastIndexOf("infiltrative"), pre.lastIndexOf("ก้อน"));
                    if (lastSpecKw > lastMassKw) {
                        data["s3_dims"] = item.dims;
                        item.assigned = true;
                        break;
                    }
                }
            }

            // STEP 4B: Previous surgical cavity
            if (t.includes("previous surgical cavity") && (t.includes("residual") || t.includes("residual mass"))) {
                data["s10_prev2"] = true;
                data["s10_grammar"] = "is a";
                for (const item of all3D) {
                    if (item.assigned) continue;
                    const pre = t.slice(Math.max(0, item.start - 50), item.start).toLowerCase();
                    const post = t.slice(item.end, Math.min(t.length, item.end + 50)).toLowerCase();
                    if ((pre.includes("cavity") || pre.includes("fibrous") || post.includes("cavity")) && !data["s10_prev2_cavity_dims"]) {
                        data["s10_prev2_cavity_dims"] = item.dims;
                        item.assigned = true;
                    } else if ((pre.includes("residual") || post.includes("residual")) && !data["s10_prev2_mass_dims"]) {
                        data["s10_prev2_mass_dims"] = item.dims;
                        item.assigned = true;
                    }
                }
            } else if (t.includes("previous surgical cavity")) {
                data["s10_prev1"] = true;
                data["s10_grammar"] = "is a";
                for (const item of all3D) {
                    if (item.assigned) continue;
                    const pre = t.slice(Math.max(0, item.start - 50), item.start).toLowerCase();
                    if (pre.includes("cavity") || pre.includes("fibrous")) {
                        data["s10_prev1_dims"] = item.dims;
                        item.assigned = true;
                        break;
                    }
                }
            } else if (t.includes("well defined") || t.includes("well-defined") || t.includes("slit like") || t.includes("slit-like")) {
                data["s10_well"] = true;
                data["s10_grammar"] = "is a";
                for (const item of all3D) {
                    if (item.assigned) continue;
                    const pre = t.slice(Math.max(0, item.start - 50), item.start).toLowerCase();
                    if (pre.includes("well") || pre.includes("slit")) {
                        data["s10_well_dims"] = item.dims;
                        item.assigned = true;
                        break;
                    }
                }
            }

            // STEP 4C: Axillary tail dimension
            if (t.includes("axillary") || t.includes("tail") || t.includes("รักแร้")) {
                for (const item of all3D) {
                    if (item.assigned) continue;
                    const pre = t.slice(Math.max(0, item.start - 50), item.start).toLowerCase();
                    if (pre.includes("axillary") || pre.includes("tail") || pre.includes("รักแร้")) {
                        data["s4_check"] = true;
                        data["s4_dims"] = item.dims;
                        item.assigned = true;
                        break;
                    }
                }
            }

            // STEP 4D: Infiltrative mass
            if (t.includes("infiltrative") || t.includes("mass") || t.includes("tumor") || t.includes("lesion") || t.includes("ก้อน")) {
                data["s10_infiltrative"] = true;
                data["s10_grammar"] = t.includes("infiltrative") ? "is an" : "is a";
                for (const item of all3D) {
                    if (item.assigned) continue;
                    const pre = t.slice(Math.max(0, item.start - 50), item.start).toLowerCase();
                    const post = t.slice(item.end, Math.min(t.length, item.end + 50)).toLowerCase();
                    if (pre.includes("mass") || pre.includes("infiltrative") || pre.includes("tumor") || pre.includes("lesion") || pre.includes("ก้อน") ||
                        post.includes("mass") || post.includes("infiltrative") || post.includes("tumor") || post.includes("lesion") || post.includes("ก้อน")) {
                        data["s10_inf_dims"] = item.dims;
                        item.assigned = true;
                        break;
                    }
                }
            }

            // Fallbacks for any unassigned 3D dimensions
            if (!data["s3_dims"]) {
                const unassigned = all3D.find(i => !i.assigned);
                if (unassigned) {
                    data["s3_dims"] = unassigned.dims;
                    unassigned.assigned = true;
                }
            }
            if (data["s10_infiltrative"] && !data["s10_inf_dims"]) {
                const unassigned = all3D.find(i => !i.assigned);
                if (unassigned) {
                    data["s10_inf_dims"] = unassigned.dims;
                    unassigned.assigned = true;
                }
            }
        }

        // 5. Skin ellipse dimensions (2D)
        const textWithout3D = t.replace(/[\d.]+\s*(?:cm|mm)?\s*x\s*[\d.]+\s*(?:cm|mm)?\s*x\s*[\d.]+/gi, '[3D_DIMS]');
        const dims2d = [];
        const dim2dRegex = /\b([\d.]+)\s*(?:cm|mm)?\s*x\s*([\d.]+)\b/g;
        let m2d;
        while ((m2d = dim2dRegex.exec(textWithout3D)) !== null) {
            dims2d.push([m2d[1].replace(/\.$/, ''), m2d[2].replace(/\.$/, '')]);
        }
        if (dims2d.length > 0 && (t.includes("skin") || t.includes("ellipse"))) {
            data["s5_dims"] = dims2d[0];
        }
        if (t.includes("appears normal") || t.includes("skin normal") || t.includes("ปกติ")) {
            data["s5_appears_normal"] = true;
        }

        // 6. Scar & Ulceration
        const scarIdx = t.indexOf("scar");
        let endScar = -1;
        if (scarIdx !== -1) {
            data["s6_check"] = true;
            const scarLen = t.match(/scar.*?\b([\d.]+)\s*(?:cm)?/i);
            if (scarLen) data["s7_len"] = scarLen[1].replace(/\.$/, '');

            const dotM = t.substring(scarIdx).search(/(?<!\d)\.(?!\d)/);
            endScar = dotM !== -1 ? scarIdx + dotM : t.length;
            endScar = Math.min(endScar, scarIdx + 80);
            const uNext = t.indexOf("ulceration", scarIdx);
            if (uNext !== -1 && uNext < endScar) endScar = uNext;

            const scarClause = t.substring(scarIdx, endScar).toLowerCase();
            const s7_locs = [];
            ["areola", "upper", "lower", "inner", "outer"].forEach(loc => {
                if (new RegExp(`\\b${loc}\\b`, 'i').test(scarClause)) {
                    s7_locs.push(loc);
                }
            });
            if (s7_locs.length > 0) data["s7_locs"] = s7_locs;
        }

        const ulcerIdx = t.indexOf("ulceration");
        let endUlcer = -1;
        if (ulcerIdx !== -1) {
            data["s8_check"] = true;
            const ulcerDim = t.match(/ulceration.*?\b([\d.]+)\s*(?:cm|mm)?\s*x\s*([\d.]+)/i);
            if (ulcerDim) {
                data["s8_dims"] = [ulcerDim[1].replace(/\.$/, ''), ulcerDim[2].replace(/\.$/, '')];
            } else if (dims2d.length > 1) {
                data["s8_dims"] = dims2d[1];
            }

            const dotM = t.substring(ulcerIdx).search(/(?<!\d)\.(?!\d)/);
            endUlcer = dotM !== -1 ? ulcerIdx + dotM : t.length;
            endUlcer = Math.min(endUlcer, ulcerIdx + 80);
            const mNext = t.indexOf("mass", ulcerIdx);
            if (mNext !== -1 && mNext < endUlcer) endUlcer = mNext;

            const ulcerClause = t.substring(ulcerIdx, endUlcer).toLowerCase();
            const s8_locs = [];
            ["areola", "upper", "lower", "inner", "outer"].forEach(loc => {
                if (new RegExp(`\\b${loc}\\b`, 'i').test(ulcerClause)) {
                    s8_locs.push(loc);
                }
            });
            if (s8_locs.length > 0) data["s8_locs"] = s8_locs;
        }

        // 7. Nipple status
        const s9_val = [];
        if (t.includes("everted")) s9_val.push("everted");
        if (t.includes("inverted") || t.includes("retracted")) s9_val.push("inverted");
        if (/(?:nipple[^\.\n]{0,50}(?:ulcer|ulceration)|(?:ulcer|ulceration)[^\.\n]{0,50}nipple)/i.test(t)) {
            s9_val.push("ulceration");
        }
        if (s9_val.length > 0) data["s9_val"] = s9_val;

        // 7.5 Tumor Quadrants & Locations (Section 10.5)
        let tumorText = t;
        if (scarIdx !== -1) {
            tumorText = tumorText.substring(0, scarIdx) + " " + tumorText.substring(endScar);
        }
        const uPos = tumorText.indexOf("ulceration");
        if (uPos !== -1) {
            const dotU = tumorText.substring(uPos).search(/(?<!\d)\.(?!\d)/);
            let endU = dotU !== -1 ? uPos + dotU : Math.min(tumorText.length, uPos + 80);
            const mNext = tumorText.indexOf("mass", uPos);
            if (mNext !== -1 && mNext < endU) endU = mNext;
            tumorText = tumorText.substring(0, uPos) + " " + tumorText.substring(endU);
        }

        if (tumorText.includes("beneath the nipple") || tumorText.includes("beneath nipple")) {
            data["s10_5_nipple"] = true;
        }
        if (tumorText.includes("beneath the scar") || tumorText.includes("beneath scar")) {
            data["s10_5_scar"] = true;
        }
        if (tumorText.includes("subareola") || tumorText.includes("central portion") || tumorText.includes("in central")) {
            data["s10_5_central"] = true;
        }

        const quadrantVals = [];
        const locMatches = [...tumorText.matchAll(/(?:(?:in|at)\s+(?:the\s+)?)?(upper|lower|central)\s*(inner|outer)?(?:\s*quadrant)?/gi)];
        if (locMatches && locMatches.length > 0) {
            const locText = locMatches[locMatches.length - 1][0].toLowerCase();
            if (locText.includes("central")) {
                data["s10_5_central"] = true;
            } else {
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
            const otherLocMatch = tumorText.match(/(?:located\s+(?:in|at)|tumor\s+is\s+in|location\s+is)\s+(?:the\s+)?(axillary\s+tail(?:\s+of\s+spence)?|retroareolar|subareolar|chest\s+wall|deep\s+fascia|[a-zA-Z\s]+?(?:region|plane|tail))/i);
            if (otherLocMatch) {
                data["s10_5_other_check"] = true;
                data["s10_5_other"] = otherLocMatch[1].trim();
            }
        }

        // 8. Margins
        const margins = ["deep", "superior", "inferior", "medial", "lateral", "skin"];
        margins.forEach(m => {
            let mMatch = t.match(new RegExp(`(?:${m}\\s*margin|\\b${m}\\b)\\s*(?:is|at|=|:)?\\s*([\\d.]+)(?:\\s*(?:cm|mm))?`, 'i'));
            if (!mMatch) {
                mMatch = t.match(new RegExp(`([\\d.]+)(?:\\s*(?:cm|mm))?\\s*(?:cm\\s*)?(?:from|at)\\s*(?:the\\s*)?${m}(?:\\s*margin)?`, 'i'));
            }
            if (mMatch) {
                data[`s11_${m}`] = mMatch[1].replace(/\.$/, '');
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
        if ((t.includes("lymph node") || t.includes("nodes") || t.includes("ต่อมน้ำเหลือง") || t.includes("ต่อม")) && !t.includes("not found") && !t.includes("no lymph")) {
            data["s14_check"] = true;
            const countMatch = t.match(/(\d+)\s*(?:lymph\s+)?nodes?/i) 
                            || t.match(/(?:จำนวน\s*)?(\d+)\s*ต่อม/i)
                            || t.match(/(?:lymph\s*nodes?|ต่อมน้ำเหลือง)[\s\S]{0,25}?(?:จำนวน\s*)?(\d+)/i);
            if (countMatch) data["s14_num"] = countMatch[1];

            const rangeMatch = t.match(/(?:ranging\s+from|measuring|size|ขนาด(?:ตั้งแต่)?)\s+([\d.]+)\s*(?:cm|mm)?\s*(?:to|-)\s*([\d.]+)\s*(?:cm|mm)?/i)
                            || t.match(/([\d.]+)\s*(?:to|-)\s*([\d.]+)\s*(?:cm|mm)/i);
            if (rangeMatch) {
                data["s14_min"] = rangeMatch[1].replace(/\.$/, '');
                data["s14_max"] = rangeMatch[2].replace(/\.$/, '');
            } else {
                const nodeIdx = Math.max(t.lastIndexOf("node"), t.lastIndexOf("ต่อม"));
                if (nodeIdx !== -1) {
                    const nodeContext = t.slice(nodeIdx);
                    const sizes = nodeContext.match(/\b(\d+(?:\.\d+)?)\b/g);
                    if (sizes && sizes.length >= 2) {
                        const nodeNum = Number(data["s14_num"] || -999);
                        const sizesFloat = sizes.map(Number).filter(n => n <= 10.0 && n !== nodeNum);
                        if (sizesFloat.length >= 2) {
                            data["s14_min"] = Math.min(...sizesFloat).toString();
                            data["s14_max"] = Math.max(...sizesFloat).toString();
                        }
                    }
                }
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
            if (data.s7_locs && Array.isArray(data.s7_locs)) {
                data.s7_locs.forEach(loc => setCheck(`[name="s7_locs"][value="${loc}"]`, true));
            }
        }
        // Ulcer
        if (data.s8_check) {
            setCheck('[name="s8_check"]', true);
            if (data.s8_dims) {
                setVal('[name="s8_dims_0"]', data.s8_dims[0]);
                setVal('[name="s8_dims_1"]', data.s8_dims[1]);
            }
            if (data.s8_locs && Array.isArray(data.s8_locs)) {
                data.s8_locs.forEach(loc => setCheck(`[name="s8_locs"][value="${loc}"]`, true));
            }
        }
        // Nipple
        if (data.s9_val && Array.isArray(data.s9_val)) {
            ['everted', 'inverted', 'ulceration'].forEach(v => {
                setCheck(`[name="s9_val"][value="${v}"]`, data.s9_val.includes(v));
            });
        }
        if (data.s8_check && (!data.s9_val || !data.s9_val.includes("ulceration"))) {
            setCheck('[name="s9_val"][value="ulceration"]', false);
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
        // Tumor Locations (10.5)
        if (data.s10_5_nipple) setCheck('[name="s10_5_nipple"]', true);
        if (data.s10_5_scar) setCheck('[name="s10_5_scar"]', true);
        if (data.s10_5_central) setCheck('[name="s10_5_central"]', true);

        // Tumor Quadrants (10.5)
        if (data.s10_5_quadrant_check && data.s10_5_quadrant_vals) {
            setCheck('[name="s10_5_quadrant_check"]', true);
            data.s10_5_quadrant_vals.forEach(q => {
                setCheck(`[name="s10_5_quadrant_vals"][value="${q}"]`, true);
            });
        }
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

    // --- Audio Playlist Engine (Multi-Clip) ---
    let currentAudioClips = [];

    function initAudioClips() {
        const hiddenClips = document.getElementById('hidden-audio-clips-json');
        const hiddenAudio = document.getElementById('hidden-audio-filename');
        if (hiddenClips && hiddenClips.value && hiddenClips.value.trim().startsWith('[')) {
            try {
                currentAudioClips = JSON.parse(hiddenClips.value);
                if (!Array.isArray(currentAudioClips)) currentAudioClips = [];
            } catch(e) {
                currentAudioClips = [];
            }
        }
        if (currentAudioClips.length === 0 && hiddenAudio && hiddenAudio.value && hiddenAudio.value.trim()) {
            const fn = hiddenAudio.value.trim();
            const audioUrl = (fn.startsWith('http://') || fn.startsWith('https://')) ? fn : `/uploads/${encodeURIComponent(fn)}`;
            currentAudioClips = [{
                filename: fn,
                url: audioUrl,
                label: 'คลิปที่ 1',
                timestamp: ''
            }];
        }
        renderAudioPlaylist(currentAudioClips.length > 0 ? currentAudioClips.length - 1 : 0);
    }

    function syncAudioInputs() {
        const hiddenClips = document.getElementById('hidden-audio-clips-json');
        const hiddenAudio = document.getElementById('hidden-audio-filename');
        const hiddenCleared = document.getElementById('hidden-audio-cleared');
        if (hiddenClips) {
            hiddenClips.value = JSON.stringify(currentAudioClips);
        }
        if (currentAudioClips.length > 0) {
            if (hiddenAudio) hiddenAudio.value = currentAudioClips[currentAudioClips.length - 1].filename || '';
            if (hiddenCleared) hiddenCleared.value = 'false';
        } else {
            if (hiddenAudio) hiddenAudio.value = '';
            if (hiddenCleared) hiddenCleared.value = 'true';
        }
    }

    function renderAudioPlaylist(selectedIdx = 0) {
        const audioContainer = document.getElementById('sidebar-audio-playback-container');
        const audioPlayer = document.getElementById('sidebar-audio-player');
        const countBadge = document.getElementById('audio-clips-count');
        const selectorContainer = document.getElementById('audio-selector-container');
        const selector = document.getElementById('audio-clip-selector');

        if (!audioContainer) return;

        if (currentAudioClips.length === 0) {
            audioContainer.style.display = 'none';
            if (audioPlayer) {
                audioPlayer.pause();
                audioPlayer.removeAttribute('src');
                audioPlayer.innerHTML = '';
                audioPlayer.load();
            }
            if (countBadge) countBadge.textContent = '0';
            return;
        }

        audioContainer.style.display = 'flex';
        if (countBadge) countBadge.textContent = currentAudioClips.length;

        if (selectorContainer && selector) {
            if (currentAudioClips.length > 1) {
                selectorContainer.style.display = 'flex';
                selector.innerHTML = '';
                currentAudioClips.forEach((clip, idx) => {
                    const opt = document.createElement('option');
                    opt.value = idx;
                    const timeStr = clip.timestamp ? ` (${clip.timestamp})` : '';
                    opt.textContent = `${clip.label || ('คลิปที่ ' + (idx + 1))}${timeStr}`;
                    if (idx === selectedIdx) opt.selected = true;
                    selector.appendChild(opt);
                });
            } else {
                selectorContainer.style.display = 'none';
            }
        }

        const safeIdx = Math.max(0, Math.min(selectedIdx, currentAudioClips.length - 1));
        const activeClip = currentAudioClips[safeIdx];
        if (activeClip && audioPlayer) {
            const audioSrc = activeClip.url || (activeClip.filename.startsWith('http') ? activeClip.filename : `/uploads/${encodeURIComponent(activeClip.filename)}`);
            audioPlayer.src = audioSrc;
            audioPlayer.load();
        }
    }

    function onSelectAudioClip(index) {
        const idx = parseInt(index, 10);
        if (!isNaN(idx) && idx >= 0 && idx < currentAudioClips.length) {
            const activeClip = currentAudioClips[idx];
            const audioPlayer = document.getElementById('sidebar-audio-player');
            if (activeClip && audioPlayer) {
                const audioSrc = activeClip.url || (activeClip.filename.startsWith('http') ? activeClip.filename : `/uploads/${encodeURIComponent(activeClip.filename)}`);
                audioPlayer.src = audioSrc;
                audioPlayer.load();
                audioPlayer.play().catch(() => {});
            }
        }
    }
    window.onSelectAudioClip = onSelectAudioClip;

    function deleteActiveAudioClip() {
        if (currentAudioClips.length === 0) return;
        const selector = document.getElementById('audio-clip-selector');
        let activeIdx = 0;
        if (selector && currentAudioClips.length > 1) {
            activeIdx = parseInt(selector.value, 10) || 0;
        }
        const clipLabel = currentAudioClips[activeIdx]?.label || `คลิปที่ ${activeIdx + 1}`;
        if (confirm(`ต้องการลบ ${clipLabel} หรือไม่?`)) {
            currentAudioClips.splice(activeIdx, 1);
            syncAudioInputs();
            renderAudioPlaylist(Math.max(0, activeIdx - 1));
            if (typeof autoSaveDraft === 'function') autoSaveDraft();
            showAppToast("ลบคลิปเสียงเรียบร้อยแล้ว");
        }
    }
    window.deleteActiveAudioClip = deleteActiveAudioClip;

    function clearSidebarAudio() {
        if (currentAudioClips.length === 0) return;
        if (confirm("ต้องการลบคลิปเสียงทั้งหมดหรือไม่?")) {
            currentAudioClips = [];
            syncAudioInputs();
            renderAudioPlaylist(0);
            if (typeof autoSaveDraft === 'function') autoSaveDraft();
            showAppToast("ลบคลิปเสียงทั้งหมดแล้ว");
        }
    }
    window.clearSidebarAudio = clearSidebarAudio;

    function resetFormToBlank() {
        clearLocalDraft();
        const form = document.querySelector('.patho-form');
        if (form) {
            form.querySelectorAll('input, select, textarea').forEach(el => {
                if (el.type === 'radio' || el.type === 'checkbox') {
                    el.checked = false;
                } else if (el.type !== 'submit' && el.type !== 'button') {
                    el.value = '';
                }
                el.removeAttribute('data-manual');
                el.style.border = '';
                el.style.backgroundColor = '';
                el.style.boxShadow = '';
                el.classList.remove('low-confidence-highlight');
            });
            document.querySelectorAll('.checkbox-visual, .circle-option, .low-confidence-highlight').forEach(el => {
                el.classList.remove('low-confidence-highlight');
            });
        }
        if (txtTranscription) txtTranscription.value = '';
        if (sidebarTranscriptionBox) sidebarTranscriptionBox.value = '';

        // Reset multi-audio
        currentAudioClips = [];
        syncAudioInputs();
        renderAudioPlaylist(0);

        // Reset multi-photo
        currentPhotos = [];
        syncPhotoInputs();
        renderPhotoGallery(0);

        const warnBox = document.getElementById('clinical-warning-box');
        if (warnBox) warnBox.style.display = 'none';

        const draftBar = document.getElementById('draft-recovery-bar');
        if (draftBar) draftBar.style.display = 'none';

        validateFormData();
    }
    window.resetFormToBlank = resetFormToBlank;

    function autoSaveDraft() {
        // DO NOT save drafts if viewing a loaded historical case
        if (document.querySelector('.case-loaded-pill') || document.body.getAttribute('data-is-history') === 'true') {
            return;
        }
        if (draftSaveTimeout) clearTimeout(draftSaveTimeout);
        draftSaveTimeout = setTimeout(() => {
            try {
                const formData = {};
                document.querySelectorAll('.patho-form input, .patho-form select, .patho-form textarea').forEach(el => {
                    if (!el.name || el.name === 'audio_file' || el.name === 'photo_data') return;
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
            const urlParams = new URLSearchParams(window.location.search);
            const isExplicitNew = urlParams.get('new') === '1' || 
                                  urlParams.get('new_case') === '1' || 
                                  document.body.getAttribute('data-is-new-case') === 'true';

            if (isExplicitNew) {
                // Clear any stored draft and ensure 100% clean blank form
                clearLocalDraft();
                resetFormToBlank();
                if (window.history.replaceState && (urlParams.has('new') || urlParams.has('new_case'))) {
                    window.history.replaceState({}, document.title, window.location.pathname);
                }
                return;
            }

            // Do not prompt or restore draft if viewing an existing case from history
            if (document.querySelector('.case-loaded-pill') || document.body.getAttribute('data-is-history') === 'true') {
                return;
            }

            const saved = localStorage.getItem(DRAFT_STORAGE_KEY);
            if (!saved) return;
            const parsed = JSON.parse(saved);
            if (!parsed || !parsed.data || Object.keys(parsed.data).length === 0) return;

            const currentSurgNo = document.querySelector('[name="s0_surgical_no"]')?.value;
            // Only prompt if form currently has no surgical number
            if (!currentSurgNo || currentSurgNo.trim() === '') {
                const draftBar = document.getElementById('draft-recovery-bar');
                const draftTime = document.getElementById('draft-saved-time');
                if (draftBar) {
                    if (draftTime && parsed.savedAt) {
                        try {
                            const d = new Date(parsed.savedAt);
                            draftTime.textContent = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) + ' น.';
                        } catch(e) {
                            draftTime.textContent = 'ฉบับก่อนหน้า';
                        }
                    }
                    draftBar.style.display = 'flex';

                    const btnRestore = document.getElementById('btn-restore-draft');
                    const btnDiscard = document.getElementById('btn-discard-draft');

                    if (btnRestore) {
                        btnRestore.onclick = function() {
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

                            if (parsed.data && parsed.data.photos_json) {
                                try {
                                    currentPhotos = JSON.parse(parsed.data.photos_json);
                                    if (!Array.isArray(currentPhotos)) currentPhotos = [];
                                    syncPhotoInputs();
                                    renderPhotoGallery(0);
                                } catch(e) {}
                            } else if (parsed.data && parsed.data.photo_data) {
                                currentPhotos = [parsed.data.photo_data];
                                syncPhotoInputs();
                                renderPhotoGallery(0);
                            }

                            if (parsed.data && parsed.data.audio_clips_json) {
                                try {
                                    currentAudioClips = JSON.parse(parsed.data.audio_clips_json);
                                    if (!Array.isArray(currentAudioClips)) currentAudioClips = [];
                                    syncAudioInputs();
                                    renderAudioPlaylist(currentAudioClips.length - 1);
                                } catch(e) {}
                            } else if (parsed.data && parsed.data.audio_filename) {
                                const afn = parsed.data.audio_filename;
                                currentAudioClips = [{
                                    filename: afn,
                                    url: (afn.startsWith('http://') || afn.startsWith('https://')) ? afn : `/uploads/${encodeURIComponent(afn)}`,
                                    label: 'คลิปที่ 1',
                                    timestamp: ''
                                }];
                                syncAudioInputs();
                                renderAudioPlaylist(0);
                            }

                            validateFormData();
                            draftBar.style.display = 'none';
                            if (micStatusContainer) {
                                micStatusContainer.innerHTML = '<span style="color:#2563eb;"><i class="fas fa-history"></i> กู้คืนข้อมูลร่างล่าสุดเรียบร้อยแล้ว</span>';
                            }
                        };
                    }

                    if (btnDiscard) {
                        btnDiscard.onclick = function() {
                            clearLocalDraft();
                            draftBar.style.display = 'none';
                            resetFormToBlank();
                        };
                    }
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

    window.setPaperZoom = function(newZoom) {
        currentDocZoom = Math.min(Math.max(newZoom, 0.5), 1.6);
        currentDocZoom = Math.round(currentDocZoom * 10) / 10;
        
        const paper = document.querySelector('.paper-sheet');
        const zoomText = document.getElementById('zoom-level-text');
        
        if (paper) {
            paper.style.zoom = currentDocZoom;
            if (!('zoom' in paper.style)) {
                paper.style.transform = `scale(${currentDocZoom})`;
                paper.style.transformOrigin = 'top center';
            }
        }
        if (zoomText) {
            zoomText.textContent = `${Math.round(currentDocZoom * 100)}%`;
        }
    };

    window.changePaperZoom = function(delta) {
        window.setPaperZoom(currentDocZoom + delta);
    };

    const btnZoomIn = document.getElementById('btn-zoom-in');
    const btnZoomOut = document.getElementById('btn-zoom-out');
    const zoomTextBtn = document.getElementById('zoom-level-text');

    if (btnZoomIn) {
        btnZoomIn.addEventListener('click', (e) => {
            e.preventDefault();
            window.changePaperZoom(0.1);
        });
    }

    if (btnZoomOut) {
        btnZoomOut.addEventListener('click', (e) => {
            e.preventDefault();
            window.changePaperZoom(-0.1);
        });
    }

    if (zoomTextBtn) {
        zoomTextBtn.addEventListener('click', (e) => {
            e.preventDefault();
            window.setPaperZoom(1.0);
        });
    }

    // Initialize multi-photo gallery and multi-audio playlist
    initPhotos();
    initAudioClips();

    // Restore draft on load
    restoreDraftIfAvailable();
});
