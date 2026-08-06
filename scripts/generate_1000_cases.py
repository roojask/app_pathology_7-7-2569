import os
import sys
import json
import random
import time
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
DATASET_DIR = BASE_DIR / "data" / "dataset_1000"
AUDIO_DIR = DATASET_DIR / "audio"
GT_JSON_PATH = DATASET_DIR / "ground_truth_1000.json"

try:
    import audioop
except ImportError:
    import audioop_lts as audioop
    sys.modules["audioop"] = audioop

try:
    from gtts import gTTS
    from pydub import AudioSegment
    import numpy as np
except ImportError:
    print("Installing dependencies...")
    os.system(f"{sys.executable} -m pip install gTTS pydub numpy audioop-lts")
    from gtts import gTTS
    from pydub import AudioSegment
    import numpy as np

# Ensure directories exist
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

SIDES = ["right", "left"]
PROCS = ["modified radical mastectomy", "simple mastectomy"]
QUADRANTS = ["upper inner", "upper outer", "lower inner", "lower outer", "central"]
ACCENTS = ["en-us", "en-uk", "en-au", "en-in", "th"]

def generate_case_text_and_gt(case_id, category_idx):
    surg_no = f"S-24-{1000 + case_id}"
    side = random.choice(SIDES)
    proc_raw = random.choice(PROCS)
    proc_val = "modified" if "modified" in proc_raw else "simple"
    
    # 3D dims
    d1, d2, d3 = round(random.uniform(5, 30), 1), round(random.uniform(5, 25), 1), round(random.uniform(2, 15), 1)
    d3d_str = f"{d1}x{d2}x{d3}"
    
    # 2D skin dims
    sd1, sd2 = round(random.uniform(5, 20), 1), round(random.uniform(2, 10), 1)
    
    # Mass dims
    md1, md2, md3 = round(random.uniform(1, 8), 1), round(random.uniform(1, 6), 1), round(random.uniform(1, 5), 1)
    
    # Lymph nodes
    node_count = random.randint(3, 20)
    n_min = round(random.uniform(0.1, 0.8), 1)
    n_max = round(random.uniform(1.0, 3.5), 1)
    
    quad = random.choice(QUADRANTS)
    
    # Template categories
    if category_idx == 1:
        # Standard
        text = f"Surgical number {surg_no}. Received in formalin is a {side} {proc_raw} specimen measuring {d3d_str} cm. The skin ellipse measures {sd1}x{sd2} cm and appears normal. There is an infiltrative firm yellow white mass measuring {md1}x{md2}x{md3} cm at the {quad} quadrant. Deep margin is {round(random.uniform(0.2, 3.0),1)} cm. {node_count} lymph nodes ranging from {n_min} to {n_max} cm are identified."
    elif category_idx == 2:
        # Out-of-order
        text = f"An infiltrative mass measuring {md1}x{md2}x{md3} cm is found at {quad} quadrant. Specimen is {side} {proc_raw} measuring {d3d_str} cm. Surgical number {surg_no}. Skin ellipse {sd1}x{sd2} cm. Deep margin 1.5 cm. {node_count} lymph nodes ranging from {n_min} to {n_max} cm."
    elif category_idx == 3:
        # Self-correction
        text = f"Surgical number {surg_no}. Received specimen right... sorry left {proc_raw} measuring {d3d_str} cm. Mass size is 2x2... correction {md1}x{md2}x{md3} cm. Skin appears normal. Lymph nodes {node_count} nodes."
    elif category_idx == 4:
        # Multi-margin
        text = f"Specimen {surg_no} is a {side} {proc_raw} measuring {d3d_str} cm. Skin ellipse {sd1}x{sd2} cm. Mass {md1}x{md2}x{md3} cm at {quad} quadrant. Deep margin 1.0 cm, superior margin 2.0 cm, inferior margin 1.5 cm, medial margin 0.5 cm, lateral margin 2.5 cm."
    elif category_idx == 5:
        # Lymph node heavy
        text = f"Surgical number {surg_no}. {side} {proc_raw} measuring {d3d_str} cm with axillary content. Identified {node_count} lymph nodes ranging from {n_min} to {n_max} cm in greatest dimension."
    elif category_idx == 6:
        # Unremarkable / Fibrocystic
        text = f"Surgical number {surg_no}. Received {side} {proc_raw} measuring {d3d_str} cm. Sectioning reveals no discrete mass, entirely fibrocystic change. Unremarkable parenchyma."
    elif category_idx == 7:
        # High speed compact
        text = f"{surg_no} {side} {proc_raw} {d3d_str}cm mass {md1}x{md2}x{md3}cm {quad} quadrant skin {sd1}x{sd2}cm deep margin 1.5cm {node_count} nodes."
    elif category_idx == 8:
        # Fume hood noise context
        text = f"Surgical number {surg_no}. Received in formalin {side} {proc_raw} measuring {d3d_str} cm. Infiltrative yellow white mass {md1}x{md2}x{md3} cm. Deep margin 1.0 cm."
    elif category_idx == 9:
        # Thai-English Mixed
        text = f"ชิ้นเนื้อ surgical number {surg_no} ข้าง {side} {proc_raw} ขนาด {d3d_str} cm. พบ mass ขนาด {md1}x{md2}x{md3} cm บริเวณ {quad} quadrant. สกัดได้ lymph nodes {node_count} nodes."
    else:
        # Edge cases
        text = f"Specimen {surg_no} {side} mastectomy measuring {d3d_str} cm. Infiltrative mass identified without dimensions. Deep margin 1.2 cm."

    gt = {
        "s0_surgical_no": surg_no,
        "s1_side": side,
        "s2_proc": proc_val,
        "s3_dims": [str(d1), str(d2), str(d3)],
        "s10_infiltrative": True if category_idx != 6 else False,
        "s14_check": True if category_idx in [1, 2, 3, 5, 7] else False,
        "raw_text": text
    }
    
    return text, gt

def create_synthetic_fume_hood_noise(duration_ms):
    # Create white noise with low-pass filter to simulate fume hood fan hum
    sample_rate = 22050
    num_samples = int(sample_rate * (duration_ms / 1000.0))
    noise_samples = np.random.normal(0, 0.08, num_samples)
    noise_int16 = (noise_samples * 32767).astype(np.int16)
    noise_segment = AudioSegment(
        noise_int16.tobytes(),
        frame_rate=sample_rate,
        sample_width=2,
        channels=1
    )
    return noise_segment

def build_1000_dataset(max_cases=1000):
    print("==================================================")
    print(f"[DATASET GENERATOR] Building {max_cases} Diverse Pathology Audio Cases...")
    print("==================================================")
    
    all_gt = {}
    start_time = time.time()
    
    for i in range(1, max_cases + 1):
        cat_idx = ((i - 1) % 10) + 1
        accent = random.choice(ACCENTS)
        lang = "th" if "Thai" in f"cat_{cat_idx}" or accent == "th" else "en"
        tld = "com"
        if accent == "en-uk": tld = "co.uk"
        elif accent == "en-au": tld = "com.au"
        elif accent == "en-in": tld = "co.in"
        
        text, gt = generate_case_text_and_gt(i, cat_idx)
        gt["case_id"] = i
        gt["category_id"] = cat_idx
        gt["accent"] = accent
        
        audio_filename = f"case_{i:04d}.mp3"
        audio_filepath = AUDIO_DIR / audio_filename
        gt["audio_filename"] = audio_filename
        
        all_gt[f"case_{i:04d}"] = gt
        
        # Generate Audio File via gTTS if not present
        if not audio_filepath.exists():
            try:
                tts = gTTS(text=text, lang=lang, tld=tld, slow=False)
                tts.save(str(audio_filepath))
                
                # Apply Fume Hood Noise to Category 8 and random 30% of cases
                if cat_idx == 8 or random.random() < 0.3:
                    speech = AudioSegment.from_file(str(audio_filepath))
                    bg_noise = create_synthetic_fume_hood_noise(len(speech))
                    combined = speech.overlay(bg_noise - 10)
                    combined.export(str(audio_filepath), format="mp3")
                    
            except Exception as e:
                pass

        if i % 100 == 0 or i == max_cases:
            elapsed = time.time() - start_time
            print(f"  • Progress: {i} / {max_cases} cases generated ({elapsed:.1f}s)")
            
    # Save Ground Truth JSON
    with open(GT_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(all_gt, f, ensure_ascii=False, indent=2)
        
    print("\n==================================================")
    print(f"[SUCCESS] 1,000 Case Dataset Successfully Generated!")
    print(f"📁 Audio Folder: {AUDIO_DIR}")
    print(f"📄 Ground Truth JSON: {GT_JSON_PATH}")
    print("==================================================")

if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
    build_1000_dataset(n)
