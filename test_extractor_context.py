"""Regression tests for context-based dimension assignment (extractor v2).
Run from the project root:  python test_extractor_context.py"""
from src.nlp.extractor import extract_data_15_sections as ex
CASES = [
 ("TC-D1 mass first (case_0002)", "An infiltrative mass measuring 5.2x4.0x3.3 cm is found at central quadrant. Specimen is right modified radical mastectomy measuring 7.1x21.7x11.6 cm. Surgical number S-24-1002.", ["7.1","21.7","11.6"], ["5.2","4.0","3.3"]),
 ("TC-D2 mass first (case_0012)", "An infiltrative mass measuring 2.9x5.1x3.8 cm is found at upper outer quadrant. Specimen is left simple mastectomy measuring 21.4x18.3x3.9 cm. Surgical number S-24-1012.", ["21.4","18.3","3.9"], ["2.9","5.1","3.8"]),
 ("TC-D3 specimen first", "Surgical number S-24-1001. Received is a right modified radical mastectomy specimen measuring 11.4x14.9x7.8 cm. There is an infiltrative firm mass measuring 1.7x1.1x4.3 cm at the lower outer quadrant.", ["11.4","14.9","7.8"], ["1.7","1.1","4.3"]),
 ("TC-D4 telegraphic", "S-24-1007 left modified radical mastectomy 14.9x6.0x12.7cm mass 7.4x2.1x1.3cm lower outer quadrant", ["14.9","6.0","12.7"], ["7.4","2.1","1.3"]),
 ("TC-D5 'by' separators, mass first", "There is a firm tumor measuring 3.0 by 2.0 by 1.5 cm in the upper inner quadrant. The left simple mastectomy specimen measures 20.0 by 15.0 by 5.0 cm overall.", ["20.0","15.0","5.0"], ["3.0","2.0","1.5"]),
 ("TC-D6 specimen only", "Received is a left simple mastectomy measuring 18.0x12.0x4.0 cm. No discrete mass, entirely fibrocystic change.", ["18.0","12.0","4.0"], None),
]
fail = 0
for name, text, spec, mass in CASES:
    p = ex(text); okS = p.get("s3_dims") == spec; okM = (p.get("s10_inf_dims") == mass)
    print(("PASS" if okS and okM else "FAIL"), name, "" if okS and okM else f"-> s3={p.get('s3_dims')} mass={p.get('s10_inf_dims')}")
    fail += not (okS and okM)
print(f"{len(CASES)-fail}/{len(CASES)} passed"); raise SystemExit(1 if fail else 0)
