#!/usr/bin/env python3
"""
Antigravity Background Image Patcher (`agy-bg-patch`)
=====================================================
Patches Antigravity's `app.asar` (`dist/utils.js`) to inject a customizable
background wallpaper & automatic slideshow layer with live hot-reloading from:
  ~/.gemini/antigravity/background/config.json

Features:
- Single image (`image`) OR multiple images (`images`: [...]) automatic slideshow!
- Configurable rotation interval (`intervalSeconds`, default: 60s) & `shuffle` mode
- Supports local image files (.png, .jpg, .webp, .gif, .svg, .avif) or HTTP(S)/data URLs
- Live hot-reload: editing `config.json` or running `python patch_background.py set ...`
  updates the background in all open Antigravity windows immediately without restart!
- Built-in screenshot helper (`python patch_background.py screenshot`) via `hubContents.capturePage()`
- Keeps built-in browser tabs (`[data-has-browser-hole="true"]`) clean and unobstructed
- Automatically backs up `app.asar` to `app.asar.bak` and recalculates ASAR SHA256 integrity
"""

import argparse
import copy
import hashlib
import json
import os
import shutil
import struct
import sys
import time
from pathlib import Path

PATCH_MARKER_START = "// === [AGY-BG-PATCH-START] ==="
PATCH_MARKER_END = "// === [AGY-BG-PATCH-END] ==="
TARGET_ANCHOR = "(0, loadingOverlay_1.attachLoadingOverlay)(win, foregroundColor, backgroundColor);"

BLOCK_SIZE = 4 * 1024 * 1024  # 4 MiB standard ASAR integrity block size


def get_default_asar_path() -> Path:
    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
        return Path(local_app_data) / "Programs" / "antigravity" / "resources" / "app.asar"
    elif sys.platform == "darwin":
        return Path("/Applications/Antigravity.app/Contents/Resources/app.asar")
    else:
        return Path("/opt/Antigravity/resources/app.asar")


def get_bg_config_dir() -> Path:
    return Path.home() / ".gemini" / "antigravity" / "background"


def get_bg_config_path() -> Path:
    return get_bg_config_dir() / "config.json"


def build_injected_js() -> str:
    return r"""// === [AGY-BG-PATCH-START] ===
    (() => {
        try {
            const os = require('os');
            const bgDir = path_1.default.join(os.homedir(), '.gemini', 'antigravity', 'background');
            const bgConfigPath = path_1.default.join(bgDir, 'config.json');
            let bgCssKey = null;
            let bgWatcher = null;
            let bgDebounce = null;
            let bgSlideTimer = null;
            let bgSlideIndex = 0;
            let bgResolvedList = [];
            let bgCurrentCfg = null;
            let lastCaptureToken = '';
            const bgImageCache = new Map();

            const mimeByExt = {
                '.png': 'image/png',
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.webp': 'image/webp',
                '.gif': 'image/gif',
                '.svg': 'image/svg+xml',
                '.avif': 'image/avif',
                '.bmp': 'image/bmp',
            };

            const resolveImageUrl = (imgInput) => {
                if (!imgInput || typeof imgInput !== 'string') return '';
                const trimmed = imgInput.trim();
                if (!trimmed) return '';
                if (/^(https?:|data:)/i.test(trimmed)) return trimmed;
                let filePath = trimmed;
                if (filePath.startsWith('file://')) {
                    filePath = filePath.replace(/^file:\/\/\/?/i, '');
                    if (process.platform !== 'win32' && !filePath.startsWith('/')) {
                        filePath = '/' + filePath;
                    }
                } else if (filePath.startsWith('~')) {
                    filePath = path_1.default.join(os.homedir(), filePath.slice(1));
                } else if (!path_1.default.isAbsolute(filePath)) {
                    filePath = path_1.default.join(bgDir, filePath);
                }
                if (!fs.existsSync(filePath)) {
                    const fallbackInWallpapers = path_1.default.join(bgDir, 'wallpapers', path_1.default.basename(filePath));
                    if (fs.existsSync(fallbackInWallpapers)) {
                        filePath = fallbackInWallpapers;
                    } else {
                        return '';
                    }
                }
                try {
                    const stat = fs.statSync(filePath);
                    const cacheKey = `${filePath}:${stat.mtimeMs}:${stat.size}`;
                    if (bgImageCache.has(cacheKey)) {
                        return bgImageCache.get(cacheKey);
                    }
                    const ext = path_1.default.extname(filePath).toLowerCase();
                    const mime = mimeByExt[ext] || 'image/png';
                    const bytes = fs.readFileSync(filePath);
                    const dataUrl = `data:${mime};base64,${bytes.toString('base64')}`;
                    if (bgImageCache.size > 16) {
                        const oldestKey = bgImageCache.keys().next().value;
                        bgImageCache.delete(oldestKey);
                    }
                    bgImageCache.set(cacheKey, dataUrl);
                    return dataUrl;
                } catch {
                    return '';
                }
            };

            const resolveImageCandidates = (cfg) => {
                const rawList = [];
                if (Array.isArray(cfg.images)) {
                    for (const item of cfg.images) {
                        if (typeof item === 'string' && item.trim()) rawList.push(item.trim());
                    }
                }
                if (rawList.length === 0 && typeof cfg.image === 'string' && cfg.image.trim()) {
                    rawList.push(cfg.image.trim());
                }
                return rawList;
            };

            const buildBackgroundCss = (cfg, dataUrl) => {
                const opacity = typeof cfg.opacity === 'number' ? Math.max(0, Math.min(1, cfg.opacity)) : 0.65;
                const blur = typeof cfg.blur === 'number' ? Math.max(0, cfg.blur) : 0;
                const brightness = typeof cfg.brightness === 'number' ? Math.max(0, cfg.brightness) : 1.0;
                const size = typeof cfg.size === 'string' && cfg.size.trim() ? cfg.size.trim() : 'cover';
                const position = typeof cfg.position === 'string' && cfg.position.trim() ? cfg.position.trim() : 'center center';
                const surfacePct = Math.round((typeof cfg.surfaceAlpha === 'number' ? Math.max(0, Math.min(1, cfg.surfaceAlpha)) : 0.35) * 100);
                const sidebarPct = Math.round((typeof cfg.sidebarAlpha === 'number' ? Math.max(0, Math.min(1, cfg.sidebarAlpha)) : 0.30) * 100);
                const cardPct = Math.round((typeof cfg.cardAlpha === 'number' ? Math.max(0, Math.min(1, cfg.cardAlpha)) : 0.60) * 100);
                const safeUrl = dataUrl.replace(/["\\]/g, '\\$&');
                const filterParts = [];
                if (blur > 0) filterParts.push(`blur(${blur}px)`);
                if (brightness !== 1) filterParts.push(`brightness(${brightness})`);
                const filterCss = filterParts.length > 0 ? `filter: ${filterParts.join(' ')};` : '';

                return `
/* Antigravity Custom Background Patch */
:root, body, .theme-standalone {
    --color-background: color-mix(in srgb, var(--background) ${surfacePct}%, transparent) !important;
    --color-sidebar: color-mix(in srgb, var(--sidebar) ${sidebarPct}%, transparent) !important;
    --color-card: color-mix(in srgb, var(--card) ${cardPct}%, transparent) !important;
}
html, body, body.theme-standalone, #root {
    background-color: transparent !important;
}
body:not([data-has-browser-hole="true"])::before {
    content: "" !important;
    position: fixed !important;
    inset: 0 !important;
    z-index: 0 !important;
    pointer-events: none !important;
    background-image: url("${safeUrl}") !important;
    background-size: ${size} !important;
    background-position: ${position} !important;
    background-repeat: no-repeat !important;
    opacity: ${opacity} !important;
    ${filterCss}
    transition: background-image 0.8s ease-in-out, opacity 0.4s ease !important;
}
#root {
    position: relative !important;
    z-index: 1 !important;
}
body:not([data-has-browser-hole="true"]) .bg-background,
body:not([data-has-browser-hole="true"]) .\\!bg-background {
    background-color: color-mix(in srgb, var(--background) ${surfacePct}%, transparent) !important;
}
body:not([data-has-browser-hole="true"]) .bg-sidebar {
    background-color: color-mix(in srgb, var(--sidebar) ${sidebarPct}%, transparent) !important;
}
body:not([data-has-browser-hole="true"]) .agy-shell,
body:not([data-has-browser-hole="true"]) .agy-inset-shell {
    background-color: transparent !important;
    --shell-canvas: color-mix(in srgb, var(--shell) ${sidebarPct}%, transparent) !important;
}
body:not([data-has-browser-hole="true"]) .agy-sheet:not([data-sheet-inset]) {
    background-color: color-mix(in srgb, var(--background) ${surfacePct}%, transparent) !important;
}
body:not([data-has-browser-hole="true"]) .agy-sheet[data-sheet-inset] [data-main-content-body],
body:not([data-has-browser-hole="true"]) .agy-inset-shell [data-side-panel-body],
body:not([data-has-browser-hole="true"]) [data-testid="bottom-terminal-panel"],
body:not([data-has-browser-hole="true"]) [data-pane-id]:not([data-has-browser-hole="true"]),
body:not([data-has-browser-hole="true"]) .browser-hole-opaque:not([data-has-browser-hole="true"]) {
    background-color: color-mix(in srgb, var(--background) ${surfacePct}%, transparent) !important;
}
body:not([data-has-browser-hole="true"]) [data-main-content-body] .bg-background,
body:not([data-has-browser-hole="true"]) [data-side-panel-body] .bg-background,
body:not([data-has-browser-hole="true"]) [data-tiling-pane] .bg-background {
    background-color: transparent !important;
}
body:not([data-has-browser-hole="true"]) [data-split-panes] .agy-sheet[data-sheet-inset] [data-tiling-pane] {
    background-image: linear-gradient(transparent var(--split-card-top), color-mix(in srgb, var(--background) ${surfacePct}%, transparent) var(--split-card-top)) !important;
}
body:not([data-has-browser-hole="true"]) .surface-glass,
body:not([data-has-browser-hole="true"]) .surface-composer > .surface-composer-card,
body:not([data-has-browser-hole="true"]) .agy-scroll-bottom {
    background-color: color-mix(in srgb, var(--card) ${cardPct}%, transparent) !important;
    backdrop-filter: blur(12px) !important;
    -webkit-backdrop-filter: blur(12px) !important;
}
`;
            };

            const renderSlideAtIndex = async (idx) => {
                if (win.isDestroyed?.() || hubContents.isDestroyed?.() || !bgCurrentCfg) return;
                if (bgResolvedList.length === 0) return;
                const safeIdx = ((idx % bgResolvedList.length) + bgResolvedList.length) % bgResolvedList.length;
                bgSlideIndex = safeIdx;
                const dataUrl = resolveImageUrl(bgResolvedList[safeIdx]);
                if (!dataUrl) return;
                const css = buildBackgroundCss(bgCurrentCfg, dataUrl);
                const prevKey = bgCssKey;
                const key = await hubContents.insertCSS(css, { cssOrigin: 'user' }).catch(() => undefined);
                if (typeof key === 'string' && key) {
                    bgCssKey = key;
                    if (prevKey && prevKey !== key) {
                        await hubContents.removeInsertedCSS(prevKey).catch(() => undefined);
                    }
                }
            };

            const advanceSlide = () => {
                if (!bgCurrentCfg || bgResolvedList.length <= 1) return;
                let nextIdx;
                if (bgCurrentCfg.shuffle && bgResolvedList.length > 2) {
                    do {
                        nextIdx = Math.floor(Math.random() * bgResolvedList.length);
                    } while (nextIdx === bgSlideIndex);
                } else {
                    nextIdx = (bgSlideIndex + 1) % bgResolvedList.length;
                }
                void renderSlideAtIndex(nextIdx);
            };

            const applyBackgroundPatch = async () => {
                if (win.isDestroyed?.() || hubContents.isDestroyed?.()) return;
                if (bgSlideTimer) {
                    clearInterval(bgSlideTimer);
                    bgSlideTimer = null;
                }
                if (!fs.existsSync(bgConfigPath)) {
                    if (bgCssKey) {
                        await hubContents.removeInsertedCSS(bgCssKey).catch(() => undefined);
                        bgCssKey = null;
                    }
                    return;
                }
                let cfg;
                try {
                    cfg = JSON.parse(fs.readFileSync(bgConfigPath, 'utf-8'));
                } catch {
                    return;
                }
                if (!cfg || cfg.enabled === false) {
                    if (bgCssKey) {
                        await hubContents.removeInsertedCSS(bgCssKey).catch(() => undefined);
                        bgCssKey = null;
                    }
                    return;
                }
                bgCurrentCfg = cfg;
                const candidates = resolveImageCandidates(cfg);
                bgResolvedList = candidates.filter((c) => Boolean(resolveImageUrl(c)));
                if (bgResolvedList.length === 0) {
                    if (bgCssKey) {
                        await hubContents.removeInsertedCSS(bgCssKey).catch(() => undefined);
                        bgCssKey = null;
                    }
                    return;
                }
                if (typeof cfg.activeIndex === 'number' && cfg.activeIndex >= 0) {
                    bgSlideIndex = cfg.activeIndex % bgResolvedList.length;
                } else if (bgSlideIndex >= bgResolvedList.length) {
                    bgSlideIndex = 0;
                }
                await renderSlideAtIndex(bgSlideIndex);

                if (typeof cfg.captureScreenshotTo === 'string' && cfg.captureScreenshotTo.trim()) {
                    const token = `${cfg.captureScreenshotTo}:${cfg.captureToken || ''}`;
                    if (token !== lastCaptureToken) {
                        lastCaptureToken = token;
                        setTimeout(async () => {
                            try {
                                const img = await hubContents.capturePage();
                                fs.writeFileSync(cfg.captureScreenshotTo.trim(), img.toPNG());
                            } catch (e) {
                                console.error('[AGY-BG-PATCH] capturePage failed:', e);
                            }
                        }, 350);
                    }
                }

                if (bgResolvedList.length > 1) {
                    const intervalSec = typeof cfg.intervalSeconds === 'number' && cfg.intervalSeconds >= 3
                        ? cfg.intervalSeconds
                        : 60;
                    bgSlideTimer = setInterval(advanceSlide, Math.round(intervalSec * 1000));
                }
            };

            const scheduleApply = () => {
                if (bgDebounce) clearTimeout(bgDebounce);
                bgDebounce = setTimeout(() => {
                    bgDebounce = null;
                    void applyBackgroundPatch();
                }, 120);
            };

            hubContents.on('did-finish-load', () => {
                void applyBackgroundPatch();
            });
            hubContents.on('dom-ready', () => {
                void applyBackgroundPatch();
            });

            try {
                if (!fs.existsSync(bgDir)) {
                    fs.mkdirSync(bgDir, { recursive: true });
                }
                bgWatcher = fs.watch(bgDir, (_eventType, filename) => {
                    if (!filename || filename === 'config.json' || /\.(png|jpe?g|webp|gif|svg|avif|bmp)$/i.test(filename)) {
                        scheduleApply();
                    }
                });
            } catch {}

            win.on('closed', () => {
                if (bgDebounce) clearTimeout(bgDebounce);
                if (bgSlideTimer) clearInterval(bgSlideTimer);
                try { bgWatcher?.close(); } catch {}
            });
        } catch (err) {
            console.error('[AGY-BG-PATCH] Failed to initialize background patch:', err);
        }
    })();
    // === [AGY-BG-PATCH-END] ==="""


def compute_integrity(data: bytes) -> dict:
    full_hash = hashlib.sha256(data).hexdigest()
    blocks = []
    for i in range(0, len(data), BLOCK_SIZE):
        chunk = data[i : i + BLOCK_SIZE]
        blocks.append(hashlib.sha256(chunk).hexdigest())
    if not blocks:
        blocks.append(hashlib.sha256(b"").hexdigest())
    return {
        "algorithm": "SHA256",
        "hash": full_hash,
        "blockSize": BLOCK_SIZE,
        "blocks": blocks,
    }


def read_asar(asar_path: Path):
    raw = asar_path.read_bytes()
    p0, p1, p2, header_str_len = struct.unpack("<4I", raw[:16])
    data_base_offset = p1 + 8
    header_json_bytes = raw[16 : 16 + header_str_len].rstrip(b"\x00")
    header = json.loads(header_json_bytes.decode("utf-8"))
    return raw, header, data_base_offset


def build_asar(header: dict, file_payloads: dict) -> bytes:
    new_header = copy.deepcopy(header)
    chunks = []
    current_offset = 0

    def walk(node: dict, prefix: str = ""):
        nonlocal current_offset
        for name, child in node.get("files", {}).items():
            rel_path = f"{prefix}/{name}" if prefix else name
            if "files" in child:
                walk(child, rel_path)
            elif child.get("unpacked"):
                continue
            else:
                data = file_payloads[rel_path]
                child["size"] = len(data)
                child["offset"] = str(current_offset)
                if "integrity" in child:
                    child["integrity"] = compute_integrity(data)
                chunks.append(data)
                current_offset += len(data)

    walk(new_header)

    header_bytes = json.dumps(new_header, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    header_str_len = len(header_bytes)
    aligned_str_len = (header_str_len + 3) & ~3
    padding_len = aligned_str_len - header_str_len
    pickle2_payload_size = 4 + aligned_str_len
    pickle1_size = 4 + pickle2_payload_size

    preamble = struct.pack("<4I", 4, pickle1_size, pickle2_payload_size, header_str_len)
    return preamble + header_bytes + (b"\x00" * padding_len) + b"".join(chunks)


def extract_all_files(raw: bytes, header: dict, data_base_offset: int) -> dict:
    payloads = {}

    def walk(node: dict, prefix: str = ""):
        for name, child in node.get("files", {}).items():
            rel_path = f"{prefix}/{name}" if prefix else name
            if "files" in child:
                walk(child, rel_path)
            elif child.get("unpacked"):
                continue
            else:
                offset = int(child["offset"])
                size = int(child["size"])
                start = data_base_offset + offset
                payloads[rel_path] = raw[start : start + size]

    walk(header)
    return payloads


def patch_utils_js(content: str) -> tuple[str, bool]:
    injected_block = f"{TARGET_ANCHOR}\n    {build_injected_js()}"

    if PATCH_MARKER_START in content and PATCH_MARKER_END in content:
        start_idx = content.index(PATCH_MARKER_START)
        end_idx = content.index(PATCH_MARKER_END) + len(PATCH_MARKER_END)
        new_content = content[:start_idx] + build_injected_js() + content[end_idx:]
        return new_content, True

    if TARGET_ANCHOR not in content:
        raise RuntimeError(f"Target anchor not found in dist/utils.js: {TARGET_ANCHOR}")

    new_content = content.replace(TARGET_ANCHOR, injected_block, 1)
    return new_content, False


def unpatch_utils_js(content: str) -> tuple[str, bool]:
    if PATCH_MARKER_START not in content or PATCH_MARKER_END not in content:
        return content, False

    start_idx = content.index(PATCH_MARKER_START)
    end_idx = content.index(PATCH_MARKER_END) + len(PATCH_MARKER_END)
    prefix = content[:start_idx].rstrip(" \t")
    if prefix.endswith("\n"):
        prefix = prefix[:-1]
    new_content = prefix + content[end_idx:]
    return new_content, True


def write_asar_in_place(asar_path: Path, new_bytes: bytes):
    with open(asar_path, "r+b") as f:
        f.seek(0)
        f.write(new_bytes)
        f.truncate(len(new_bytes))


def cmd_install(args):
    asar_path = Path(args.asar)
    if not asar_path.exists():
        print(f"[ERROR] app.asar not found at: {asar_path}", file=sys.stderr)
        sys.exit(1)

    backup_path = asar_path.with_suffix(".asar.bak")
    raw, header, data_base_offset = read_asar(asar_path)
    payloads = extract_all_files(raw, header, data_base_offset)

    if "dist/utils.js" not in payloads:
        print("[ERROR] dist/utils.js not found inside app.asar", file=sys.stderr)
        sys.exit(1)

    utils_str = payloads["dist/utils.js"].decode("utf-8")
    already_patched = PATCH_MARKER_START in utils_str

    if not backup_path.exists() and not already_patched:
        shutil.copy2(asar_path, backup_path)
        print(f"[BACKUP] Created clean backup: {backup_path}")
    elif backup_path.exists():
        print(f"[BACKUP] Existing backup preserved: {backup_path}")

    patched_utils, was_update = patch_utils_js(utils_str)
    payloads["dist/utils.js"] = patched_utils.encode("utf-8")

    new_asar_bytes = build_asar(header, payloads)
    write_asar_in_place(asar_path, new_asar_bytes)

    action = "Updated existing" if was_update else "Installed"
    print(f"[SUCCESS] {action} background patch in: {asar_path}")
    print(f"[CONFIG]  Background config path: {get_bg_config_path()}")


def cmd_uninstall(args):
    asar_path = Path(args.asar)
    backup_path = asar_path.with_suffix(".asar.bak")

    if backup_path.exists() and not args.in_place_unpatch:
        data = backup_path.read_bytes()
        write_asar_in_place(asar_path, data)
        print(f"[SUCCESS] Restored original app.asar from backup: {backup_path}")
        return

    raw, header, data_base_offset = read_asar(asar_path)
    payloads = extract_all_files(raw, header, data_base_offset)
    utils_str = payloads["dist/utils.js"].decode("utf-8")
    unpatched_utils, changed = unpatch_utils_js(utils_str)
    if not changed:
        print("[INFO] app.asar is not currently patched.")
        return

    payloads["dist/utils.js"] = unpatched_utils.encode("utf-8")
    new_asar_bytes = build_asar(header, payloads)
    write_asar_in_place(asar_path, new_asar_bytes)
    print(f"[SUCCESS] Removed background patch from: {asar_path}")


def cmd_status(args):
    asar_path = Path(args.asar)
    backup_path = asar_path.with_suffix(".asar.bak")
    config_path = get_bg_config_path()

    print("=== Antigravity Background Patch Status ===")
    print(f"app.asar path : {asar_path} ({'exists' if asar_path.exists() else 'MISSING'})")
    print(f"Backup path   : {backup_path} ({'exists' if backup_path.exists() else 'none'})")

    if asar_path.exists():
        raw, header, data_base_offset = read_asar(asar_path)
        payloads = extract_all_files(raw, header, data_base_offset)
        utils_str = payloads.get("dist/utils.js", b"").decode("utf-8", errors="replace")
        is_patched = PATCH_MARKER_START in utils_str
        print(f"Patch status  : {'PATCHED (Active)' if is_patched else 'UNPATCHED'}")

    print(f"Config path   : {config_path} ({'exists' if config_path.exists() else 'none'})")
    if config_path.exists():
        try:
            cfg = json.loads(config_path.read_text(encoding="utf-8"))
            print("Current config:")
            print(json.dumps(cfg, indent=2, ensure_ascii=False))
        except Exception as e:
            print(f"Config read error: {e}")


def cmd_set(args):
    config_path = get_bg_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    cfg = {
        "enabled": True,
        "images": [],
        "intervalSeconds": 60,
        "shuffle": False,
        "opacity": 0.70,
        "blur": 0,
        "brightness": 1.0,
        "size": "cover",
        "position": "center center",
        "surfaceAlpha": 0.30,
        "sidebarAlpha": 0.25,
        "cardAlpha": 0.55,
    }
    if config_path.exists():
        try:
            cfg.update(json.loads(config_path.read_text(encoding="utf-8")))
        except Exception:
            pass

    def normalize_img_path(img: str) -> str:
        if not img.startswith(("http://", "https://", "data:")):
            p = Path(img).expanduser().resolve()
            if p.exists():
                return p.as_posix()
        return img

    if args.images:
        cfg["images"] = [normalize_img_path(i) for i in args.images]
        cfg["image"] = cfg["images"][0]
    elif args.image is not None:
        norm = normalize_img_path(args.image)
        cfg["image"] = norm
        cfg["images"] = [norm]

    if args.interval is not None:
        cfg["intervalSeconds"] = max(3, args.interval)
    if args.shuffle is not None:
        cfg["shuffle"] = args.shuffle
    if args.opacity is not None:
        cfg["opacity"] = max(0.0, min(1.0, args.opacity))
    if args.blur is not None:
        cfg["blur"] = max(0.0, args.blur)
    if args.brightness is not None:
        cfg["brightness"] = max(0.0, args.brightness)
    if args.size is not None:
        cfg["size"] = args.size
    if args.position is not None:
        cfg["position"] = args.position
    if args.surface_alpha is not None:
        cfg["surfaceAlpha"] = max(0.0, min(1.0, args.surface_alpha))
    if args.sidebar_alpha is not None:
        cfg["sidebarAlpha"] = max(0.0, min(1.0, args.sidebar_alpha))
    if args.card_alpha is not None:
        cfg["cardAlpha"] = max(0.0, min(1.0, args.card_alpha))
    if args.enable:
        cfg["enabled"] = True
    if args.disable:
        cfg["enabled"] = False

    config_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[UPDATED] {config_path}")
    print(json.dumps(cfg, indent=2, ensure_ascii=False))


def cmd_screenshot(args):
    config_path = get_bg_config_path()
    if not config_path.exists():
        print("[ERROR] config.json not found. Run `set` first.", file=sys.stderr)
        sys.exit(1)
    out_path = Path(args.output).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        out_path.unlink()

    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    cfg["captureScreenshotTo"] = out_path.as_posix()
    cfg["captureToken"] = str(time.time())
    if args.index is not None:
        cfg["activeIndex"] = args.index
    config_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"[CAPTURE] Requested window screenshot -> {out_path}")
    for _ in range(30):
        time.sleep(0.2)
        if out_path.exists() and out_path.stat().st_size > 0:
            break

    # Clean temporary capture keys
    cfg.pop("captureScreenshotTo", None)
    cfg.pop("captureToken", None)
    cfg.pop("activeIndex", None)
    config_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if out_path.exists() and out_path.stat().st_size > 0:
        print(f"[SUCCESS] Captured {out_path} ({out_path.stat().st_size} bytes)")
    else:
        print("[WARN] Screenshot wait timed out (ensure Antigravity has been restarted with the latest patch).")


def main():
    parser = argparse.ArgumentParser(description="Antigravity Custom Background Image & Slideshow Patcher")
    parser.add_argument("--asar", default=str(get_default_asar_path()), help="Path to Antigravity app.asar")

    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("install", help="Apply background image patch to app.asar")

    p_un = subparsers.add_parser("uninstall", help="Restore original app.asar")
    p_un.add_argument("--in-place-unpatch", action="store_true", help="Remove patch markers without using backup file")

    subparsers.add_parser("status", help="Show patch and configuration status")

    p_set = subparsers.add_parser("set", help="Update background image/slideshow and appearance settings (hot-reloads live)")
    p_set.add_argument("--image", "-i", help="Single image path or URL")
    p_set.add_argument("--images", nargs="+", help="List of image paths or URLs for automatic slideshow rotation")
    p_set.add_argument("--interval", "-t", type=int, help="Slideshow rotation interval in seconds (min 3, default: 60)")
    p_set.add_argument("--shuffle", action=argparse.BooleanOptionalAction, help="Enable or disable shuffle order (--shuffle / --no-shuffle)")
    p_set.add_argument("--opacity", "-o", type=float, help="Wallpaper opacity (0.0 to 1.0, default: 0.70)")
    p_set.add_argument("--blur", "-b", type=float, help="Wallpaper blur in pixels (default: 0)")
    p_set.add_argument("--brightness", type=float, help="Wallpaper brightness multiplier (default: 1.0)")
    p_set.add_argument("--size", help="CSS background-size (cover, contain, etc.)")
    p_set.add_argument("--position", help="CSS background-position (e.g. 'center center')")
    p_set.add_argument("--surface-alpha", type=float, help="Main content panel opacity (0.0 to 1.0, default: 0.30)")
    p_set.add_argument("--sidebar-alpha", type=float, help="Sidebar/shell opacity (0.0 to 1.0, default: 0.25)")
    p_set.add_argument("--card-alpha", type=float, help="Card/composer glass opacity (0.0 to 1.0, default: 0.55)")
    p_set.add_argument("--enable", action="store_true", help="Enable custom background")
    p_set.add_argument("--disable", action="store_true", help="Disable custom background")

    p_shot = subparsers.add_parser("screenshot", help="Capture a live screenshot of the Antigravity window via Electron capturePage()")
    p_shot.add_argument("--output", "-o", required=True, help="Output PNG path")
    p_shot.add_argument("--index", type=int, help="Optional wallpaper slide index to display before capturing")

    args = parser.parse_args()
    if not args.command or args.command == "status":
        cmd_status(args)
    elif args.command == "install":
        cmd_install(args)
    elif args.command == "uninstall":
        cmd_uninstall(args)
    elif args.command == "set":
        cmd_set(args)
    elif args.command == "screenshot":
        cmd_screenshot(args)


if __name__ == "__main__":
    main()
