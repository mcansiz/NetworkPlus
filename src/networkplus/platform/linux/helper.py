#!/usr/bin/env python3
"""networkPlus Linux uygulayicisi — KOK yetkisiyle calisir (pkexec).

BAGIMSIZ betiktir: yalnizca standart kutuphane; networkplus paketini import
ETMEZ (pkexec ortami temizler, PYTHONPATH gelmez).

Kullanim:  helper.py <plan.json> <calisma-dizini>
plan.json: {"apply": [adim...], "rollback": [adim...], "confirm_seconds": 30}
adim:      {"id": 1, "title": "...", "commands": [{"argv": [...], "ignore": false}]}

Protokol Windows betigiyle aynidir (platform/windows/apply.py):
  adimlar -> applied.json -> keep.flag / revert.flag bekle -> karar yoksa
  GERI AL -> final.json. Arayuz donsa ya da kapansa bile geri alma calisir.
Komutlar kabuk OLMADAN (argv listesi) calistirilir.
"""

import json
import os
import subprocess
import sys
import time

CMD_TIMEOUT_S = 90


def run_steps(steps):
    results = []
    env = dict(os.environ, LC_ALL="C", LANG="C")
    for step in steps:
        ok, error, warnings = True, None, []
        for cmd in step.get("commands") or []:
            argv = cmd["argv"]
            try:
                proc = subprocess.run(argv, capture_output=True, timeout=CMD_TIMEOUT_S, env=env)
                code = proc.returncode
                msg = (proc.stderr or proc.stdout).decode("utf-8", "replace").strip()
            except (OSError, subprocess.TimeoutExpired) as exc:
                code, msg = -1, str(exc)
            if code != 0:
                text = f"{' '.join(argv[:4])}…: {msg or f'kod {code}'}"
                if cmd.get("ignore"):
                    warnings.append(text)
                    continue
                ok, error = False, text
                break
        results.append({"id": step.get("id"), "title": step.get("title"), "ok": ok,
                        "error": error, "warnings": warnings})
    return results


def write_json(work_dir, name, obj):
    path = os.path.join(work_dir, name)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=1)
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)          # arayuz yarim dosya okumasin


def main(argv):
    for stream in (sys.stdout, sys.stderr):       # hata metni arayuze UTF-8 ulassin
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    plan_path, work_dir = argv[1], argv[2]
    with open(plan_path, encoding="utf-8") as fh:
        plan = json.load(fh)
    confirm = int(plan.get("confirm_seconds") or 0)
    rollback = plan.get("rollback") or []

    applied = run_steps(plan.get("apply") or [])
    write_json(work_dir, "applied.json", {"phase": "applied", "steps": applied, "confirm_seconds": confirm})

    decision = "keep"
    if confirm > 0 and rollback:
        decision = "timeout"
        deadline = time.monotonic() + confirm
        while time.monotonic() < deadline:
            if os.path.exists(os.path.join(work_dir, "keep.flag")):
                decision = "keep"
                break
            if os.path.exists(os.path.join(work_dir, "revert.flag")):
                decision = "revert"
                break
            time.sleep(0.25)
    rolled = run_steps(rollback) if decision != "keep" else []
    write_json(work_dir, "final.json", {"phase": "final", "decision": decision, "rollback": rolled})
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
