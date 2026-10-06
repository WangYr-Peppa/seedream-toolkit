#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Batch illustration for the seedream toolkit.

Two sub-commands:
  gen      job.json [-o OUTDIR] [--result R.json] [--dry-run]
  resolve  spec.json --result R.json -o spec.resolved.json

job.json (office -> seedream):
{
  "style": "flat vector illustration, unified blue-gray palette",  # optional global style lock
  "aspect_default": "16:9", "model": "flash", "size": "1.5K",
  "out_dir": "output/images",
  "items": [
    {"id": "s3_arch", "content": "browser/service/db three-tier architecture", "aspect": "16:9", "model": "flash", "size": "1.5K"}
  ]
}

result.json (seedream -> office):
{ "items": [{"id","path","ok","model","size","aspect","cost","error"}], "total_cost": 0.24, "dry_run": false }

resolve: copies a presentation spec (deck.py format) and fills each slide's
`image` from `image_id` using result.json, so the stock deck.py can embed it.

--dry-run validates and quotes WITHOUT calling the API (no cost).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_image as gi  # reuse constants + pure helpers (no side effects on import)

GENERATOR = str(Path(__file__).resolve().parent / "generate_image.py")


def compose_prompt(content: str, style: str | None) -> str:
    """Apply the global style lock to a per-item content string."""
    content = (content or "").strip().rstrip("。.")
    style = (style or "").strip()
    if style and style not in content:
        return f"{content}，{style}" if content else style
    return content


def sanitize_id(value: str) -> str:
    """Make an id safe for use as a file base name."""
    out = re.sub(r'[<>:"/\\|?*\s]+', "_", (value or "img").strip()).strip("_")
    return out or "img"


def item_plan(model: str, size: str, aspect: str | None) -> tuple[str | None, str | None, float | None]:
    """Return (family, tier, unit_cost). Any field may be None if unknown."""
    family = gi.normalize_model_name(model)
    tier = None
    try:
        width, height = gi.resolve_size(size, aspect)
        tier = gi.get_size_tier(width, height)
    except ValueError:
        tier = None
    cost = gi.PRICE_TABLE.get((family, tier)) if (family and tier) else None
    return family, tier, cost


def run_gen(job_path: str, out_dir_override: str | None, result_path: str | None, dry_run: bool) -> int:
    job_path = str(Path(job_path).expanduser())
    job = json.loads(Path(job_path).read_text(encoding="utf-8"))
    items = job.get("items") or []
    if not items:
        print("ERROR: job has no items")
        return 2

    job_dir = Path(job_path).resolve().parent
    out_dir = out_dir_override or job.get("out_dir") or str(job_dir / "images")
    style = job.get("style")
    result_path = result_path or str(Path(job_path).with_suffix("")) + ".result.json"

    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    results: list[dict] = []
    total = 0.0

    for it in items:
        iid = sanitize_id(str(it.get("id") or f"img{len(results) + 1}"))
        prompt = compose_prompt(it.get("content") or it.get("prompt") or "", style)
        model = it.get("model") or job.get("model") or "flash"
        size = it.get("size") or job.get("size") or "1.5K"
        aspect = it.get("aspect") or job.get("aspect_default")
        family, tier, cost = item_plan(model, size, aspect)

        rec = {
            "id": iid, "model": model, "size": size, "aspect": aspect,
            "family": family, "tier": tier, "unit_cost": cost,
            "ok": True, "path": None, "error": None,
        }

        cmd = [sys.executable or "python", GENERATOR, "-p", prompt, "-m", model,
               "-s", size, "-f", iid, "-o", out_dir, "--no-preview"]
        if aspect:
            cmd += ["-a", aspect]
        if dry_run:
            cmd += ["--dry-run"]

        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
        out = (proc.stdout or "") + (proc.stderr or "")

        if proc.returncode != 0:
            rec["ok"] = False
            lines = [ln for ln in out.strip().splitlines() if ln.strip()]
            rec["error"] = (lines[-1] if lines else "unknown error")[:300]
        else:
            for ln in out.splitlines():
                if ln.strip().startswith("SAVED:"):
                    rec["path"] = ln.split("SAVED:", 1)[1].strip().split(" ", 1)[0]
                    break

        if cost:
            total += cost
        results.append(rec)
        status = "ok" if rec["ok"] else "FAIL"
        print(f"[{'quote' if dry_run else 'gen'}] {iid}: {status} "
              f"{rec.get('path') or rec.get('error') or ''}")

    failed = sum(1 for r in results if not r["ok"])
    res = {"items": results, "total_cost": round(total, 2), "dry_run": dry_run, "out_dir": out_dir}
    Path(result_path).write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"result: {result_path}")
    print(f"共 {len(results)} 项，失败 {failed} 项；{'预估费用' if dry_run else '已出图'} ≈ ¥{res['total_cost']:.2f}")
    return 0 if failed == 0 else 1


def run_resolve(spec_path: str, result_path: str, out_path: str) -> int:
    spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    res = json.loads(Path(result_path).read_text(encoding="utf-8"))
    img_map = {r["id"]: r["path"] for r in res.get("items", []) if r.get("ok") and r.get("path")}

    filled = 0
    for sl in spec.get("slides", []):
        iid = sl.get("image_id")
        if iid and not sl.get("image") and iid in img_map:
            sl["image"] = img_map[iid]
            filled += 1

    Path(out_path).write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"resolved {filled} image_id -> image; saved: {out_path}")

    missing = [sl.get("image_id") for sl in spec.get("slides", [])
               if sl.get("image_id") and not sl.get("image")]
    if missing:
        print(f"WARNING: 无对应结果图的 image_id: {missing}")
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description="Batch illustration (job.json -> images -> result.json) + deck resolve.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("gen", help="generate images from a job.json")
    g.add_argument("job")
    g.add_argument("-o", "--out-dir", help="override output directory")
    g.add_argument("--result", help="result.json path (default: <job>.result.json)")
    g.add_argument("--dry-run", action="store_true", help="validate + quote only; no API call")

    r = sub.add_parser("resolve", help="fill deck spec image_id fields from result.json")
    r.add_argument("spec")
    r.add_argument("--result", required=True)
    r.add_argument("-o", "--output", required=True)

    args = ap.parse_args()
    if args.cmd == "gen":
        sys.exit(run_gen(args.job, args.out_dir, args.result, args.dry_run))
    sys.exit(run_resolve(args.spec, args.result, args.output))


if __name__ == "__main__":
    main()
