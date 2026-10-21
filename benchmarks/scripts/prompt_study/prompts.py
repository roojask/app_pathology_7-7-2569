"""
prompts.py  --  prompt variants for the Prompt Sensitivity Study.

Each variant answers one question:
  P0  none            : baseline
  P1  generic         : is naming the domain enough?
  P2  keywords        : is sentence structure needed, or just vocabulary?
  P3a format_only     : non-medical numbers/units only -> pure FORMAT effect
  P3b fewshot_clinical: clinical sentences with different values
  P4  full_cap        : current system prompt (Config.PATHOLOGY_PROMPT)
  P5  placebo         : unrelated English, same token length as P4
  P6  shuffled        : P4 words in random order (same vocabulary, no grammar)
  P7  no_contrastive  : P4 without right/left and everted/inverted
  P8  adversarial     : cardiology vocabulary (wrong domain)

faster-whisper keeps only the LAST 223 tokens of a prompt (it truncates from
the START), so every variant is checked to be <= 223 tokens.

build_variants(count_tokens) needs a token counter (see run_prompt_sweep.py).
Before running the TEST split, check that no number in P3a/P3b appears as a
ground-truth value in the test cases (see check_value_overlap in the runner).
"""
import random

MAX_PROMPT_TOKENS = 223

KEYWORDS = (
    "mastectomy, lumpectomy, formalin, infiltrative, axillary, fibrocystic, "
    "subareolar, quadrant, superior, inferior, medial, lateral, deep, margin, "
    "lymph nodes, residual mass, paraffin, specimen, skin ellipse, nipple, "
    "ulceration, circumscribed, centimeters, cm, millimeters, mm"
)

FORMAT_ONLY = (
    "The box measures 12.5 x 8.0 x 3.5 cm and weighs 450 g. "
    "The gap is 0.6 cm. The tube is 15 mm wide and 7.2 cm long."
)

FEWSHOT_CLINICAL = (
    "Received in formalin is a left lumpectomy specimen measuring 6.5 x 4.0 x 2.5 cm. "
    "Infiltrative mass measuring 1.4 x 1.2 x 0.9 cm in the lower inner quadrant, "
    "0.6 cm from the deep margin. Axillary contents with 3 lymph nodes, the largest 0.8 cm."
)

PLACEBO_SOURCE = (
    "The garden behind the old house was quiet in the early morning. "
    "A gentle wind moved through the tall grass near the river, and the first "
    "train of the day crossed the bridge on its way to the coast. "
    "In the kitchen, bread was cooling on the table next to a bowl of ripe fruit. "
    "The children walked to school along the main road, talking about the weekend "
    "and the football match. Later the market opened, and farmers arrived with "
    "baskets of vegetables, flowers, and fresh eggs. "
)

ADVERSARIAL = (
    "Echocardiography report. Left ventricular ejection fraction is reduced. "
    "Mitral regurgitation, aortic stenosis, atrial fibrillation, coronary artery "
    "stent, pericardial effusion. Blood pressure in millimeters of mercury. "
    "Right atrium, right ventricle, septum, apex, papillary muscle."
)


def _remove(text, old, new=""):
    assert old in text, f"expected substring not found in P4: {old!r}"
    return text.replace(old, new)


def make_no_contrastive(p4):
    t = p4
    t = _remove(t, "is a right modified radical mastectomy", "is a modified radical mastectomy")
    t = _remove(t, "Left simple mastectomy. ", "")
    t = _remove(t, "The nipple is everted, inverted, unremarkable, shows ulceration.",
                "The nipple is unremarkable.")
    return " ".join(t.split())


def make_shuffled(p4, seed=0):
    words = p4.split()
    random.Random(seed).shuffle(words)
    return " ".join(words)


def make_placebo(target_tokens, count_tokens):
    words = (PLACEBO_SOURCE * 6).split()
    while len(words) > 1 and count_tokens(" ".join(words)) > target_tokens:
        words.pop()
    return " ".join(words)


def build_variants(p4_text, count_tokens):
    """Return ordered dict {variant_name: prompt_or_None}. Asserts token limits."""
    p4_tokens = count_tokens(p4_text)
    variants = {
        "P0_none": None,
        "P1_generic": "Medical dictation.",
        "P2_keywords": KEYWORDS,
        "P3a_format_only": FORMAT_ONLY,
        "P3b_fewshot_clinical": FEWSHOT_CLINICAL,
        "P4_full_cap": p4_text,
        "P5_placebo": make_placebo(p4_tokens, count_tokens),
        "P6_shuffled": make_shuffled(p4_text),
        "P7_no_contrastive": make_no_contrastive(p4_text),
        "P8_adversarial": ADVERSARIAL,
    }
    for name, p in variants.items():
        if p is not None:
            n = count_tokens(p)
            assert n <= MAX_PROMPT_TOKENS, f"{name} has {n} tokens (> {MAX_PROMPT_TOKENS})"
    return variants
