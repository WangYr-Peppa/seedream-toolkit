#!/usr/bin/env python3
"""Generate images with the Volcano Engine Ark (Doubao Seedream) image API.

Standard Ark endpoint: https://ark.cn-beijing.volces.com/api/v3/images/generations

The API key is read from the ARK_API_KEY environment variable
(fallback: ARK_SEEDREAM_API_KEY). Never hard-code the key.

Only the Python standard library is required.

Examples:
    python generate_image.py -p "一只戴着墨镜的橘猫，坐在海边，日落，超写实"
    python generate_image.py -p "赛博朋克城市夜景" -a 16:9 -o ./out
    python generate_image.py -p "把背景改成雨夜街道" -i ./input.png
"""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_ENDPOINT = os.environ.get(
    "ARK_IMAGE_ENDPOINT",
    "https://ark.cn-beijing.volces.com/api/v3/images/generations",
)

# Friendly aliases -> real Ark model IDs. Raw model IDs pass through unchanged.
# Availability verified on the cn-beijing test account 2026-10.
MODEL_ALIASES = {
    "3.0-t2i": "doubao-seedream-3-0-t2i-250415",   # dead (Shutdown)
    "4.0": "doubao-seedream-4-0-20260415",          # current 4.0 (activatable; 4K)
    "4.0-old": "doubao-seedream-4-0-250828",        # dead
    "4.5": "doubao-seedream-4-5-251128",            # dead on this account
    "5.0": "doubao-seedream-5-0-260128",            # dead on this account
    "5.0-lite": "doubao-seedream-5-0-lite-260128",  # dead on this account
    "5.0-pro": "doubao-seedream-5-0-pro-260628",
    "5.0-flash": "doubao-seedream-5-0-flash-260915",
}

# Aspect presets, keyed by resolution tier. The "1.5K" table keeps total pixels
# under 2.61M so the image stays in the cheap Ark price tier
# (0.30 CNY/img for doubao-seedream-5.0-pro).
ASPECT_PX = {
    "1.5K": {
        "1:1": "1536x1536",   # 2.36M
        "4:3": "1728x1296",   # 2.24M
        "3:4": "1296x1728",
        "16:9": "2048x1152",  # 2.36M
        "9:16": "1152x2048",
        "3:2": "1920x1280",   # 2.46M
        "2:3": "1280x1920",
        "21:9": "2048x878",   # 1.80M
    },
    "2K": {
        "1:1": "2048x2048",
        "4:3": "2048x1536",
        "3:4": "1536x2048",
        "16:9": "2048x1152",
        "9:16": "1152x2048",
        "3:2": "2048x1365",
        "2:3": "1365x2048",
        "21:9": "2048x878",
    },
}


def read_api_key() -> str:
    key = os.environ.get("ARK_API_KEY") or os.environ.get("ARK_SEEDREAM_API_KEY")
    if not key:
        sys.exit(
            "ERROR: ARK_API_KEY is not set.\n"
            "Set it first, e.g. in PowerShell:\n"
            '  [Environment]::SetEnvironmentVariable("ARK_API_KEY","<your-key>","User")\n'
            "then open a new terminal (or restart opencode)."
        )
    return key.strip()


def to_data_url(value: str) -> str:
    """Accept an http(s) URL or a local image path; return a URL/data URL."""
    if value.startswith(("http://", "https://", "data:")):
        return value
    path = Path(value).expanduser()
    if not path.is_file():
        sys.exit(f"ERROR: reference image not found: {path}")
    mime = mimetypes.guess_type(str(path))[0] or "image/png"
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def build_payload(args: argparse.Namespace) -> dict:
    model = MODEL_ALIASES.get(args.model, args.model)

    size = args.size
    if args.aspect:
        if "x" in size.lower():
            print(f"note: --aspect ignored because --size is explicit ({size})")
        else:
            tier = "2K" if size.strip().upper().startswith("2") else "1.5K"
            table = ASPECT_PX[tier]
            if args.aspect not in table:
                sys.exit(f"ERROR: unknown aspect {args.aspect}; choose one of {', '.join(table)}")
            size = table[args.aspect]

    payload: dict = {
        "model": model,
        "prompt": args.prompt,
        "size": size,
        "response_format": "url",
        "watermark": args.watermark,
    }
    # Ark built-in prompt optimization (Seedream 5.0-pro / 4.0 support standard|fast).
    if args.prompt_mode and args.prompt_mode != "off":
        payload["optimize_prompt_options"] = {"mode": args.prompt_mode}
    if args.seed is not None:
        payload["seed"] = args.seed

    refs = args.image or []
    if refs:
        urls = [to_data_url(r) for r in refs]
        payload["image"] = urls[0] if len(urls) == 1 else urls

    if args.sequential:
        payload["sequential_image_generation"] = "auto"
        payload["sequential_image_generation_options"] = {"max_images": args.max_images}
    if args.web_search:
        payload["tools"] = [{"type": "web_search"}]

    return payload


def post_json(url: str, payload: dict, api_key: str, retries: int = 2) -> dict:
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    last_err: Exception | None = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")
            # If Ark rejects the prompt-optimization param, retry once without it.
            if (e.code == 400 and "optimize_prompt_options" in payload
                    and "optimize" in detail.lower()):
                print("note: server rejected optimize_prompt_options; retrying without it")
                payload.pop("optimize_prompt_options", None)
                body = json.dumps(payload).encode("utf-8")
                last_err = RuntimeError(f"HTTP {e.code}: {detail}")
                continue
            # retry on rate limit / server errors only
            if e.code in (429, 500, 502, 503, 504) and attempt < retries:
                last_err = RuntimeError(f"HTTP {e.code}: {detail}")
                time.sleep(2 * (attempt + 1))
                continue
            sys.exit(f"ERROR: Ark API returned HTTP {e.code}\n{detail}")
        except (urllib.error.URLError, TimeoutError) as e:
            last_err = e
            if attempt < retries:
                time.sleep(2 * (attempt + 1))
                continue
            sys.exit(f"ERROR: request failed: {e}")
    sys.exit(f"ERROR: request failed after retries: {last_err}")


def _ext_for(data: bytes) -> str:
    """Detect the real image type from magic bytes (Ark may return JPEG even if asked for PNG)."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    return ".png"


def save_image(item: dict, out_dir: Path, base_name: str, index: int) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = "" if index == 0 else f"_{index + 1}"

    if item.get("b64_json"):
        data = base64.b64decode(item["b64_json"])
    else:
        url = item.get("url")
        if not url:
            sys.exit(f"ERROR: response has neither url nor b64_json: {item}")
        with urllib.request.urlopen(url, timeout=180) as resp:
            data = resp.read()

    target = out_dir / f"{base_name}{suffix}{_ext_for(data)}"
    target.write_bytes(data)
    return target


def write_meta(image_path: Path, base_payload: dict, payload: dict, args: argparse.Namespace) -> None:
    """Write a .txt sidecar next to the image so results are reproducible/iterable."""
    meta = {
        "model": base_payload["model"],
        "prompt": base_payload["prompt"],
        "size": base_payload["size"],
        "seed": payload.get("seed", -1),
        "aspect": args.aspect,
        "prompt_mode": args.prompt_mode,
        "watermark": base_payload["watermark"],
        "refs": args.image or [],
    }
    sidecar = image_path.with_name(image_path.name + ".txt")
    sidecar.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser(description="Generate images via Volcano Engine Ark Seedream API.")
    p.add_argument("-p", "--prompt", required=True, help="text prompt (Chinese or English)")
    p.add_argument("-f", "--filename", default="seedream", help="output base name (no extension)")
    p.add_argument("-o", "--out", default=".", help="output directory (default: current dir)")
    p.add_argument("-m", "--model", default="doubao-seedream-5-0-flash-260915",
                   help="model alias (4.0/4.5/5.0/5.0-lite/5.0-pro/5.0-flash/3.0-t2i) or raw model ID")
    p.add_argument("-s", "--size", default="1.5K",
                   help='resolution: 1K/1.5K/2K or "WxH" (default 1.5K = cheapest tier)')
    p.add_argument("-a", "--aspect", help="aspect preset: 1:1,4:3,3:4,16:9,9:16,3:2,2:3,21:9")
    p.add_argument("-i", "--image", action="append",
                   help="reference image path or URL (repeatable; single=img2img, many=fusion)")
    p.add_argument("--seed", type=int, help="random seed for reproducibility")
    p.add_argument("--no-watermark", dest="watermark", action="store_false",
                   help="disable the AI watermark (default: disabled)")
    p.add_argument("--watermark", dest="watermark", action="store_true", help="enable AI watermark")
    p.set_defaults(watermark=False)
    p.add_argument("--sequential", action="store_true", help="enable grouped/sequential generation")
    p.add_argument("--max-images", type=int, default=4, help="max images for --sequential")
    p.add_argument("--web-search", action="store_true", help="enable web-search enhanced generation")
    p.add_argument("--prompt-mode", choices=["standard", "fast", "off"], default="standard",
                   help="Ark built-in prompt optimization mode (default: standard)")
    p.add_argument("-n", "--n", type=int, default=1,
                   help="number of variants (uses seed, seed+1, ... when --seed is given); costs n images")
    p.add_argument("--save-meta", action="store_true",
                   help="write a .txt sidecar (prompt/params/seed) next to each image")
    args = p.parse_args()

    api_key = read_api_key()
    base_payload = build_payload(args)
    out_dir = Path(args.out).expanduser()
    print(f"-> model={base_payload['model']} size={base_payload['size']} "
          f"prompt_mode={args.prompt_mode} watermark={base_payload['watermark']} n={args.n}")

    saved: list[Path] = []
    for i in range(args.n):
        payload = dict(base_payload)
        if args.seed is not None:
            payload["seed"] = args.seed + i
        seed_used = payload.get("seed", -1)
        result = post_json(DEFAULT_ENDPOINT, payload, api_key)
        data = result.get("data") or []
        if not data:
            sys.exit(f"ERROR: empty result: {json.dumps(result, ensure_ascii=False)}")
        for item in data:
            path = save_image(item, out_dir, args.filename, len(saved))
            saved.append(path)
            print(f"SAVED: {path.resolve()}  (seed={seed_used})")
            if args.save_meta:
                write_meta(path, base_payload, payload, args)
        if result.get("usage"):
            print(f"usage: {json.dumps(result['usage'], ensure_ascii=False)}")


if __name__ == "__main__":
    main()
