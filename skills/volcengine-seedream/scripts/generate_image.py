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
import http.client
import json
import mimetypes
import os
import re
import subprocess
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
    "lite": "doubao-seedream-5-0-lite-260128",
    "flash": "doubao-seedream-5-0-flash-260915",
    "pro": "doubao-seedream-5-0-pro-260628",
    "5.0-lite": "doubao-seedream-5-0-lite-260128",
    "5.0-pro": "doubao-seedream-5-0-pro-260628",
    "5.0-flash": "doubao-seedream-5-0-flash-260915",
}

# short alias -> friendly family name (for pricing / validation / summary)
BARE_ALIASES = {"flash": "5.0-flash", "pro": "5.0-pro", "lite": "5.0-lite"}

# Models believed to support sequential/grouped image generation.
SUPPORTED_SEQUENTIAL = {"5.0-pro", "5.0-flash", "5.0-lite", "4.0", "5.0"}

# Price table (CNY per image) for cn-beijing, 2026-10.
# 1K and 1.5K are priced the same where listed.
PRICE_TABLE = {
    ("5.0-flash", "1.5K"): 0.12,
    ("5.0-flash", "2K"): None,    # unverified
    ("5.0-flash", "4K"): None,    # not supported by this model
    ("5.0-lite", "1.5K"): 0.22,
    ("5.0-lite", "2K"): 0.22,     # flat price assumption (only 0.22 given)
    ("5.0-lite", "4K"): 0.22,
    ("5.0-pro", "1.5K"): 0.30,
    ("5.0-pro", "2K"): 0.60,
    ("5.0-pro", "4K"): None,      # pro tops out at 2K
}

# Total-pixel thresholds for price tiers.
# <2.61M keeps the image in the cheap 1.5K tier.
TIER_PIXEL_MAX = {
    "1.5K": 2_610_000,
    "2K": 4_500_000,    # covers 2048x2048 (4.19M)
    "4K": 16_900_000,   # covers 4096x4096 (16.78M)
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


def normalize_model_name(model_arg: str) -> str | None:
    """Return a friendly family name (e.g. '5.0-pro') for pricing/validation.

    Accepts aliases from MODEL_ALIASES or raw Ark model IDs.
    Returns None if the family cannot be determined.
    """
    if model_arg in BARE_ALIASES:
        return BARE_ALIASES[model_arg]
    if model_arg in MODEL_ALIASES:
        key = model_arg
        # Friendly aliases map directly to known families.
        if key in ("flash", "pro", "lite"):
            return f"5.0-{key}"
        if key.startswith("5.0-"):
            return key
        if key in ("4.0", "4.5", "5.0"):
            return key
        # Other aliases (e.g. 3.0-t2i, 4.0-old) are not in the price table.
        return None
    low = model_arg.lower()
    if "seedream-5-0-flash" in low:
        return "5.0-flash"
    if "seedream-5-0-lite" in low:
        return "5.0-lite"
    if "seedream-5-0-pro" in low:
        return "5.0-pro"
    if "seedream-5-0" in low:
        return "5.0"
    if "seedream-4-0" in low:
        return "4.0"
    if "seedream-4-5" in low:
        return "4.5"
    return None


def resolve_size(size: str, aspect: str | None) -> tuple[int, int]:
    """Parse --size and optional --aspect into (width, height).

    Raises ValueError on invalid format or unsupported combination.
    """
    s = size.strip().upper()
    named_map = {"1K": (1024, 1024), "1.5K": (1536, 1536), "2K": (2048, 2048), "4K": (4096, 4096)}

    if "X" in s:
        try:
            parts = s.split("X")
            if len(parts) != 2:
                raise ValueError
            w, h = map(int, parts)
            if w <= 0 or h <= 0:
                raise ValueError
            return (w, h)
        except Exception:
            raise ValueError(f"--size 格式错误: {size}（仅支持 1K/1.5K/2K/4K 或 WxH）")

    if s not in named_map:
        raise ValueError(f"--size 不支持: {size}（仅支持 1K/1.5K/2K/4K 或 WxH）")

    if aspect is not None:
        if s == "4K":
            raise ValueError("4K 暂不支持 aspect 预设，请改用 -s <WxH> 或去掉 -a")
        tier = "2K" if s == "2K" else "1.5K"
        table = ASPECT_PX[tier]
        if aspect not in table:
            raise ValueError(
                f"未知 aspect {aspect}；{tier} 档可选: {', '.join(table)}"
            )
        w, h = map(int, table[aspect].split("x"))
        return (w, h)

    return named_map[s]


def get_size_tier(width: int, height: int) -> str | None:
    """Map a resolved (width, height) to a price tier: 1.5K / 2K / 4K.

    Uses total-pixel thresholds to match the Ark price-tier boundary
    (<=2.61M pixels -> 1.5K).
    """
    pixels = width * height
    if pixels <= TIER_PIXEL_MAX["1.5K"]:
        return "1.5K"
    if pixels <= TIER_PIXEL_MAX["2K"]:
        return "2K"
    if pixels <= TIER_PIXEL_MAX["4K"]:
        return "4K"
    return None


def count_chinese_chars(text: str) -> int:
    """Count CJK Unified Ideographs in a string."""
    return len(re.findall(r"[\u4e00-\u9fff]", text))


def estimate_cost_line(
    normalized: str | None,
    tier: str | None,
    n: int,
    has_reference: bool,
    max_images: int = 1,
    sequential: bool = False,
) -> str:
    """Return a human-readable cost estimate line."""
    if normalized is None or tier is None or normalized in ("4.0", "4.5"):
        return "预计费用: 未知（以控制台为准）"

    price = PRICE_TABLE.get((normalized, tier))
    if price is None:
        if normalized == "5.0-flash" and tier == "2K":
            line = (
                f"预计费用: {normalized} × {n} 张 @{tier} "
                f"≈ 未证（2K 价格未证；以控制台实际账单为准）"
            )
        else:
            line = (
                f"预计费用: {normalized} × {n} 张 @{tier} "
                f"≈ 未知（以控制台实际账单为准）"
            )
    elif sequential and max_images > 1:
        low = price * n
        high = price * n * max_images
        line = (
            f"预计费用: {normalized} × {n} 个请求 @{tier}，"
            f"每张请求最多产出 {max_images} 张，按张计费 "
            f"≈ ¥{low:.2f} ~ ¥{high:.2f}（以控制台实际账单为准）"
        )
    else:
        total = price * n
        line = (
            f"预计费用: {normalized} × {n} 张 @{tier} "
            f"≈ ¥{total:.2f}（以控制台实际账单为准）"
        )

    if has_reference and normalized == "5.0-pro":
        line += "（另：输入图约 0.02 元/张，首张免费）"
    return line


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
    width, height = resolve_size(args.size, args.aspect)
    size = f"{width}x{height}"

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


def post_json(url: str, payload: dict, api_key: str, retries: int = 2) -> tuple[dict, dict]:
    """POST JSON and return (response_dict, payload_used).

    If the server rejects optimize_prompt_options with HTTP 400, retry once
    without it *without* consuming a retry budget, and the returned payload
    reflects the removal so the caller can back-propagate it.
    """
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    last_err: Exception | None = None
    attempt = 0
    network_errors = (
        urllib.error.URLError,
        TimeoutError,
        ConnectionResetError,
        http.client.RemoteDisconnected,
    )
    while attempt <= retries:
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                return json.loads(resp.read().decode("utf-8")), payload
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")
            # If Ark rejects the prompt-optimization param, retry once without it.
            # This retry does NOT count against the retries budget.
            if (e.code == 400 and "optimize_prompt_options" in payload
                    and "optimize" in detail.lower()):
                print("note: server rejected optimize_prompt_options; retrying without it")
                payload.pop("optimize_prompt_options", None)
                body = json.dumps(payload).encode("utf-8")
                continue
            # retry on rate limit / server errors only
            if e.code in (429, 500, 502, 503, 504) and attempt < retries:
                last_err = RuntimeError(f"HTTP {e.code}: {detail}")
                attempt += 1
                time.sleep(2 * attempt)
                continue
            sys.exit(f"ERROR: Ark API returned HTTP {e.code}\n{detail}")
        except network_errors as e:
            last_err = e
            if attempt < retries:
                attempt += 1
                time.sleep(2 * attempt)
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


def sanitize_filename(name: str) -> str:
    """Return a safe base name: basename + strip Windows illegal chars."""
    name = Path(name).name
    name = re.sub(r'[<>:"/\\|?*]', "", name)
    name = name.strip()
    if not name:
        name = "seedream"
    return name


def unique_path(out_dir: Path, base_name: str, ext: str) -> Path:
    """Return a non-conflicting output path, adding _1/_2/... before the extension."""
    target = out_dir / f"{base_name}{ext}"
    if not target.exists():
        return target
    i = 1
    while True:
        candidate = out_dir / f"{base_name}_{i}{ext}"
        if not candidate.exists():
            return candidate
        i += 1


def save_image(item: dict, out_dir: Path, base_name: str, index: int) -> Path:
    suffix = "" if index == 0 else f"_{index + 1}"

    if item.get("b64_json"):
        data = base64.b64decode(item["b64_json"])
    else:
        url = item.get("url")
        if not url:
            sys.exit(f"ERROR: response has neither url nor b64_json: {item}")
        try:
            with urllib.request.urlopen(url, timeout=180) as resp:
                data = resp.read()
        except urllib.error.HTTPError as e:
            sys.exit(f"ERROR: failed to download image from {url}: HTTP {e.code}")
        except (urllib.error.URLError, TimeoutError, ConnectionResetError, http.client.RemoteDisconnected) as e:
            sys.exit(f"ERROR: failed to download image from {url}: {e}")

    ext = _ext_for(data)
    stem = f"{base_name}{suffix}"
    target = unique_path(out_dir, stem, ext)
    target.write_bytes(data)
    return target


def write_meta(image_path: Path, base_payload: dict, payload: dict, args: argparse.Namespace) -> None:
    """Write a .txt sidecar next to the image so results are reproducible/iterable."""
    width, height = resolve_size(args.size, args.aspect)
    meta = {
        "model": base_payload["model"],
        "prompt": base_payload["prompt"],
        "size": base_payload["size"],
        "resolved_size": f"{width}x{height}",
        "seed": payload.get("seed", -1),
        "aspect": args.aspect,
        "prompt_mode": args.prompt_mode,
        "watermark": base_payload["watermark"],
        "refs": args.image or [],
        "n": args.n,
        "sequential": args.sequential,
        "max_images": args.max_images,
        "web_search": args.web_search,
        "endpoint": DEFAULT_ENDPOINT,
    }
    sidecar = image_path.with_name(image_path.name + ".txt")
    sidecar.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def ensure_output_writable(out_dir: Path) -> None:
    """Create output dir and verify it is writable before any API call."""
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        sys.exit(f"ERROR: cannot create output directory: {out_dir}\n{e}")
    probe = out_dir / ".seedream_write_probe"
    try:
        probe.write_text("probe", encoding="utf-8")
        probe.unlink()
    except OSError as e:
        sys.exit(f"ERROR: output directory is not writable: {out_dir}\n{e}")


def validate_args(args: argparse.Namespace) -> None:
    """Validate argument consistency.

    Prints warnings (non-blocking) and errors (blocking, exits with code 1).
    Runs for both real generation and --dry-run.
    """
    errors: list[str] = []
    warnings: list[str] = []

    norm = normalize_model_name(args.model)

    # Size / aspect validation (single source of truth).
    resolved = None
    try:
        resolved = resolve_size(args.size, args.aspect)
        args._resolved_size = resolved
    except ValueError as e:
        errors.append(str(e))

    tier = None
    if resolved is not None:
        tier = get_size_tier(*resolved)

    if norm is None and not args.model.lower().startswith("doubao-"):
        errors.append(
            f'未知模型名 "{args.model}"，请用 flash/pro/lite/5.0-* 或完整 doubao-* ID'
        )

    if args.n < 1:
        errors.append("-n 必须 >= 1")

    if args.max_images < 1:
        errors.append("--max-images 必须 >= 1")
    elif not args.sequential and args.max_images != 4:
        # Default 4 without --sequential is the argparse default; only warn when explicitly set.
        warnings.append("--max-images 仅在配合 --sequential 时生效")

    cc = count_chinese_chars(args.prompt)
    if cc > 300:
        warnings.append(f"提示词含 {cc} 个汉字，超过 300 个可能影响效果（建议精简）")

    for img in args.image or []:
        if img.startswith(("http://", "https://", "data:")):
            continue
        path = Path(img).expanduser()
        if not path.is_file():
            errors.append(f"本地参考图不存在: {path}")

    if args.prompt_mode == "fast" and norm != "5.0-pro":
        if norm is None:
            errors.append(f"--prompt-mode fast 仅 5.0-pro 支持（无法识别模型 {args.model}）")
        else:
            errors.append(f"--prompt-mode fast 仅 5.0-pro 支持（当前模型为 {norm}）")

    if args.web_search and norm != "5.0-lite":
        if norm is None:
            errors.append(f"--web-search 仅 5.0-lite 支持（无法识别模型 {args.model}）")
        else:
            errors.append(f"--web-search 仅 5.0-lite 支持（当前模型为 {norm}）")

    if tier == "4K" and norm not in ("4.0", "5.0-lite"):
        errors.append("分辨率 4K 仅 4.0 / 5.0-lite 支持；5.0-pro 最高 2K")

    if tier == "2K" and norm == "5.0-flash":
        warnings.append("5.0-flash 的 2K 价格未证，实际费用请以控制台账单为准")

    if args.sequential and norm not in SUPPORTED_SEQUENTIAL:
        warnings.append(
            f"模型 {args.model} 可能不支持组图生成（--sequential/--max-images），效果请以控制台为准"
        )

    for w in warnings:
        print(f"WARNING: {w}")
    for e in errors:
        print(f"ERROR: {e}")

    if errors:
        sys.exit(1)


def print_summary(args: argparse.Namespace) -> None:
    """Print parsed parameters, prompt char count and cost estimate."""
    norm = normalize_model_name(args.model)
    resolved = getattr(args, "_resolved_size", None)
    tier = get_size_tier(*resolved) if resolved else None
    resolved_model = MODEL_ALIASES.get(args.model, args.model)
    out = Path(args.out).expanduser() / args.filename

    print("参数摘要:")
    print(f"  prompt: {args.prompt!r}")
    print(f"  prompt 汉字数: {count_chinese_chars(args.prompt)}")
    print(f"  model: {args.model} -> {resolved_model}")
    print(f"  size: {args.size} (resolved: {resolved[0]}x{resolved[1] if resolved else 'unknown'}, tier: {tier or 'unknown'})")
    print(f"  aspect: {args.aspect or '(none)'}")
    print(f"  prompt_mode: {args.prompt_mode}")
    print(f"  watermark: {args.watermark}")
    print(f"  n: {args.n}")
    print(f"  output: {out}")
    print(f"  reference images: {args.image or []}")
    print(f"  web_search: {args.web_search}")
    print(f"  sequential: {args.sequential}, max_images: {args.max_images}")
    print(estimate_cost_line(norm, tier, args.n, bool(args.image), args.max_images, args.sequential))


def preview_image(path: Path) -> None:
    """Open an image with the system default viewer. Failures are non-fatal."""
    try:
        if sys.platform == "win32":
            os.startfile(str(path))
        elif sys.platform == "darwin":
            subprocess.run(["open", str(path)], check=False)
        else:
            subprocess.run(["xdg-open", str(path)], check=False)
        print(f"PREVIEW: {path.resolve()}")
    except Exception as e:
        print(f"WARNING: 无法预览图片: {e}")


def main() -> None:
    p = argparse.ArgumentParser(description="Generate images via Volcano Engine Ark Seedream API.")
    p.add_argument("-p", "--prompt", required=True, help="text prompt (Chinese or English)")
    p.add_argument("-f", "--filename", default="seedream", help="output base name (no extension)")
    p.add_argument("-o", "--out", default=str(Path.home() / "Pictures" / "seedream"),
                   help="output directory (default: <home>/Pictures/seedream)")
    p.add_argument("-m", "--model", default="doubao-seedream-5-0-flash-260915",
                   help="model alias (4.0/4.5/5.0/5.0-lite/5.0-pro/5.0-flash/3.0-t2i) or raw model ID")
    p.add_argument("-s", "--size", default="1.5K",
                   help='resolution: 1K/1.5K/2K/4K or "WxH" (default 1.5K = cheapest tier)')
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
    p.add_argument("--dry-run", action="store_true",
                   help="validate arguments and print summary/cost estimate without calling the API")
    p.add_argument("--no-preview", action="store_true",
                   help="do not open the saved image with the default viewer")
    args = p.parse_args()

    # Sanitize output filename before any validation or summary.
    args.filename = sanitize_filename(args.filename)

    validate_args(args)
    print_summary(args)

    if args.dry_run:
        print("DRY-RUN: 参数校验通过，不会调用 API 或写入文件")
        sys.exit(0)

    api_key = read_api_key()
    base_payload = build_payload(args)
    out_dir = Path(args.out).expanduser()

    # Ensure output directory exists and is writable *before* spending money on API calls.
    ensure_output_writable(out_dir)

    print(f"-> model={base_payload['model']} size={base_payload['size']} "
          f"prompt_mode={args.prompt_mode} watermark={base_payload['watermark']} n={args.n}")

    saved: list[Path] = []
    for i in range(args.n):
        payload = dict(base_payload)
        if args.seed is not None:
            payload["seed"] = args.seed + i
        seed_used = payload.get("seed", -1)
        result, payload_used = post_json(DEFAULT_ENDPOINT, payload, api_key)
        # Back-propagate optimize removal so the next variant does not retry the same 400.
        if "optimize_prompt_options" not in payload_used and "optimize_prompt_options" in base_payload:
            base_payload.pop("optimize_prompt_options", None)
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

    if saved and not args.no_preview:
        preview_image(saved[0])


if __name__ == "__main__":
    main()
