import unittest
from src.nlp.extractor import extract_data_15_sections, generate_confidence_flags
from src.nlp.normalizer import normalize_text

class TestNLPExtraction(unittest.TestCase):
    def test_normalizer(self):
        raw = "SPECIMEN RECEIVED IN FORMALIN, MEASURING 5 BY 4 BY 3 CENTIMETERS"
        normalized = normalize_text(raw)
        self.assertIn("5 x 4 x 3", normalized)
        self.assertIn("cm", normalized)

    def test_extractor_structure(self):
        sample_text = (
            "Modified radical mastectomy specimen right breast. "
            "Skin ellipse measures 15 x 10 cm. Nipple is everted. "
            "Infiltrative firm yellow-white mass measuring 2.5 x 2.0 x 1.5 cm at upper outer quadrant. "
            "Deep margin is 1.5 cm from mass. 12 lymph nodes found."
        )
        data = extract_data_15_sections(sample_text)
        self.assertIsInstance(data, dict)
        self.assertEqual(data.get("s1_side"), "right")
        self.assertEqual(data.get("s2_proc"), "modified")


    def test_confidence_flags(self):
        sample_data = {
            "Section 1: Specimen Type": "Modified radical mastectomy",
            "Section 2: Specimen Integrity": "Intact",
            "Section 6: Mass Location": "Upper outer quadrant"
        }
        flags = generate_confidence_flags(sample_data)
        self.assertIsInstance(flags, dict)

if __name__ == "__main__":
    unittest.main()
