# Voice-based Medicine Selector

A Streamlit app that lets you **speak or type** a medicine name, suggests close matches from a local JSON database, lets you pick an exact **variant**, set **quantity + unit**, and then **saves** your selection to `purchases.json`.

> UI entry point: `streamlit run app.py`

---

## ✨ Features

- 🎤 **Voice input** using `SpeechRecognition` (Google Web Speech backend)
- 🔎 **Fuzzy matching** of medicine names (RapidFuzz or `difflib` fallback)
- 🧠 **Suggestions** list to quickly pick the right brand/strength
- 🧪 **Optional noise handling**
  - **VAD gating** via `webrtcvad`
  - **Spectral denoise** via `noisereduce`
- 💾 **Persists** selections to `purchases.json`
- 🧰 **Graceful fallbacks** if optional deps are missing

---

## 🗂️ Repository Layout (minimal)

```
.
├── app.py               # Streamlit app (your provided code)
├── medicine_db.json     # Local database of medicine → variants
└── README.md            # This file
```

---

## 📦 Requirements

- Python **3.9 – 3.12**
- Microphone access (for voice input)
- Internet connection for Google Web Speech (used by `SpeechRecognition`)

### Core Python packages
- `streamlit`
- `SpeechRecognition`

### Optional (recommended) packages
- `webrtcvad` — VAD-based speech gating
- `numpy` — needed for denoising
- `noisereduce` — spectral noise reduction
- `rapidfuzz` — fast, robust fuzzy matching

> If any optional package is missing, the app will **still run** with reduced functionality.

### System packages (OS-specific)
- **PortAudio** (for mic access used by PyAudio inside `SpeechRecognition`):
  - macOS: `brew install portaudio`
  - Ubuntu/Debian: `sudo apt-get install portaudio19-dev python3-pyaudio`
  - Windows: install Python wheels for `pyaudio` if needed (see Troubleshooting)

---

## ⚙️ Installation

1) **Create & activate a virtual environment** (recommended):

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate
```

2) **Install dependencies**:

**Minimal install:**
```bash
pip install streamlit SpeechRecognition
```

**With optional goodies:**
```bash
pip install streamlit SpeechRecognition rapidfuzz numpy noisereduce webrtcvad
```

> If `webrtcvad` fails to build on Windows, you can skip it; the app will fall back automatically.

3) **Place your data file**: ensure a `medicine_db.json` is in the project root (schema below).

4) **Run the app**:
```bash
streamlit run app.py
```

---

## 📁 Data Files

### `medicine_db.json` (input)

The app reads a **flat dictionary** where keys are medicine names and values are arrays of variant strings.

**Example:**
```json
{
  "Paracetamol": [
    "Paracetamol 500mg Tablet",
    "Paracetamol Syrup 125mg/5ml",
    "Paracetamol Injection 150mg",
    "Paracetamol Extra 650mg"
  ],
  "Omeprazole": [
    "Omeprazole 20mg Capsule",
    "Omeprazole 40mg Tablet",
    "Omeprazole Injection 40mg"
  ]
}
```

- Keys can be in **any case**; matching is done case-insensitively.
- If the file is missing or corrupted, the app shows an **error** in the UI.

### `purchases.json` (output)

An array of records; each record is saved when you click **Submit**:

```json
[
  {
    "medicine_name": "Paracetamol",
    "selected_variant": "Paracetamol 500mg Tablet",
    "quantity": 2,
    "unit": "strip"
  }
]
```

> The file is **appended** to on each submit, and created if it doesn’t exist.

---

## 🧭 How to Use

1. Click **🎙️ Speak Medicine Name** and say the brand/generic (e.g., “Paracetamol”), or type it in the input field.
2. The app will **normalize** your text and run **fuzzy matching** against all known medicines from `medicine_db.json`.
3. Pick a **suggestion** (chips/radio) if offered.
4. Choose the **exact variant**, set **Quantity** and **Unit**.
5. Click **✅ Submit** to save to `purchases.json`.

---

## 🔧 Configuration knobs (in code)

- **VAD aggressiveness**: `apply_vad_gating(..., aggressiveness=2)` → set `0–3` (3 = most aggressive).
- **Fuzzy threshold**: `best_match(..., threshold=78.0)` → raise to be stricter, lower to be looser.
- **Pause/silence behavior**: `recognizer.pause_threshold`, `recognizer.non_speaking_duration`.
- **Denoise strength**: `spectral_denoise(..., prop_decrease=0.7)`.

All of the above live in **`app.py`**.

---

## 🧪 Adding More Medicines

Just edit **`medicine_db.json`** and add more keys + variant arrays.

**Template to copy:**
```json
"Azithromycin": [
  "Azithromycin 250mg Tablet",
  "Azithromycin 500mg Tablet",
  "Azithromycin Suspension 200mg/5ml"
]
```

> After editing, **refresh** the Streamlit app tab (or restart) to load new entries.

---

## 🛠️ Troubleshooting

**Q: Mic permission denied / no audio device**  
- Grant the browser/system mic permission for Python/Terminal or your default input device.
- On macOS, check *System Settings → Privacy & Security → Microphone*.

**Q: `pyaudio` or PortAudio errors**  
- Install system libs first (see Requirements). On Windows, try prebuilt wheels for your Python version.

**Q: `webrtcvad` build fails**  
- It’s optional—skip it. The app will still work without VAD.

**Q: Voice recognition says service unavailable**  
- The Google Web Speech endpoint failed temporarily. Try again or check your network connection.

**Q: JSON corrupted**  
- The app shows: “Medicine database JSON is corrupted!” Fix the JSON format (quotes, commas, arrays).

---

## 🔍 How It Works (internals)

- **Audio capture →** optional **VAD gating** → optional **spectral denoise** → Google speech recognition.
- The recognized text is **cleaned** (`lowercase`, alnum + hyphen, whitespace) and then matched against the **lowercased** list of medicines using **RapidFuzz** (or `difflib` fallback).
- Suggestions use top-5 candidates; the **best** (>= threshold) is auto-selected if confident.
- Final selection + quantity/unit are **persisted** to `purchases.json`.

---

## 🧱 Limitations

- Uses the **online** Google Web Speech backend (no offline ASR).
- Not a medical device; list is limited to what’s in `medicine_db.json`.
- No dosage checks or clinical decision support.

---

## 🗺️ Roadmap (ideas)

- Offline ASR (e.g., Vosk, Whisper small) as a fallback
- Bengali language support toggle
- Import/export CSV for `purchases.json`
- Basic admin UI for managing `medicine_db.json`

---

## 📄 License

Choose and add a license (e.g., MIT).

---

## 🙏 Acknowledgments

- [Streamlit](https://streamlit.io/)
- [SpeechRecognition](https://pypi.org/project/SpeechRecognition/)
- [RapidFuzz](https://github.com/maxbachmann/RapidFuzz)
- [noisereduce](https://github.com/timsainb/noisereduce)
- [webrtcvad](https://github.com/wiseman/py-webrtcvad)

---

## ▶️ One-liner Quickstart

```bash
pip install streamlit SpeechRecognition rapidfuzz numpy noisereduce webrtcvad && streamlit run app.py
```
