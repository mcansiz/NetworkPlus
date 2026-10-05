"""Release notu: .github/release-notes.md sablonunu doldurup stdout'a yazar (release.yml).

    python3 .github/release_notes.py <surum> <etiket> <depo> <kosu-url> <macos-satiri> <macos-tr>
"""

import sys
from pathlib import Path

ver, tag, repo, run, row, tr = sys.argv[1:7]
text = (Path(__file__).parent / "release-notes.md").read_text(encoding="utf-8")
for key, value in (("{VERSION}", ver), ("{TAG}", tag), ("{REPO}", repo),
                   ("{RUN_URL}", run), ("{MACOS_ROW}", row), ("{MACOS_TR}", tr)):
    text = text.replace(key, value)
sys.stdout.reconfigure(encoding="utf-8")
sys.stdout.write(text)
