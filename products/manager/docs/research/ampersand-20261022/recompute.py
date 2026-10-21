#!/usr/bin/env python3
"""Recompute published Ampersand chart aggregates without running JavaScript.

The numeric calculation uses only the Python standard library. Optional original
figures use Matplotlib and a caller-supplied Japanese font. This is an arithmetic
audit of publisher data, not a model invocation or an independent benchmark.
"""
from __future__ import annotations

import argparse
from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile


HERE = Path(__file__).resolve().parent
SOURCES = {
    "life_combined": {
        "url": "https://ampersand.humansand.ai/blog/life-combined-data.js?v=no-note-1",
        "retrieved_at": "2026-10-21T23:33:45.463593Z",
        "bytes": 2046,
        "sha256": "196aff6d814a702058528c8d158e32d00340dde40e0096b9553f364dd4f917f1",
    },
    "evaluation_display": {
        "url": "https://ampersand.humansand.ai/blog/evaluations.js",
        "retrieved_at": "2026-10-21T23:33:45.633121Z",
        "bytes": 63968,
        "sha256": "f5160c6d396acb368a52f2358b16c112b645f7551a61c1de1cfac166f70bbc89",
    },
}
WEIGHTS = (Decimal("0"), Decimal("0.2"), Decimal("0.3"))
MODEL_NAMES = {
    "Gemini 3.8 Flash", "Fable 5.1", "Ampersand", "Muse Spark 1.3",
    "Kimi K3", "Opus 5.5", "GPT-6 Astra", "GPT-6.1 Sol", "GLM 5.3",
}


def read_pinned(path: Path, key: str) -> str:
    data = path.read_bytes()
    spec = SOURCES[key]
    if len(data) != spec["bytes"] or hashlib.sha256(data).hexdigest() != spec["sha256"]:
        raise ValueError(f"{key}: source differs from the recorded public snapshot")
    return data.decode("utf-8")


def parse_rows(source: str) -> list[dict]:
    match = re.search(r"window\.AMP_LIFE_COMBINED\s*=\s*(\[.*?\])\s*;", source, re.S)
    if not match:
        raise ValueError("public aggregate array not found")
    # Only transform the pinned data literal. Do not execute functions, import JS,
    # or preserve source comments (which are irrelevant to the arithmetic).
    literal = re.sub(r"//[^\n]*", "", match.group(1))
    literal = re.sub(r"'([^'\\]*)'", lambda m: json.dumps(m.group(1)), literal)
    literal = re.sub(r"([{,]\s*)([A-Za-z_]\w*)\s*:", r'\1"\2":', literal)
    literal = re.sub(r",\s*(?=[}\]])", "", literal)
    parsed = json.loads(literal, parse_float=Decimal, parse_int=Decimal)
    if not isinstance(parsed, list) or len(parsed) != 9:
        raise ValueError("expected nine published model aggregates")
    allowed = {"name", "goal", "cost", "costError", "seTerms", "featured"}
    required = allowed - {"featured"}
    rows = []
    for row in parsed:
        if not isinstance(row, dict) or not required <= row.keys() or row.keys() - allowed:
            raise ValueError("unexpected aggregate fields")
        if row["name"] not in MODEL_NAMES:
            raise ValueError("unexpected model name")
        numbers = [row["goal"], row["cost"], row["costError"]]
        terms = row["seTerms"]
        if not isinstance(terms, list) or len(terms) != 3:
            raise ValueError("three standard-error terms required")
        if any(not isinstance(x, Decimal) or not x.is_finite() for x in numbers + terms):
            raise ValueError("finite published numbers required")
        if min(numbers + [terms[0], terms[2]]) < 0 or terms[1] ** 2 > terms[0] * terms[2]:
            raise ValueError("invalid published variance or cost")
        rows.append({key: row[key] for key in ("name", "goal", "cost", "costError", "seTerms")})
    if {r["name"] for r in rows} != MODEL_NAMES:
        raise ValueError("duplicate or missing model")
    return rows


def default_weight(source: str) -> Decimal:
    matches = re.findall(r"const\s+weights\s*=\s*\{\s*life\s*:\s*([0-9.]+)\s*,", source)
    if len(matches) != 1:
        raise ValueError("expected one published life-chart default weight")
    value = Decimal(matches[0])
    if value != Decimal("0.2"):
        raise ValueError("published default changed")
    return value


def score(row: dict, weight: Decimal) -> Decimal:
    return row["goal"] - weight * row["cost"]


def ranked(rows: list[dict], weight: Decimal) -> list[dict]:
    ordered = sorted(rows, key=lambda row: (-score(row, weight), row["name"]))
    return [{"rank": i + 1, "name": row["name"], "score": float(score(row, weight))}
            for i, row in enumerate(ordered)]


def recompute(life: str, display: str) -> tuple[dict, list[dict]]:
    rows = parse_rows(life)
    weight = default_weight(display)
    by_name = {row["name"]: row for row in rows}
    gap = score(by_name["Fable 5.1"], weight) - score(by_name["Ampersand"], weight)
    # Direct arithmetic sanity checks on the frozen public values.
    assert gap == Decimal("0.00254")
    assert [ranked(rows, w)[0]["name"] for w in WEIGHTS] == [
        "Ampersand", "Fable 5.1", "Gemini 3.8 Flash"]
    aggregates = []
    for row in rows:
        a, b, c = row["seTerms"]
        variance = a - 2 * weight * b + weight * weight * c
        aggregates.append({
            "name": row["name"], "goal": float(row["goal"]), "cost": float(row["cost"]),
            "published_cost_error": float(row["costError"]),
            "published_se_terms": [float(x) for x in row["seTerms"]],
            "score_at_published_weight": float(score(row, weight)),
            "standard_error_at_published_weight": round(math.sqrt(float(variance)), 12),
        })
    report = {
        "schema": "manager.ampersand.public-aggregate-recalculation.v1",
        "sources": SOURCES,
        "calculation": {
            "formula": "score = goal - weight * cost",
            "standard_error_formula": "sqrt(A - 2 * weight * B + weight^2 * C)",
            "published_default_weight": float(weight),
            "arithmetic": "Decimal arithmetic on the published decimal values; no JavaScript execution",
            "weight_sensitivity": "Alternative weights change the arithmetic on fixed aggregates, not the model outputs",
            "units": "Publisher-defined goal progress and V9 interaction cost; these are not dollars or human welfare units",
        },
        "model_aggregates": aggregates,
        "rankings": [{"weight": float(w), "numerical_order": ranked(rows, w)} for w in WEIGHTS],
        "fable_minus_ampersand_at_published_weight": float(gap),
        "boundary": {
            "analysis_type": "Recalculation of company-published simulation aggregates",
            "model_inference_calls": 0,
            "new_simulation_runs": 0,
            "human_participants_recruited": 0,
            "javascript_executed": False,
            "raw_individual_records_retained": False,
            "source_comments_or_internal_links_retained": False,
            "api_access_observation": "A separate unauthenticated GET of /v1/models returned HTTP 401; inference was not run",
            "significance": "No paired model-difference test or causal inference was performed",
            "standard_error_scope": "Publisher-reported within-scenario repeat variation; not generalization to real populations",
            "interpretation": "Numerical ordering depends on the cost weight and does not establish a practically meaningful winner",
        },
    }
    return report, rows


def check_reference(path: Path, rows: list[dict], weight: Decimal) -> None:
    reference = json.loads(path.read_text())
    existing = {r["name"]: r for r in reference["rows"]}
    if set(existing) != MODEL_NAMES:
        raise ValueError("reference model set differs")
    for row in rows:
        ref = existing[row["name"]]
        for field in ("goal", "cost"):
            if Decimal(str(ref[field])) != row[field]:
                raise ValueError(f"reference mismatch: {row['name']} {field}")
        if abs(float(score(row, weight)) - ref["score"]) > 1e-10:
            raise ValueError(f"reference score mismatch: {row['name']}")


def figures(rows: list[dict], output: Path, japanese_font: Path) -> None:
    """Render original explanatory figures, never screenshots of vendor charts."""
    os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "ampersand-matplotlib"))
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import font_manager
    from matplotlib import pyplot as plt
    from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

    font_manager.fontManager.addfont(str(japanese_font))
    japanese_family = font_manager.FontProperties(fname=str(japanese_font)).get_name()
    output.mkdir(parents=True, exist_ok=True)
    ink = "#193447"
    paper = "#f8f7f3"
    colors = {"Ampersand": "#8061a8", "Fable 5.1": "#16827d",
              "Gemini 3.8 Flash": "#d28329", "Muse Spark 1.3": "#526f9a"}
    selected = [r for name in colors for r in rows if r["name"] == name]
    for lang in ("en", "ja"):
        jp = lang == "ja"
        plt.rcParams.update({"font.family": japanese_family if jp else "DejaVu Sans",
                             "font.size": 13, "axes.unicode_minus": False,
                             "text.color": ink, "axes.labelcolor": ink,
                             "xtick.color": ink, "ytick.color": ink})
        fig = plt.figure(figsize=(14, 9), facecolor=paper)
        fig.text(.055, .94, "人の反応を予測して学ぶ。その後、現実で確かめる。" if jp else
                 "Practice with predicted reactions. Then test in reality.", fontsize=24, weight="bold")
        fig.text(.055, .894, "一般的な学習の考え方を示す概念図。Ampersandの非公開の内部構造を表すものではありません。" if jp else
                 "A conceptual teaching diagram. It does not specify undisclosed Ampersand internals.", fontsize=12.7, color="#526473")
        left = fig.add_axes([.055, .15, .56, .68]); left.set_xlim(0, 1); left.set_ylim(0, 1); left.axis("off")
        right = fig.add_axes([.665, .15, .285, .68]); right.set_xlim(0, 1); right.set_ylim(0, 1); right.axis("off")
        left.text(0, .98, "A  模擬環境で学習する" if jp else "A  Learn in a simulated interaction", fontsize=17, weight="bold")
        right.text(0, .98, "B  現実で別に検証する" if jp else "B  Evaluate in the real world", fontsize=16, weight="bold")

        def box(ax, xy, wh, label, fill, fontsize=14):
            x, y = xy; w, h = wh
            ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.012,rounding_size=0.02",
                                       linewidth=1.2, edgecolor="#ccd4d8", facecolor=fill))
            ax.text(x + w / 2, y + h / 2, label, ha="center", va="center", fontsize=fontsize,
                    linespacing=1.6, multialignment="center")

        def arrow(ax, start, end, label=None, label_xy=None):
            ax.add_patch(FancyArrowPatch(start, end, arrowstyle="-|>", mutation_scale=20,
                                        linewidth=1.8, color="#526473"))
            if label:
                ax.text(*label_xy, label, fontsize=11.5, ha="center", va="center", color="#526473",
                        bbox={"facecolor": paper, "edgecolor": "none", "pad": 3})

        box(left, (.015, .65), (.40, .19), "AIの方策\n返信・道具の使用・\n何もしない、を選ぶ" if jp else
            "Assistant policy\nChoose a reply, a tool action,\nor NO_ACTION", "#e6eef5")
        box(left, (.58, .65), (.40, .19), "人・環境のモデル\n相手の反応と\n状況の変化を予測する" if jp else
            "User / world model\nPredict reactions and\nchanges in the situation", "#eee7f6")
        box(left, (.58, .22), (.40, .22), "報酬・評価規則\n目的の進展、手間、\n誤りや害を採点する" if jp else
            "Reward / evaluation rule\nScore progress, effort,\nerrors and harms", "#fbefda")
        box(left, (.015, .22), (.40, .22), "学習による更新\n高く評価された選択を\n選びやすくする" if jp else
            "Learning update\nMake better-scoring\nchoices more likely", "#e4f1ea")
        arrow(left, (.43, .745), (.565, .745), "行動" if jp else "Action", (.497, .80))
        arrow(left, (.78, .635), (.78, .455), "予測した結果" if jp else "Predicted outcome", (.78, .545))
        arrow(left, (.565, .33), (.43, .33), "評価" if jp else "Score", (.497, .39))
        arrow(left, (.215, .455), (.215, .635), "更新" if jp else "Update", (.215, .545))
        left.text(0, .08, "人のモデルは予測し、評価規則は採点し、AIの方策は行動を選ぶ。" if jp else
                  "The user model predicts; the rule scores; the assistant chooses.", fontsize=12)
        box(right, (.025, .67), (.94, .16), "方策と検証計画を固定する" if jp else
            "Freeze the policy\nand evaluation plan", "#ffffff", 13.5)
        box(right, (.025, .40), (.94, .16), "実際の課題と結果を観測する" if jp else
            "Observe actual tasks\nand their outcomes", "#ffffff", 13.5)
        box(right, (.025, .10), (.94, .19), "比較対象と照合し、\n費用・失敗・害も記録する" if jp else
            "Compare with a baseline;\nrecord costs, failures\nand harms", "#ffffff", 13.5)
        arrow(right, (.495, .65), (.495, .58)); arrow(right, (.495, .38), (.495, .31))
        fig.text(.055, .063, "模擬環境で高い報酬を得ても、現実の便益は別の証拠で確認する必要があります。" if jp else
                 "A high simulated reward still requires independent evidence of real-world benefit.", fontsize=14, weight="bold")
        fig.savefig(output / f"ampersand-training-loop-{lang}.png", dpi=180, facecolor=paper,
                    metadata={"Software": "Manager research: original conceptual figure"})
        plt.close(fig)

        fig = plt.figure(figsize=(14, 9), facecolor=paper)
        fig.text(.055, .94, "コストをどう重く見るかで、数値の順位は変わる" if jp else
                 "The numerical ranking changes with the cost weight", fontsize=24, weight="bold")
        fig.text(.055, .891, "公開集計値を再計算：得点 = 目的の進展 − λ × 相互作用のコスト" if jp else
                 "Recomputed public aggregates: score = goal progress − λ × interaction cost", fontsize=14)
        ax = fig.add_axes([.08, .22, .59, .59], facecolor=paper)
        weights = [Decimal(i) / 1000 for i in range(401)]
        for row in selected:
            ax.plot([float(w) for w in weights], [float(score(row, w)) for w in weights],
                    color=colors[row["name"]], lw=3.0 if row["name"] == "Ampersand" else 2.5,
                    label=row["name"])
        ax.axvline(.2, color="#627382", ls=(0, (4, 4)), lw=1.4)
        ax.text(.206, 13.98, "公開ページの設定 λ = 0.2" if jp else "Published setting: λ = 0.2",
                fontsize=11.5, color="#526473", va="top")
        ax.set_xlim(0, .4); ax.set_ylim(11.7, 14.03)
        ax.set_xticks([0, .1, .2, .3, .4]); ax.set_yticks([12.0, 12.5, 13.0, 13.5, 14.0])
        ax.set_xlabel("相互作用コストの重み λ" if jp else "Weight on interaction cost, λ", labelpad=13, fontsize=14)
        ax.set_ylabel("再計算した得点" if jp else "Recomputed score", labelpad=12, fontsize=14)
        ax.grid(axis="y", color="#dfe3e4", lw=.9)
        for side in ("top", "right"): ax.spines[side].set_visible(False)
        for side in ("left", "bottom"): ax.spines[side].set_color("#b6c2c9")
        ax.legend(loc="lower left", frameon=False, ncol=2, fontsize=11.7)
        side = fig.add_axes([.725, .22, .23, .59]); side.set_xlim(0, 1); side.set_ylim(0, 1); side.axis("off")
        side.text(0, .985, "数値上の上位3モデル" if jp else "Top three by arithmetic", fontsize=14.5, weight="bold", va="top")
        for i, w in enumerate(WEIGHTS):
            y = .84 - i * .32
            side.text(0, y, f"λ = {w}", fontsize=15, weight="bold")
            for j, row in enumerate(ranked(rows, w)[:3]):
                ry = y - .065 * (j + 1)
                side.text(0, ry, str(j + 1), fontsize=11.3, color="#607381")
                side.text(.08, ry, row["name"], fontsize=11.3, color=colors[row["name"]])
                side.text(1, ry, f"{row['score']:.5f}", fontsize=11.3, ha="right")
        fig.text(.055, .116, "λ = 0.2：FableとAmpersandの差は 0.00254。統計的・実用的な優劣を示す検定は行っていません。" if jp else
                 "At λ = 0.2, Fable − Ampersand = 0.00254. This calculation does not test statistical or practical superiority.", fontsize=12)
        fig.text(.055, .075, "会社が公開した模擬実験の集計値9モデルから再計算（図は4モデル）。新しいモデル実行や人の効果測定ではありません。" if jp else
                 "Reanalysis of nine company-published simulation aggregates (four plotted). No new model runs or human-effect measurements.", fontsize=11.6, color="#526473")
        fig.text(.055, .035, "出典：humans& 公開JavaScript、2026年10月21日取得。出典ハッシュと計算方法は付属記録に掲載。" if jp else
                 "Source: humans& public JavaScript, retrieved 21 Oct 2026. Source hashes and calculation method are in the accompanying record.", fontsize=11, color="#526473")
        fig.savefig(output / f"ampersand-score-weight-{lang}.png", dpi=180, facecolor=paper,
                    metadata={"Software": "Manager research: original public-aggregate reanalysis"})
        plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--life-js", type=Path, required=True)
    parser.add_argument("--evaluations-js", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=HERE / "observations.json")
    parser.add_argument("--reference-json", type=Path)
    parser.add_argument("--figures", action="store_true")
    parser.add_argument("--japanese-font", type=Path)
    parser.add_argument("--figure-dir", type=Path, default=HERE.parents[1] / "articles" / "figures")
    args = parser.parse_args()
    report, rows = recompute(read_pinned(args.life_js, "life_combined"),
                             read_pinned(args.evaluations_js, "evaluation_display"))
    if args.reference_json:
        check_reference(args.reference_json, rows, Decimal(str(report["calculation"]["published_default_weight"])))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.figures:
        if not args.japanese_font or not args.japanese_font.is_file():
            parser.error("--figures requires --japanese-font pointing to a Japanese-capable font")
        figures(rows, args.figure_dir, args.japanese_font)
    print(json.dumps({"models": len(rows), "weights": [float(w) for w in WEIGHTS],
                      "published_default_weight": .2,
                      "fable_minus_ampersand": report["fable_minus_ampersand_at_published_weight"],
                      "model_inference_calls": 0,
                      "output_sha256": hashlib.sha256(args.output.read_bytes()).hexdigest()}, sort_keys=True))


if __name__ == "__main__":
    main()
