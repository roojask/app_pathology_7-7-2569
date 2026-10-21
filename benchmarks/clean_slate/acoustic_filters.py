"""
acoustic_filters.py -- Acoustic Preprocessing, Cross-Filter Benchmark, Parameter Grid Search,
and Blind SNR-Gated Adaptive Denoising (Method D8) for the Clean-Slate Thesis Redesign.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path
import numpy as np
from scipy.io import wavfile
from scipy.signal import stft, istft
from faster_whisper.audio import decode_audio

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
import configs.config  # Ensures bin/ffmpeg.exe is in PATH

FFMPEG_BIN = str(REPO_ROOT / "bin" / "ffmpeg.exe") if (REPO_ROOT / "bin" / "ffmpeg.exe").exists() else "ffmpeg"
SILENCE_FILTER = "silenceremove=start_periods=1:start_duration=0.1:start_threshold=-50dB"

# Custom 15-band noise floor profile for laboratory fume-hood hum (heavy low-frequency energy)
CUSTOM_FUME_BAND_NOISE = "10 8 6 4 2 0 -2 -4 -6 -8 -10 -12 -14 -15 -15"


def estimate_blind_snr(audio_path: str | Path, sr: int = 16000, frame_length: int = 512, hop_length: int = 256) -> dict:
    """
    Blind Acoustic SNR Estimator:
    Computes frame-level RMS power (32 ms frames, 16 ms hop) and estimates SNR (dB)
    from the 85th percentile (active speech + noise) vs. 15th percentile (background noise floor)
    of non-digital-zero frames. No category or oracle labels are used.
    """
    y = decode_audio(str(audio_path), sampling_rate=sr).astype(np.float32)
    duration_sec = len(y) / float(sr)
    n_frames = (len(y) - frame_length) // hop_length + 1
    if n_frames <= 0:
        return {"snr_db": 0.0, "p15_db": -100.0, "p85_db": -100.0, "duration_sec": duration_sec}

    strides = (y.strides[0] * hop_length, y.strides[0])
    frames = np.lib.stride_tricks.as_strided(y, shape=(n_frames, frame_length), strides=strides)
    power = np.mean(frames ** 2, axis=1)
    non_zero = power[power > 1e-10]
    if len(non_zero) == 0:
        return {"snr_db": 0.0, "p15_db": -100.0, "p85_db": -100.0, "duration_sec": duration_sec}

    p_noise = float(np.percentile(non_zero, 15))
    p_sig_plus_noise = float(np.percentile(non_zero, 85))
    p_speech = max(p_sig_plus_noise - p_noise, 1e-10)
    p_noise = max(p_noise, 1e-10)
    snr_db = float(10.0 * np.log10(p_speech / p_noise))
    return {
        "snr_db": round(snr_db, 3),
        "p15_db": round(float(10.0 * np.log10(p_noise)), 3),
        "p85_db": round(float(10.0 * np.log10(max(p_sig_plus_noise, 1e-10))), 3),
        "duration_sec": round(duration_sec, 3),
    }


def apply_ffmpeg_filter(input_path: str | Path, af_chain: str | None, out_wav_path: str | Path) -> str:
    """Runs FFmpeg with the specified audio filter chain (`-af`) to produce a 16 kHz mono WAV."""
    cmd = [FFMPEG_BIN, "-y", "-i", str(input_path)]
    if af_chain:
        cmd += ["-af", af_chain]
    cmd += ["-ar", "16000", "-ac", "1", str(out_wav_path)]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    return str(out_wav_path)


def apply_spectral_gating_scipy(input_path: str | Path, out_wav_path: str | Path, prop_decrease: float = 0.85) -> str:
    """
    Lightweight CPU Spectral Subtraction / Wiener-style Spectral Gate using STFT:
    Estimates per-frequency-bin noise floor from the lowest-energy 15% frames and attenuates
    bins below 1.5x the noise floor.
    """
    y = decode_audio(str(input_path), sampling_rate=16000).astype(np.float32)
    f, t, Zxx = stft(y, fs=16000, nperseg=512, noverlap=384)
    mag = np.abs(Zxx)
    phase = np.angle(Zxx)

    frame_energy = np.mean(mag ** 2, axis=0)
    non_zero_idx = np.where(frame_energy > 1e-10)[0]
    if len(non_zero_idx) > 4:
        thresh_e = np.percentile(frame_energy[non_zero_idx], 20)
        noise_frames = mag[:, frame_energy <= thresh_e]
        noise_profile = np.median(noise_frames, axis=1, keepdims=True) if noise_frames.shape[1] > 0 else np.percentile(mag, 15, axis=1, keepdims=True)
    else:
        noise_profile = np.percentile(mag, 15, axis=1, keepdims=True)

    # Smooth Wiener-like gain mask
    snr_bin = (mag ** 2) / (noise_profile ** 2 * 2.2 + 1e-10)
    gain = np.clip(snr_bin / (1.0 + snr_bin), 1.0 - prop_decrease, 1.0)
    Zxx_clean = mag * gain * np.exp(1j * phase)
    _, y_rec = istft(Zxx_clean, fs=16000, nperseg=512, noverlap=384)
    y_rec = np.clip(y_rec[:len(y)], -1.0, 1.0)
    wavfile.write(str(out_wav_path), 16000, (y_rec * 32767.0).astype(np.int16))
    return str(out_wav_path)


FILTER_CONFIGS = {
    # Cross-Filter Benchmark
    "F0_no_filter": {"type": "none", "af": None, "desc": "No Denoising Filter (Raw Audio)"},
    "F0_silence_only": {"type": "ffmpeg", "af": SILENCE_FILTER, "desc": "Silence Removal Only (Bypass Denoiser)"},
    "F1_bandpass": {
        "type": "ffmpeg",
        "af": f"highpass=f=150,lowpass=f=7500,{SILENCE_FILTER}",
        "desc": "Band-Pass Filter (150-7500 Hz)",
    },
    "F2_anlmdn": {
        "type": "ffmpeg",
        "af": f"anlmdn=s=7:p=0.002:r=0.002:m=15,{SILENCE_FILTER}",
        "desc": "FFmpeg anlmdn (Non-Local Means Time-Domain)",
    },
    "F3_spectral_gate": {
        "type": "scipy_stft",
        "af": None,
        "desc": "STFT Wiener Spectral Gating",
    },
    # FFmpeg afftdn Parameter Grid Search: nr in {6, 12, 18, 24}, nt in {w (white), v (vinyl), c (custom)}
    "afftdn_nr6_white": {"type": "ffmpeg", "af": f"afftdn=nr=6:nf=-50:nt=w,{SILENCE_FILTER}", "desc": "afftdn (nr=6, nt=white)"},
    "afftdn_nr12_white": {"type": "ffmpeg", "af": f"afftdn=nr=12:nf=-50:nt=w,{SILENCE_FILTER}", "desc": "afftdn (nr=12, nt=white [Default])"},
    "afftdn_nr18_white": {"type": "ffmpeg", "af": f"afftdn=nr=18:nf=-50:nt=w,{SILENCE_FILTER}", "desc": "afftdn (nr=18, nt=white)"},
    "afftdn_nr24_white": {"type": "ffmpeg", "af": f"afftdn=nr=24:nf=-50:nt=w,{SILENCE_FILTER}", "desc": "afftdn (nr=24, nt=white)"},
    "afftdn_nr6_vinyl": {"type": "ffmpeg", "af": f"afftdn=nr=6:nf=-50:nt=v,{SILENCE_FILTER}", "desc": "afftdn (nr=6, nt=vinyl)"},
    "afftdn_nr12_vinyl": {"type": "ffmpeg", "af": f"afftdn=nr=12:nf=-50:nt=v,{SILENCE_FILTER}", "desc": "afftdn (nr=12, nt=vinyl)"},
    "afftdn_nr18_vinyl": {"type": "ffmpeg", "af": f"afftdn=nr=18:nf=-50:nt=v,{SILENCE_FILTER}", "desc": "afftdn (nr=18, nt=vinyl)"},
    "afftdn_nr24_vinyl": {"type": "ffmpeg", "af": f"afftdn=nr=24:nf=-50:nt=v,{SILENCE_FILTER}", "desc": "afftdn (nr=24, nt=vinyl)"},
    "afftdn_nr12_custom": {
        "type": "ffmpeg",
        "af": f"afftdn=nr=12:nf=-45:nt=c:bn='{CUSTOM_FUME_BAND_NOISE}',{SILENCE_FILTER}",
        "desc": "afftdn (nr=12, nt=custom fume profile)",
    },
    "afftdn_nr18_custom": {
        "type": "ffmpeg",
        "af": f"afftdn=nr=18:nf=-45:nt=c:bn='{CUSTOM_FUME_BAND_NOISE}',{SILENCE_FILTER}",
        "desc": "afftdn (nr=18, nt=custom fume profile)",
    },
}


def process_audio_with_filter(
    audio_path: str | Path,
    filter_id: str,
    temp_dir: str | Path,
    snr_threshold_tau: float = 15.0,
    gated_active_filter_id: str = "afftdn_nr12_custom",
) -> tuple[str, dict]:
    """
    Processes `audio_path` according to `filter_id` (including `D8_snr_gated`).
    Returns (path_to_processed_audio, metadata_dict).
    """
    snr_info = estimate_blind_snr(audio_path)
    out_wav = Path(temp_dir) / f"proc_{Path(audio_path).stem}_{filter_id}.wav"

    if filter_id == "D8_snr_gated":
        if snr_info["snr_db"] >= snr_threshold_tau:
            # Clean speech detected -> Bypass spectral denoiser to preserve short consonant/vowel formants
            chosen_id = "F0_no_filter"
            gated_decision = "bypass_clean"
        else:
            # Noisy speech detected -> Route through optimal denoiser
            chosen_id = gated_active_filter_id
            gated_decision = f"denoise_active ({chosen_id})"
    else:
        chosen_id = filter_id
        gated_decision = "static"

    cfg = FILTER_CONFIGS[chosen_id]
    if cfg["type"] == "none":
        return str(audio_path), {**snr_info, "chosen_filter": chosen_id, "gated_decision": gated_decision}
    elif cfg["type"] == "ffmpeg":
        apply_ffmpeg_filter(audio_path, cfg["af"], out_wav)
        return str(out_wav), {**snr_info, "chosen_filter": chosen_id, "gated_decision": gated_decision}
    elif cfg["type"] == "scipy_stft":
        apply_spectral_gating_scipy(audio_path, out_wav)
        return str(out_wav), {**snr_info, "chosen_filter": chosen_id, "gated_decision": gated_decision}
    else:
        raise ValueError(f"Unknown filter type: {cfg['type']}")
