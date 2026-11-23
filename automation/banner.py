#!/usr/bin/env python3
"""Build a wide banner image from an app's screenshots, side by side.

Reference style (the "iOS优质应用" channel): ONE wide banner with up to
4 iPhone screenshots side by side, no text headlines, no app icon.
The caption (not the banner) carries the text.

This module is shared with the live posting script
~/workspace/telegram-freeapps-bot/banner.py — keep the geometry identical
(fixed shot height 900, 16px gaps, 24px padding, iOS system-gray
background) so the pipeline and the live script produce the same banner.

Usage as a script:
  banner.py --shots shot1.jpg shot2.jpg [shot3.jpg shot4.jpg] --out banner.jpg
  banner.py --dir ~/workspace/devlog/assets/free-apps-20261123/iap-shots --appid 6813558062 --out banner.jpg

As a module:
  from banner import build_banner
  build_banner(['a.jpg', 'b.jpg'], 'banner.jpg')

Screenshots are scaled to equal height and laid out left to right with a
small gap on a clean light-neutral background. Up to 4 shots are used;
fewer is fine (2-shot fallback). Output is JPEG.
"""
import argparse
import os
import sys

from PIL import Image

# Banner geometry. 4 phone screenshots at equal height land near 1600px wide.
SHOT_HEIGHT = 900
GAP = 16
PAD = 24
BG = (242, 242, 247)  # iOS system gray 6 — clean light neutral
QUALITY = 88
MAX_SHOTS = 4


def build_banner(shot_paths, out_path, shot_height=SHOT_HEIGHT, gap=GAP,
                 pad=PAD, bg=BG, quality=QUALITY, max_shots=MAX_SHOTS):
    """Composite up to max_shots screenshots into one wide banner JPEG.

    Returns (out_path, width, height). Raises ValueError if no usable shots.
    """
    paths = [p for p in shot_paths if p and os.path.isfile(p)][:max_shots]
    if not paths:
        raise ValueError('no usable screenshot files: %r' % (shot_paths,))

    scaled = []
    for p in paths:
        im = Image.open(p).convert('RGB')
        w, h = im.size
        if h == 0:
            continue
        new_w = max(1, round(w * shot_height / h))
        scaled.append(im.resize((new_w, shot_height), Image.LANCZOS))
    if not scaled:
        raise ValueError('no usable screenshot files: %r' % (shot_paths,))

    total_w = sum(im.width for im in scaled) + gap * (len(scaled) - 1) + pad * 2
    total_h = shot_height + pad * 2
    canvas = Image.new('RGB', (total_w, total_h), bg)
    x = pad
    for im in scaled:
        canvas.paste(im, (x, pad))
        x += im.width + gap
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    canvas.save(out_path, 'JPEG', quality=quality)
    print(f"  banner -> {out_path} ({total_w}x{total_h})")
    return out_path, total_w, total_h


def find_shots(assets_dir, appid, subdirs=('shots', 'iap-shots')):
    """Find an app's local screenshots: <assets>/<sub>/<appid>-N.jpg, N=1..4."""
    found = []
    for sub in subdirs:
        for n in range(1, MAX_SHOTS + 1):
            p = os.path.join(assets_dir, sub, f'{appid}-{n}.jpg')
            if os.path.isfile(p):
                found.append(p)
        if found:
            break
    return found[:MAX_SHOTS]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--shots', nargs='+', default=None,
                    help='screenshot files in display order (up to 4)')
    ap.add_argument('--dir', default=None,
                    help='assets dir holding shots/ and iap-shots/ subdirs')
    ap.add_argument('--appid', default=None,
                    help='App Store id; used with --dir to locate shots')
    ap.add_argument('--out', required=True, help='output banner JPEG path')
    ap.add_argument('--height', type=int, default=SHOT_HEIGHT)
    args = ap.parse_args()

    if args.shots:
        paths = args.shots
    elif args.dir and args.appid:
        paths = find_shots(args.dir, args.appid)
    else:
        ap.error('give --shots, or --dir plus --appid')
    out, w, h = build_banner(paths, args.out, shot_height=args.height)
    print(f'{out}: {w}x{h} from {len(paths)} shot(s)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
