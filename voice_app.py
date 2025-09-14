# streamlit run app.py
import streamlit as st
import json, os, io, math, struct, re
import speech_recognition as sr
from dataclasses import dataclass
from typing import List, Tuple, Optional

# ----- Optional dependencies (robust noise reduction & fuzzy matching) -----
try:
    import webrtcvad  # VAD-based speech gating
    HAS_VAD = True
except Exception:
    HAS_VAD = False

try:
    import numpy as np
    import noisereduce as nr  # spectral noise reducer (optional)
    HAS_NR = True
except Exception:
    HAS_NR = False

try:
    from rapidfuzz import process, fuzz
    HAS_FUZZ = True
except Exception:
    import difflib
    HAS_FUZZ = False

# ===============================
# Streamlit Config
# ===============================
st.set_page_config(page_title="Voice Medicine Selector", page_icon="🎤", layout="centered")
st.markdown(
    """
    <h1 style='text-align:center; color:#2C3E50;'>🎤 Voice-based Medicine Selector</h1>
    <p style='text-align:center; color:#7F8C8D;'>Speak or type a medicine → pick a variant → save</p>
    """,
    unsafe_allow_html=True
)

# ===============================
# Load Medicine DB
# ===============================
DB_FILE = "medicine_db.json"
if os.path.exists(DB_FILE):
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            MED_DB = json.load(f)
    except json.JSONDecodeError:
        st.error("⚠️ Medicine database JSON is corrupted!")
        MED_DB = {}
else:
    st.error("⚠️ Medicine database file not found!")
    MED_DB = {}

ALL_MED_NAMES = sorted(MED_DB.keys())
ALL_MED_NAMES_LOWER = [m.lower() for m in ALL_MED_NAMES]

# ===============================
# Session State
# ===============================
ss = st.session_state
ss.setdefault("medicine_name", None)
ss.setdefault("spoken_text", None)
ss.setdefault("selected_variant", None)
ss.setdefault("quantity", 1)
ss.setdefault("unit", "pack")
ss.setdefault("suggestions", [])
ss.setdefault("last_recog_conf", None)

recognizer = sr.Recognizer()
# Robust recognition settings
recognizer.dynamic_energy_threshold = True
recognizer.pause_threshold = 0.6
recognizer.non_speaking_duration = 0.3

# ===============================
# Audio helpers
# ===============================
@dataclass
class PCM:
    rate: int
    width: int   # bytes per sample (2 for int16)
    data: bytes  # little-endian signed PCM mono

def audio_to_pcm(audio: sr.AudioData, target_rate=16000, target_width=2) -> PCM:
    raw = audio.get_raw_data(convert_rate=target_rate, convert_width=target_width)
    return PCM(rate=target_rate, width=target_width, data=raw)

def pcm_bytes_to_np(pcm: PCM) -> np.ndarray:
    # int16 mono -> float32 [-1, 1]
    arr = np.frombuffer(pcm.data, dtype=np.int16).astype(np.float32) / 32768.0
    return arr

def np_to_pcm_bytes(arr: np.ndarray) -> bytes:
    arr16 = (np.clip(arr, -1.0, 1.0) * 32767.0).astype(np.int16)
    return arr16.tobytes()

def apply_vad_gating(pcm: PCM, aggressiveness=2, frame_ms=30) -> PCM:
    """Keep voiced frames only. If VAD unavailable, return pcm unchanged."""
    if not HAS_VAD:
        return pcm
    vad = webrtcvad.Vad(aggressiveness)
    sample_rate = pcm.rate
    bytes_per_frame = int(sample_rate * (frame_ms / 1000.0)) * pcm.width
    data = pcm.data
    # pad to full frames
    if len(data) % bytes_per_frame:
        pad = bytes_per_frame - (len(data) % bytes_per_frame)
        data += b"\x00" * pad
    frames = [data[i:i+bytes_per_frame] for i in range(0, len(data), bytes_per_frame)]
    voiced = []
    # simple keep/remove; (optionally add hangover to keep small silences)
    HANG = 3
    keep_count = 0
    for fr in frames:
        is_speech = vad.is_speech(fr, sample_rate)
        if is_speech:
            keep_count = HANG
            voiced.append(fr)
        else:
            if keep_count > 0:
                voiced.append(fr)
                keep_count -= 1
    out = b"".join(voiced) if voiced else pcm.data
    return PCM(rate=sample_rate, width=pcm.width, data=out)

def spectral_denoise(pcm: PCM, prop_decrease=0.7) -> PCM:
    """Optional spectral denoise if noisereduce is installed."""
    if not (HAS_NR and np is not None):
        return pcm
    y = pcm_bytes_to_np(pcm)
    # Estimate noise as first 0.5s (or less if short)
    n_samples = min(len(y), int(0.5 * pcm.rate))
    noise_clip = y[:n_samples] if n_samples > 0 else y
    y_denoised = nr.reduce_noise(y=y, y_noise=noise_clip, sr=pcm.rate,
                                 prop_decrease=prop_decrease, stationary=False)
    return PCM(rate=pcm.rate, width=pcm.width, data=np_to_pcm_bytes(y_denoised))

def clean_recognizer_text(t: str) -> str:
    t = t.strip().lower()
    t = re.sub(r"[^a-z0-9\s\-]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t

def fuzzy_candidates(q: str, choices: List[str], topn=5) -> List[Tuple[str, float]]:
    if not q or not choices:
        return []
    if HAS_FUZZ:
        matches = process.extract(q, choices, scorer=fuzz.WRatio, limit=topn)
        # matches -> [(choice, score, idx)]
        return [(m[0], float(m[1])) for m in matches]
    else:
        # fallback to difflib
        cands = difflib.get_close_matches(q, choices, n=topn, cutoff=0.0)
        return [(c, 100.0 * difflib.SequenceMatcher(None, q, c).ratio()) for c in cands]

def best_match(q: str, choices: List[str], threshold=80.0) -> Tuple[Optional[str], List[Tuple[str, float]]]:
    cands = fuzzy_candidates(q, choices, topn=5)
    best = cands[0][0] if cands and cands[0][1] >= threshold else None
    return best, cands

# ===============================
# UI: Voice Input
# ===============================
colA, colB = st.columns([1,1])

with colA:
    if st.button("🎙️ Speak Medicine Name", use_container_width=True):
        with sr.Microphone(sample_rate=16000) as source:
            st.info("Listening… please speak clearly")
            try:
                recognizer.adjust_for_ambient_noise(source, duration=1.5)  # longer calibration
                audio = recognizer.listen(source, timeout=15, phrase_time_limit=8)

                # --- noise reduction pipeline ---
                pcm = audio_to_pcm(audio, target_rate=16000, target_width=2)
                pcm = apply_vad_gating(pcm, aggressiveness=2, frame_ms=30)
                pcm = spectral_denoise(pcm, prop_decrease=0.7)

                # Build cleaned AudioData for recognizer
                audio_clean = sr.AudioData(pcm.data, pcm.rate, pcm.width)

                try:
                    spoken = recognizer.recognize_google(audio_clean, language="en-US")
                except sr.UnknownValueError:
                    # fallback: try original audio if cleaned failed
                    spoken = recognizer.recognize_google(audio, language="en-US")

                spoken = clean_recognizer_text(spoken)
                ss.spoken_text = spoken

                # Fuzzy match to known names (lowercase map)
                best, cands = best_match(spoken, ALL_MED_NAMES_LOWER, threshold=78.0)
                ss.suggestions = [ALL_MED_NAMES[ALL_MED_NAMES_LOWER.index(c)] for c, _ in cands]
                ss.last_recog_conf = cands[0][1] if cands else None

                # --- No "You said/matched" or diagnostics shown ---
                ss.medicine_name = ALL_MED_NAMES[ALL_MED_NAMES_LOWER.index(best)] if best else spoken

            except sr.WaitTimeoutError:
                st.error("⌛ Timeout: you didn’t start speaking in time.")
            except sr.RequestError:
                st.error("⚠️ Speech service unavailable.")
            except Exception as e:
                st.error(f"🎛️ Audio error: {e}")

with colB:
    typed = st.text_input("⌨️ Or type the medicine name:", value=ss.medicine_name or "")
    if typed:
        typed_clean = clean_recognizer_text(typed)
        best, cands = best_match(typed_clean, ALL_MED_NAMES_LOWER, threshold=78.0)
        ss.suggestions = [ALL_MED_NAMES[ALL_MED_NAMES_LOWER.index(c)] for c, _ in cands]
        ss.medicine_name = ALL_MED_NAMES[ALL_MED_NAMES_LOWER.index(best)] if best else typed

# Suggestions (chips)
if ss.suggestions:
    sel = st.pills("Suggestions", options=ss.suggestions, selection_mode="single",
                   default=ss.suggestions[0] if ss.suggestions else None, key="pill_select") \
          if hasattr(st, "pills") else st.radio("Suggestions", options=ss.suggestions, index=0, horizontal=True)
    if sel:
        ss.medicine_name = sel

# ===============================
# Selection + Save
# ===============================
med_name = ss.medicine_name
if med_name:
    key = med_name if med_name in MED_DB else (med_name.lower() if med_name.lower() in MED_DB else None)

    if key:
        options = MED_DB[key]
        # Preserve selection if still present
        default_idx = options.index(ss.selected_variant) if ss.selected_variant in options else 0
        ss.selected_variant = st.selectbox("📋 Select final medicine:", options, index=default_idx)

        c1, c2 = st.columns(2)
        with c1:
            ss.quantity = st.number_input("📦 Quantity", min_value=1, value=ss.quantity)
        with c2:
            ss.unit = st.selectbox("⚖️ Unit", ["pack", "bottle", "strip", "box"],
                                   index=["pack","bottle","strip","box"].index(ss.unit))

        if st.button("✅ Submit", type="primary"):
            entry = {
                "medicine_name": key,
                "selected_variant": ss.selected_variant,
                "quantity": ss.quantity,
                "unit": ss.unit
            }
            # Append to purchases.json
            fp = "purchases.json"
            try:
                if os.path.exists(fp):
                    with open(fp, "r", encoding="utf-8") as f:
                        all_data = json.load(f)
                else:
                    all_data = []
            except json.JSONDecodeError:
                all_data = []

            all_data.append(entry)
            with open(fp, "w", encoding="utf-8") as f:
                json.dump(all_data, f, indent=2, ensure_ascii=False)
            st.success("💾 Purchase saved!")
    else:
        st.error("❌ Medicine not found in database.")

# --- Diagnostics removed from UI ---
