import glob
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
templates_dir = BASE_DIR / "templates"

cdn_url = "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css"
local_tag = "{{ url_for('static', filename='fontawesome/css/all.min.css') }}"

updated = 0
for p in templates_dir.glob("*.html"):
    with open(p, "r", encoding="utf-8") as f:
        content = f.read()
    if cdn_url in content:
        new_content = content.replace(cdn_url, local_tag)
        with open(p, "w", encoding="utf-8") as f:
            f.write(new_content)
        updated += 1
        print(f"Updated {p.name} to use local FontAwesome!")

print(f"Done! Localized {updated} templates for true 100% offline security.")
