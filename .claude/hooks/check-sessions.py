#!/usr/bin/env python3
"""SessionStart kancasi: oturum gecmisi projeye bagli mi? (salt okunur, hicbir sey degistirmez)

~/.claude/projects/<slug> klasoru .claude/sessions/<slug> icine junction/symlink
ile bagliysa SESSIZ kalir. Bagli degilse Claude'a tek satirlik hatirlatma yazar;
Claude kullaniciya kurulum komutunu soyler (ai_rules/60).

Kurulum makine basina BIR KEZ yapilir; sonra bu kanca hic konusmaz.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def slugify(path: str) -> str:
    s = path.rstrip("\\/")
    for ch in (":", "\\", "/", "_", "."):
        s = s.replace(ch, "-")
    return s


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}
    project = Path(os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or ".").resolve()
    projects = Path.home() / ".claude" / "projects"
    if not projects.is_dir():
        return 0
    slug = slugify(str(project)).lower()
    entry = next((p for p in projects.iterdir() if p.name.lower() == slug), None)
    sessions = (project / ".claude" / "sessions").resolve()
    if entry is not None:
        try:
            target = Path(os.path.realpath(entry))
        except OSError:
            target = entry
        if str(target).lower().startswith(str(sessions).lower()):
            return 0                                   # bagli: sessiz
    print("[networkPlus] Oturum gecmisi henuz projeye bagli degil (~/.claude/projects altinda; "
          "30 gun sonra silinebilir). Kullaniciya hatirlat: Claude Code/VS Code kapaliyken proje "
          "dizininden BIR KEZ `python %USERPROFILE%\\.claude\\skills\\session-persistence\\scripts\\"
          "setup_sessions.py` calistirilmali (ai_rules/60).")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
