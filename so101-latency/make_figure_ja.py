"""Japanese comparison figure: raising P and moving to native Windows reduce SO-101 follow latency."""
import sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

sys.path.insert(0, "D:/GitHub/baito-soarm/so101-latency")
from analyze_latency import load, sample_times, best_lag  # noqa: E402

for f in ("C:/Windows/Fonts/YuGothM.ttc", "C:/Windows/Fonts/YuGothB.ttc"):
    font_manager.fontManager.addfont(f)
JP = font_manager.FontProperties(fname="C:/Windows/Fonts/YuGothM.ttc").get_name()
plt.rcParams.update({"font.family": JP, "axes.unicode_minus": False, "font.size": 10.5})
BOLD = {"fontweight": "bold"}

R = "D:/GitHub/baito-soarm/so101-latency/results/"
RUNS = {
    "wsl_p16": "latency-20261122-170204-142820-60hz-p16.csv",
    "wsl_p24": "latency-20261122-170318-403168-60hz-p24.csv",
    "win_p16": "latency-20261122-175822-321233-60hz-p16-i0-d32.csv",
    "win_p24": "latency-20261122-174451-409136-60hz-p24-d32.csv",
    "win_p32": "latency-20261122-180358-143271-60hz-p32-i0-d32.csv",
}
ARM = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll"]
BANDS = {"low": (10, 40), "mid": (40, 80)}


def band_means(path):
    d, _ = load(R + path)
    lt, st, ft = sample_times(d)
    per = {b: [] for b in BANDS}
    for j in ARM:
        sent, fol = d[f"{j}.sent"], d[f"{j}.follower"]
        vs = np.abs(np.gradient(sent, st) * 1000)
        got = {b: [] for b in BANDS}
        for w0 in np.arange(st[0] + 200, st[-1] - 900, 150):
            m = (st >= w0) & (st < w0 + 600); mf = (ft >= w0) & (ft < w0 + 1100)
            if np.ptp(sent[m]) < 4 or m.sum() < 15:
                continue
            lw, _ = best_lag(st[m], sent[m], ft[mf], fol[mf], 400)
            if lw is None or lw <= 0 or lw >= 400:
                continue
            mv = np.mean(vs[m])
            for b, (lo, hi) in BANDS.items():
                if lo <= mv < hi:
                    got[b].append(lw)
        for b in BANDS:
            if len(got[b]) >= 3:
                per[b].append(np.median(got[b]))
    p = np.diff(d["loop_ms"])
    return {"low": float(np.mean(per["low"])), "mid": float(np.mean(per["mid"])),
            "t": d["loop_ms"][1:] / 1000, "period": p, "late": int((p > 25).sum()), "n": len(p),
            "pmax": float(p.max()), "hz": float(1000 / p.mean())}


S = {k: band_means(v) for k, v in RUNS.items()}
for k, v in S.items():
    print(f"{k}: low {v['low']:.1f} mid {v['mid']:.1f} | {v['hz']:.1f} Hz late {v['late']}/{v['n']} max {v['pmax']:.1f}")

INK, INK2, MUTED, GRID, AXIS = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
C1, C2, C3 = "#2a78d6", "#eb6834", "#1baf7a"
BANDLAB = ["低速\n10–40 deg/s", "中速\n40–80 deg/s"]

fig = plt.figure(figsize=(13, 10), dpi=170, facecolor="white")
gs = fig.add_gridspec(2, 2, hspace=0.62, wspace=0.20, left=0.065, right=0.98, top=0.80, bottom=0.135)
fig.text(0.065, 0.955, "SO-ARM101 追従遅延の比較", fontsize=19, fontweight="bold", color=INK)
fig.text(0.065, 0.918, "フォロワーの位置ゲイン P を上げ、WSL（usbipd）から Windows 直結に移すことで、"
         "リーダーに対するフォロワーの遅れが約 35% 減少", fontsize=11.5, color=INK2)


def style(ax, ymax, ylabel="遅延 [ms]"):
    ax.set_ylim(0, ymax)
    ax.yaxis.grid(True, color=GRID, lw=0.8); ax.set_axisbelow(True)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(AXIS)
    ax.tick_params(colors=MUTED, length=0, labelsize=10)
    ax.set_ylabel(ylabel, color=INK2, fontsize=10)


def bars(ax, groups, series, colors, labels, ymax):
    n = len(series); w = 0.8 / n
    x = np.arange(len(groups))
    for i, (vals, c, lab) in enumerate(zip(series, colors, labels)):
        xs = x - 0.4 + w * (i + 0.5)
        ax.bar(xs, vals, width=w * 0.9, color=c, label=lab, zorder=3)
        for xx, v in zip(xs, vals):
            ax.text(xx, v + ymax * 0.015, f"{v:.0f}", ha="center", va="bottom", fontsize=9.5, color=INK2)
    ax.set_xticks(x, groups, color=INK2)
    style(ax, ymax)
    ax.legend(frameon=False, fontsize=9.5, loc="lower left", ncol=n, labelcolor=INK2,
              handlelength=1.0, columnspacing=1.2, bbox_to_anchor=(0, 1.0), borderaxespad=0.2)


def title(ax, tag, text, sub, note=None):
    ax.text(0, 1.25, f"{tag}  {text}", transform=ax.transAxes, fontsize=13, color=INK, **BOLD)
    ax.text(0, 1.155, sub, transform=ax.transAxes, fontsize=9.5, color=MUTED)
    if note:
        ax.text(1, 1.155, note, transform=ax.transAxes, ha="right", fontsize=10.5, color=INK, **BOLD)


# (a) P gain on Windows
ax = fig.add_subplot(gs[0, 0])
ser = [[S[k]["low"], S[k]["mid"]] for k in ("win_p16", "win_p24", "win_p32")]
bars(ax, BANDLAB, ser, [C1, C2, C3], ["P=16（LeRobot 既定）", "P=24", "P=32"], 125)
red = 1 - S["win_p32"]["mid"] / S["win_p16"]["mid"]
title(ax, "A", "P ゲインの効果", "Windows 直結 · D=32 · J1〜J5 平均", f"P=16 → 32 で約 {red*100:.0f}% 短縮")

# (b) environment at P=24
ax = fig.add_subplot(gs[0, 1])
ser = [[S[k]["low"], S[k]["mid"]] for k in ("wsl_p24", "win_p24")]
bars(ax, BANDLAB, ser, [C1, C2], ["WSL（usbipd 経由）", "Windows 直結"], 125)
title(ax, "B", "実行環境の効果：遅延", "P=24 · D=32 · J1〜J5 平均",
      f"低速で約 {S['wsl_p24']['low'] - S['win_p24']['low']:.0f} ms 短縮")

# (c) frame time trace
ax = fig.add_subplot(gs[1, 0])
for k, c, lab in (("wsl_p24", C1, "WSL（usbipd 経由）"), ("win_p24", C2, "Windows 直結")):
    ax.plot(S[k]["t"], S[k]["period"], color=c, lw=1.0, label=lab, zorder=3 if k == "win_p24" else 2)
ax.axhline(25, color=MUTED, lw=0.9, ls=(0, (3, 3)), zorder=4)
ax.text(0.2, 27, "25 ms を超えると引っかかり", ha="left", va="bottom", fontsize=9, color=INK2, zorder=5,
        bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.9))
ax.set_xlim(0, 15); ax.set_xlabel("時間 [s]", color=INK2, fontsize=10)
style(ax, 170, "1 フレームの処理時間 [ms]")
ax.legend(frameon=False, fontsize=9.5, loc="lower left", ncol=2, labelcolor=INK2, bbox_to_anchor=(0, 1.0),
          borderaxespad=0.2)
w, n = S["wsl_p24"], S["win_p24"]
title(ax, "C", "実行環境の効果：通信の引っかかり", "P=24 · 60 Hz（目標 16.7 ms / フレーム）")
ax.text(0.985, 0.96, f"WSL：引っかかり {w['late']} / {w['n']} フレーム、最大 {w['pmax']:.0f} ms\n"
        f"Windows：引っかかり {n['late']} / {n['n']} フレーム、最大 {n['pmax']:.0f} ms",
        transform=ax.transAxes, ha="right", va="top", fontsize=9.5, color=INK, linespacing=1.6, zorder=5,
        bbox=dict(boxstyle="round,pad=0.4", fc="white", ec=GRID, alpha=0.95))

# (d) overall
ax = fig.add_subplot(gs[1, 1])
ser = [[S[k]["low"], S[k]["mid"]] for k in ("wsl_p16", "win_p32")]
bars(ax, BANDLAB, ser, [MUTED, C1], ["当初（WSL · P=16）", "最終（Windows · P=32）"], 140)
title(ax, "D", "総合：当初設定と最終設定", "D=32 · J1〜J5 平均")
for i, b in enumerate(("low", "mid")):
    a, z = S["wsl_p16"][b], S["win_p32"][b]
    ax.text(i, a + 14, f"−{a - z:.0f} ms（−{(1 - z / a) * 100:.0f}%）", ha="center", va="bottom",
            fontsize=10.5, color=INK, **BOLD)

fig.text(0.065, 0.022,
         "測定条件：LeRobot 0.7.0、SO-ARM101、60 Hz、6 関節同時の自由追従、各条件 15 秒。遅延は書き込んだ指令とフォロワー実位置の曲線を"
         "時間方向にずらして重ねた値（0.6 秒区間ごと、同じ速度帯の中央値）。\n"
         "P=32 は WSL では振動が目立つため、WSL で使う場合は P=24 を推奨。グリッパーはトルク制限のため集計対象外。",
         fontsize=8.8, color=MUTED, linespacing=1.6)

out = sys.argv[1]
fig.savefig(out, dpi=170, facecolor="white")
print("saved", out)
