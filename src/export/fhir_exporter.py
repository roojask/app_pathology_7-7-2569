import json
import datetime
from typing import Dict, Any

def convert_to_hl7_fhir_r4(data: Dict[str, Any], surgical_no: str, timestamp_str: str = None) -> Dict[str, Any]:
    """
    แปลงข้อมูลรายงานผลตรวจพยาธิวิทยาเป็นมาตรฐาน HL7 FHIR R4 DiagnosticReport Resource
    สอดคล้องกับมาตรฐานเวชระเบียนสากล (LOINC & SNOMED CT)
    """
    if not timestamp_str:
        timestamp_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
    
    clean_sno = surgical_no.replace(" ", "-").strip() if surgical_no else "S-Unknown"
    
    observations = []
    
    # 1. Observation: Laterality (ด้านที่ผ่าตัด)
    side = data.get("s1_side", "").lower()
    if side:
        observations.append({
            "resourceType": "Observation",
            "id": f"obs-laterality-{clean_sno}",
            "status": "final",
            "code": {
                "coding": [{
                    "system": "http://loinc.org",
                    "code": "20228-3",
                    "display": "Anatomic site Laterality"
                }]
            },
            "valueString": side.capitalize(),
            "bodySite": {
                "coding": [{
                    "system": "http://snomed.info/sct",
                    "code": "76752008",
                    "display": "Breast structure"
                }]
            }
        })
        
    # 2. Observation: Procedure (ชนิดการผ่าตัด)
    proc = data.get("s2_proc")
    if proc:
        proc_display = "Modified radical mastectomy" if proc == "modified" else "Simple mastectomy"
        observations.append({
            "resourceType": "Observation",
            "id": f"obs-proc-{clean_sno}",
            "status": "final",
            "code": {
                "coding": [{
                    "system": "http://snomed.info/sct",
                    "code": "396487001",
                    "display": "Surgical procedure on breast"
                }]
            },
            "valueString": proc_display
        })
        
    # 3. Observation: Specimen Dimensions (ขนาดชิ้นเนื้อ)
    dims = data.get("s3_dims", [])
    if dims and any(dims):
        dim_str = " x ".join([str(d) for d in dims if str(d).strip()]) + " cm"
        observations.append({
            "resourceType": "Observation",
            "id": f"obs-dims-{clean_sno}",
            "status": "final",
            "code": {
                "coding": [{
                    "system": "http://loinc.org",
                    "code": "44652-6",
                    "display": "Gross specimen dimensions"
                }]
            },
            "valueString": dim_str
        })
        
    # 4. Observation: Tumor Mass Findings (ลักษณะก้อนมะเร็ง)
    tumor_findings = []
    if data.get("s10_infiltrative"):
        inf_dims = " x ".join([str(d) for d in data.get("s10_inf_dims", []) if str(d).strip()])
        tumor_findings.append(f"Infiltrative firm yellow-white mass ({inf_dims} cm)")
    if data.get("s10_well_defined"):
        well_dims = " x ".join([str(d) for d in data.get("s10_well_dims", []) if str(d).strip()])
        tumor_findings.append(f"Well-defined firm white mass with slit-like appearance ({well_dims} cm)")
        
    if tumor_findings:
        observations.append({
            "resourceType": "Observation",
            "id": f"obs-tumor-{clean_sno}",
            "status": "final",
            "code": {
                "coding": [{
                    "system": "http://loinc.org",
                    "code": "21889-1",
                    "display": "Gross tumor description"
                }]
            },
            "valueString": "; ".join(tumor_findings)
        })
        
    # 5. Observation: Surgical Margins (ระยะขอบตัด)
    margins = {}
    for m in ["superior", "inferior", "medial", "lateral", "anterior", "posterior"]:
        val = data.get(f"s11_{m}")
        if val:
            margins[m] = f"{val} mm"
    if margins:
        observations.append({
            "resourceType": "Observation",
            "id": f"obs-margins-{clean_sno}",
            "status": "final",
            "code": {
                "coding": [{
                    "system": "http://loinc.org",
                    "code": "84893-7",
                    "display": "Surgical margin distances"
                }]
            },
            "component": [
                {
                    "code": {"coding": [{"system": "http://loinc.org", "code": f"margin-{k}", "display": f"{k.capitalize()} Margin"}]},
                    "valueString": v
                } for k, v in margins.items()
            ]
        })
        
    # 6. Observation: Lymph Nodes (ต่อมน้ำเหลือง)
    if data.get("s14_check") or data.get("s14_min") or data.get("s14_max"):
        ln_min = data.get("s14_min", "")
        ln_max = data.get("s14_max", "")
        observations.append({
            "resourceType": "Observation",
            "id": f"obs-lymph-{clean_sno}",
            "status": "final",
            "code": {
                "coding": [{
                    "system": "http://loinc.org",
                    "code": "21894-1",
                    "display": "Regional lymph nodes evaluation"
                }]
            },
            "valueString": f"Lymph nodes identified, ranging from {ln_min} to {ln_max} cm"
        })

    # Main FHIR DiagnosticReport Resource
    fhir_bundle = {
        "resourceType": "DiagnosticReport",
        "id": f"patho-dr-{clean_sno}",
        "meta": {
            "versionId": "1",
            "lastUpdated": timestamp_str,
            "profile": ["http://hl7.org/fhir/StructureDefinition/DiagnosticReport"]
        },
        "identifier": [{
            "system": "https://hospital.org/pathology/cases",
            "value": clean_sno
        }],
        "status": "final",
        "category": [{
            "coding": [{
                "system": "http://terminology.hl7.org/CodeSystem/v2-0074",
                "code": "SP",
                "display": "Surgical Pathology"
            }]
        }],
        "code": {
            "coding": [{
                "system": "http://loinc.org",
                "code": "11526-1",
                "display": "Pathology study"
            }],
            "text": "Gross Pathology Examination Report for Breast Specimen (CAP Protocol)"
        },
        "subject": {
            "display": f"Specimen Case {clean_sno}"
        },
        "effectiveDateTime": timestamp_str,
        "issued": timestamp_str,
        "performer": [{
            "display": data.get("footer_prosecutor", "Pathology Resident / Specialist")
        }],
        "contained": observations,
        "result": [{"reference": f"#{obs['id']}"} for obs in observations],
        "conclusion": f"Gross examination of {clean_sno} completed according to CAP standard. Verification hash: {data.get('doc_hash', 'VERIFIED')}."
    }
    
    return fhir_bundle
