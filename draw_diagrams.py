# -*- coding: utf-8 -*-
"""画博客配图：网络拓扑图 + 分流示意图（泛化标签，无真实 IP/令牌）。"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import os

FONT = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
FONT_B = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
fp = font_manager.FontProperties(fname=FONT)
fp_b = font_manager.FontProperties(fname=FONT_B)
OUT = os.path.expanduser("~/workspace/devlog/assets")

BG = "#0f1115"
BOX = "#1c2230"
BOX_EDGE = "#3a4a63"
EDGE = "#8a94a6"
GOLD = "#d9a441"
GREEN = "#4caf7d"
BLUE = "#5b8dd9"
TEXT = "#e8eaf0"
SUB = "#9aa3b2"


def box(ax, x, y, w, h, title, lines, accent=GOLD, title_size=15, line_size=12):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.04",
                                linewidth=1.5, edgecolor=accent, facecolor=BOX))
    ax.text(x + w / 2, y + h - 0.22, title, ha="center", va="top",
            fontproperties=fp_b, fontsize=title_size, color=TEXT)
    for i, ln in enumerate(lines):
        ax.text(x + w / 2, y + h - 0.55 - i * 0.32, ln, ha="center", va="top",
                fontproperties=fp, fontsize=line_size, color=SUB)


def arrow(ax, x1, y1, x2, y2, label="", color=EDGE, style="-|>", lw=1.6, rad=0.0, lx=None, ly=None):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle=style, mutation_scale=14,
                                 linewidth=lw, color=color, connectionstyle=f"arc3,rad={rad}"))
    if label:
        ax.text(lx if lx is not None else (x1 + x2) / 2,
                ly if ly is not None else (y1 + y2) / 2,
                label, ha="center", va="center", fontproperties=fp, fontsize=11.5, color=color,
                bbox=dict(boxstyle="round,pad=0.25", facecolor=BG, edgecolor="none", alpha=0.9))


# ---------------- 图 1：网络拓扑 ----------------
fig, ax = plt.subplots(figsize=(10, 7.2))
fig.patch.set_facecolor(BG)
ax.set_facecolor(BG)
ax.set_xlim(0, 10)
ax.set_ylim(0, 7.2)
ax.axis("off")
ax.set_title("家庭网络拓扑（主路由＋旁路由）", fontproperties=fp_b, fontsize=19, color=TEXT, pad=14)

box(ax, 3.4, 6.0, 3.2, 0.85, "互联网", ["光猫／运营商"], accent=BLUE)
box(ax, 3.4, 4.35, 3.2, 1.25, "主路由", ["daed / OpenClash", "Cloudflare 隧道"], accent=GOLD)
box(ax, 3.4, 2.55, 3.2, 1.25, "旁路由", ["WARP 分流", "daed（备用）"], accent=GREEN)
box(ax, 0.5, 0.55, 2.6, 1.25, "电脑", ["网关 → 旁路由"], accent=EDGE)
box(ax, 6.9, 0.55, 2.6, 1.25, "手机", ["网关 → 旁路由"], accent=EDGE)
arrow(ax, 5.0, 6.0, 5.0, 5.62, "宽带入户", lx=6.2, ly=5.82)
arrow(ax, 5.0, 4.35, 5.0, 3.82, "LAN", lx=6.2, ly=4.08)
arrow(ax, 3.9, 2.55, 2.2, 1.82, "", rad=0.15)
arrow(ax, 6.1, 2.55, 7.8, 1.82, "", rad=-0.15)
ax.text(5.0, 0.15, "电脑与手机均指向旁路由；旁路由出网经主路由", ha="center", va="center",
        fontproperties=fp, fontsize=12, color=SUB)
fig.savefig(os.path.join(OUT, "topology.png"), dpi=150, facecolor=BG, bbox_inches="tight")
plt.close(fig)

# ---------------- 图 2：分流示意 ----------------
fig, ax = plt.subplots(figsize=(10, 7.2))
fig.patch.set_facecolor(BG)
ax.set_facecolor(BG)
ax.set_xlim(0, 10)
ax.set_ylim(0, 7.2)
ax.axis("off")
ax.set_title("旁路由分流示意（按域名走 WARP 或直连）", fontproperties=fp_b, fontsize=19, color=TEXT, pad=14)

box(ax, 0.4, 2.9, 2.4, 1.6, "电脑／手机", ["网关 → 旁路由"], accent=EDGE)
box(ax, 3.9, 2.9, 2.4, 1.6, "旁路由", ["按域名分流", "名单 18 个域名"], accent=GREEN)
box(ax, 7.3, 4.9, 2.3, 1.5, "走 WARP", ["YouTube、Google", "Cloudflare 等 18 站"], accent=BLUE)
box(ax, 7.3, 1.6, 2.3, 1.5, "直连", ["其余全部网站", "经主路由出网"], accent=GOLD)
arrow(ax, 2.8, 3.7, 3.9, 3.7, "", lx=3.35, ly=3.95)
arrow(ax, 6.3, 4.1, 7.3, 5.35, "名单内", lx=6.95, ly=5.0, color=BLUE)
arrow(ax, 6.3, 3.3, 7.3, 2.35, "名单外", lx=6.95, ly=2.45, color=GOLD)
ax.text(5.0, 0.9, "名单按域名后缀匹配，子域名自动覆盖；加域名只需改名单并重载", ha="center", va="center",
        fontproperties=fp, fontsize=12, color=SUB)
ax.text(5.0, 0.45, "daed 关停时 WARP 为唯一代理；daed 开启时节点优先、WARP 兜底", ha="center", va="center",
        fontproperties=fp, fontsize=12, color=SUB)
fig.savefig(os.path.join(OUT, "split.png"), dpi=150, facecolor=BG, bbox_inches="tight")
plt.close(fig)
print("OK", os.listdir(OUT))
