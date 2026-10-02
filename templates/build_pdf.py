#!/usr/bin/env python3
"""Markdownソース (src/*.md) を結合してPDF教科書を生成する。

使い方: 下の設定ブロック (TITLE〜COVER_META) を書き換えて `python3 build_pdf.py`。
生成後に pypdf でテキスト層の検証（Identity-H チェック・タイトル抽出確認）まで行う。

数式: 本文中の $...$（インライン）と $$...$$（別行立て）を LaTeX として
MathJax (node) でSVG化して埋め込む。コードブロック・インラインコード内の $ は対象外。
リテラルの $ は \\$ と書く。MathJax は ~/.cache/textbook-mathjax に自動インストールされる。
"""
import base64
import glob
import json
import os
import re
import subprocess
import sys
import tempfile

import markdown
import weasyprint

# ============ 設定ブロック（教科書ごとにここだけ書き換える） ============
TITLE = "○○教科書"                      # 書名（表紙・検証に使用）
HEADER = "○○教科書 — サブタイトル"       # 各ページ右上のランニングヘッダ
OUT_NAME = "○○教科書.pdf"               # 出力ファイル名（リポジトリ直下に生成）
COVER_SUB = [                            # 表紙のサブタイトル行（複数可）
    "サブタイトル1行目",
    "サブタイトル2行目（ハンズオン内容など）",
]
COVER_META = "2026年○月版（対象バージョン: ○○）"
# =======================================================================

BASE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(BASE, "src")
OUT = os.path.join(BASE, OUT_NAME)

# フォントは ~/.local/share/fonts の Noto Sans CJK JP を fontconfig 経由で参照する
# （WeasyPrint は CID型OTF の @font-face 読込に失敗するため）
STYLE = """
@page {
  size: A4;
  margin: 22mm 18mm 20mm 18mm;
  @bottom-center { content: counter(page) " / " counter(pages); font-family: 'Noto Sans CJK JP'; font-size: 8pt; color: #666; }
  @top-right { content: "%HEADER%"; font-family: 'Noto Sans CJK JP'; font-size: 7.5pt; color: #999; }
}
@page cover { @bottom-center { content: none; } @top-right { content: none; } }
body { font-family: 'Noto Sans CJK JP', sans-serif; font-size: 9.5pt; line-height: 1.75; color: #1a1a2e; }
.cover { page: cover; text-align: center; padding-top: 70mm; page-break-after: always; }
.cover h1 { font-size: 24pt; color: #0f3a8a; border: none; margin-bottom: 8mm; page-break-before: avoid; }
.cover .sub { font-size: 13pt; color: #333; margin-bottom: 4mm; }
.cover .meta { font-size: 10pt; color: #777; margin-top: 30mm; }
.toc { page-break-after: always; }
.toc h1 { page-break-before: avoid; }
.toc ul { list-style: none; padding-left: 1em; }
.toc a { text-decoration: none; color: #1a1a2e; }
h1 { font-size: 17pt; color: #0f3a8a; border-bottom: 2.5pt solid #0f3a8a; padding-bottom: 2mm; page-break-before: always; margin-top: 0; }
h2 { font-size: 12.5pt; color: #14532d; border-left: 3.5pt solid #16a34a; padding-left: 2.5mm; margin-top: 7mm; page-break-after: avoid; }
h3 { font-size: 10.5pt; color: #0f3a8a; margin-top: 5mm; page-break-after: avoid; }
code { font-family: 'Noto Sans Mono CJK JP', monospace; font-size: 8.3pt; background: #f1f5f9; padding: 0.5pt 2pt; border-radius: 2pt; }
pre { background: #f6f8fa; border: 0.5pt solid #d0d7de; border-radius: 3pt; padding: 2.5mm; page-break-inside: avoid; line-height: 1.45; }
pre code { background: none; padding: 0; font-size: 8.3pt; white-space: pre-wrap; overflow-wrap: break-word; }
table { border-collapse: collapse; width: 100%; margin: 3mm 0; font-size: 8.8pt; page-break-inside: avoid; }
th, td { border: 0.5pt solid #94a3b8; padding: 1.2mm 2mm; text-align: left; vertical-align: top; }
th { background: #e2e8f0; }
blockquote { background: #fefce8; border-left: 3pt solid #eab308; margin: 3mm 0; padding: 1.5mm 3mm; page-break-inside: avoid; }
blockquote p { margin: 1mm 0; }
hr { border: none; border-top: 0.5pt solid #cbd5e1; }
img.math { }
img.math-display { display: block; margin: 2.5mm auto; page-break-inside: avoid; }
/* チャート式風の例題ブロック */
.reidai { border: 1.1pt solid #0f3a8a; border-radius: 2pt; margin: 4.5mm 0; }
.reidai-head { background: #0f3a8a; color: #fff; padding: 1.4mm 3mm; page-break-after: avoid; }
.reidai-head .kind { font-weight: bold; margin-right: 3mm; }
.reidai-head .stars { float: right; color: #fde047; letter-spacing: 0.8pt; }
.reidai-problem { padding: 2mm 3mm; page-break-inside: avoid; }
.reidai-problem p:first-child, .reidai-sec p:first-child { margin-top: 0.5mm; }
.reidai-problem p:last-child, .reidai-sec p:last-child { margin-bottom: 0.5mm; }
.reidai-sec { padding: 1.5mm 3mm 2mm; border-top: 0.5pt solid #cbd5e1; }
.reidai-sec::before { content: attr(data-label); display: block; font-weight: bold; margin-bottom: 0.5mm; }
.sec-shishin { background: #eff6ff; }
.sec-shishin::before { color: #1d4ed8; }
.sec-kaito::before { color: #dc2626; }
.sec-bekkai::before { color: #dc2626; }
.sec-kento { background: #f8fafc; }
.sec-kento::before { color: #475569; }
.sec-renshu { background: #f0fdf4; }
.sec-renshu::before { color: #15803d; }
.codehilite .k, .codehilite .kn, .codehilite .ow { color: #cf222e; }
.codehilite .s1, .codehilite .s2, .codehilite .sd { color: #0a3069; }
.codehilite .c1 { color: #6e7781; font-style: italic; }
.codehilite .nf { color: #8250df; }
.codehilite .mi, .codehilite .mf { color: #0550ae; }
""".replace("%HEADER%", HEADER)

# Noto Sans CJK JP にグリフがない絵文字が1つでもあると WeasyPrint が
# Identity-H でない特殊 CMap を出力し、PDF全体のテキスト抽出が壊れる。
# フォントにある記号へ置換する（豆腐化の回避も兼ねる）
REPLACEMENTS = {
    "💡": "※", "⚠️": "※", "⚠": "※",
    "❌": "×", "⭕": "○", "✅": "○", "✔": "○",
    "🚀": "", "📌": "・", "👍": "○",
    "️": "",  # 異体字セレクタ
}
# 置換後も残っている絵文字類の検出。非BMP絵文字と異体字セレクタは確実に
# フォント未収録なのでハードエラー、BMP内の記号類（★♪なども含む範囲）は
# 収録済みの場合があるため警告に留める（最終防衛線は verify() の Identity-H 検査）
EMOJI_FATAL_RE = re.compile("[\U0001F000-\U0001FAFF️]")
EMOJI_WARN_RE = re.compile("[☀-⛿✀-➿⬀-⯿]")

# ---------------------------- 数式レンダリング ----------------------------
MATHJAX_PREFIX = os.path.expanduser("~/.cache/textbook-mathjax")
MATHJAX_PKG = os.path.join(MATHJAX_PREFIX, "node_modules", "mathjax")

# stdin から [{tex, display}, ...] を受け取り、SVG文字列の配列を stdout に返す
TEX2SVG_JS = """
const fs = require('fs');
require(process.argv[2]).init({
  loader: { load: ['input/tex', 'output/svg'] },
  tex: { packages: { '[+]': ['ams'] } },
  svg: { fontCache: 'none' },
}).then((MathJax) => {
  const items = JSON.parse(fs.readFileSync(0, 'utf8'));
  const out = items.map((it) => {
    const node = MathJax.tex2svg(it.tex, { display: it.display });
    return MathJax.startup.adaptor.outerHTML(node.children[0]);
  });
  process.stdout.write(JSON.stringify(out));
}).catch((e) => { console.error(e); process.exit(1); });
"""

DISPLAY_MATH_RE = re.compile(r"\$\$(.+?)\$\$", re.S)
INLINE_MATH_RE = re.compile(r"(?<![\\$])\$([^$\n]+?)(?<!\\)\$")
SVG_ATTR_RE = re.compile(
    r'style="vertical-align:\s*(-?[\d.]+)(?:ex)?;?[^"]*".*?width="([\d.]+)ex" height="([\d.]+)ex"',
    re.S,
)


def extract_math(text, start=0):
    """コードブロック・インラインコードを避けて $..$ / $$..$$ をトークンに置換する。

    start は通し番号の開始値（複数ファイル間でトークンが衝突しないようにする）。
    返り値: (トークン化済みテキスト, [(token, tex, display), ...])
    """
    found = []

    def _repl(display):
        def inner(m):
            token = f"MJXTOKEN{start + len(found)}X"
            found.append((token, m.group(1).strip(), display))
            return token
        return inner

    parts = re.split(r"(```[\s\S]*?(?:```|\Z))", text)  # フェンスコードを分離
    for i, part in enumerate(parts):
        if part.startswith("```"):
            continue
        subs = re.split(r"(`[^`\n]+`)", part)  # インラインコードを分離
        for j, sp in enumerate(subs):
            if sp.startswith("`"):
                continue
            sp = DISPLAY_MATH_RE.sub(_repl(True), sp)
            sp = INLINE_MATH_RE.sub(_repl(False), sp)
            subs[j] = sp.replace("\\$", "$")
        parts[i] = "".join(subs)
    return "".join(parts), found


def render_math(items):
    """MathJax で [(token, tex, display)] → {token: <img>タグ} を作る。"""
    if not items:
        return {}
    if not os.path.isdir(MATHJAX_PKG):
        print("installing mathjax to", MATHJAX_PREFIX)
        subprocess.run(
            ["npm", "install", "--prefix", MATHJAX_PREFIX,
             "--no-fund", "--no-audit", "mathjax@3"],
            check=True,
        )
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as jf:
        jf.write(TEX2SVG_JS)
        jspath = jf.name
    try:
        proc = subprocess.run(
            ["node", jspath, MATHJAX_PKG],
            input=json.dumps([{"tex": t, "display": d} for _, t, d in items]),
            capture_output=True, text=True,
        )
    finally:
        os.unlink(jspath)
    if proc.returncode != 0:
        sys.exit(f"error: MathJax の実行に失敗しました:\n{proc.stderr}")
    svgs = json.loads(proc.stdout)

    imgs = {}
    for (token, tex, display), svg in zip(items, svgs):
        if "data-mjx-error" in svg:
            sys.exit(f"error: LaTeX の構文エラー: ${tex}$")
        m = SVG_ATTR_RE.search(svg)
        if not m:
            sys.exit(f"error: MathJax 出力の寸法を解析できません: ${tex}$")
        # MathJax の ex は自フォント基準（1ex = 0.5em）。本文フォントの x-height に
        # 依存しないよう em に換算して <img> に付ける（縦横比は viewBox が保持）
        va, w, h = (float(v) * 0.5 for v in m.groups())
        uri = "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()
        if display:
            style = f"width:{w:.3f}em; max-width:100%;"
            cls = "math math-display"
        else:
            style = f"height:{h:.3f}em; vertical-align:{va:.3f}em;"
            cls = "math"
        imgs[token] = f'<img class="{cls}" style="{style}" src="{uri}" alt="{_esc(tex)}">'
    return imgs


def _esc(s):
    return s.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")
# --------------------------------------------------------------------------

# ---------------------- チャート式風の例題ブロック ----------------------
# 数学・統計系教科書の演習問題用。行頭マーカーで書く:
#   :::基本例題 12 Fisher情報行列の計算 ★★★   ← 例題/基本例題/重要例題/演習例題、★=難易度(1〜5)
#   （問題文）
#   :::指針
#   :::解答
#   :::別解 / :::検討   （任意）
#   :::練習              （例題と同番号の類題）
#   :::                  ← ブロック終了
REIDAI_OPEN_RE = re.compile(
    r"^:::(例題|基本例題|重要例題|演習例題)\s+(\S+)\s*(.*?)\s*(★+)?\s*$"
)
REIDAI_SEC_RE = re.compile(r"^:::(指針|解答|別解|検討|練習)\s*$")
REIDAI_CLOSE_RE = re.compile(r"^:::\s*$")
SEC_CLASSES = {"指針": "shishin", "解答": "kaito", "別解": "bekkai",
               "検討": "kento", "練習": "renshu"}


def expand_chart_blocks(text, fname):
    """::: マーカーを構造化HTMLに展開する（内部Markdownは md_in_html が処理）。"""
    out, in_fence = [], False
    num, open_divs = None, 0  # open_divs: 現在開いている閉じ待ち<div>数

    for ln, line in enumerate(text.split("\n"), 1):
        if line.startswith("```"):
            in_fence = not in_fence
        if in_fence or not line.startswith(":::"):
            out.append(line)
            continue
        where = f"{fname}:{ln}"
        if m := REIDAI_OPEN_RE.match(line):
            if open_divs:
                sys.exit(f"error: {where}: 前の例題ブロックが ::: で閉じられていません")
            kind, num, title, stars = m.groups()
            star_html = (
                f'<span class="stars">{"★" * len(stars)}{"☆" * (5 - len(stars))}</span>'
                if stars else ""
            )
            # md_in_html は祖先にも markdown 属性がないと子孫を処理しないため外枠にも付ける
            out += [
                '<div class="reidai" markdown="block">',
                f'<div class="reidai-head">{star_html}'
                f'<span class="kind">{kind} {_esc(num)}</span>{_esc(title)}</div>',
                '<div class="reidai-problem" markdown="block">',
            ]
            open_divs = 2
        elif m := REIDAI_SEC_RE.match(line):
            if not open_divs:
                sys.exit(f"error: {where}: :::{m.group(1)} が例題ブロックの外にあります")
            sec = m.group(1)
            label = f"練習 {num}" if sec == "練習" else sec
            # md_in_html は深い入れ子の markdown 属性を処理しないため、
            # セクションは外枠直下の1段ネストに保ち、ラベルはCSSの ::before で描く
            out += [
                "</div>",  # 直前の problem / sec を閉じる
                f'<div class="reidai-sec sec-{SEC_CLASSES[sec]}" '
                f'data-label="{_esc(label)}" markdown="block">',
            ]
            open_divs = 2
        elif REIDAI_CLOSE_RE.match(line):
            if not open_divs:
                sys.exit(f"error: {where}: 対応する例題のない ::: があります")
            out += ["</div>"] * open_divs
            open_divs = 0
        else:
            sys.exit(f"error: {where}: 不明なマーカーです: {line}")
    if open_divs:
        sys.exit(f"error: {fname}: 例題ブロックが ::: で閉じられないままEOFに達しました")
    return "\n".join(out)
# --------------------------------------------------------------------------


def build():
    files = sorted(glob.glob(os.path.join(SRC, "*.md")))
    if not files:
        sys.exit("error: src/*.md が見つかりません")
    print("sources:", [os.path.basename(f) for f in files])
    bodies, toc_items, math_items = [], [], []
    for f in files:
        md = markdown.Markdown(
            extensions=["tables", "fenced_code", "codehilite", "toc", "sane_lists",
                        "md_in_html"],
            extension_configs={
                "codehilite": {"guess_lang": False},
                "toc": {"toc_depth": 2},
            },
        )
        with open(f, encoding="utf-8") as fh:
            text = fh.read()
        for src, dst in REPLACEMENTS.items():
            text = text.replace(src, dst)
        text = expand_chart_blocks(text, os.path.basename(f))
        text, found = extract_math(text, len(math_items))
        math_items.extend(found)
        fatal = sorted(set(EMOJI_FATAL_RE.findall(text)))
        if fatal:
            sys.exit(
                f"error: {os.path.basename(f)} にフォント未収録の文字が残っています: {fatal}\n"
                "REPLACEMENTS に置換ルールを追加するか、本文から削除してください。"
            )
        warn = sorted(set(EMOJI_WARN_RE.findall(text)) - set("★☆"))  # ★☆は収録確認済み
        if warn:
            print(f"warning: {os.path.basename(f)} に記号 {warn} — "
                  "verify() が失敗したら置換してください")
        bodies.append(md.convert(text))
        # md.toc は <div class="toc"> で包まれており、外側の .toc と
        # page-break-after が重複するため中身だけ取り出す
        inner = md.toc.strip()
        inner = inner.removeprefix('<div class="toc">').removesuffix("</div>")
        toc_items.append(inner)

    math_imgs = render_math(math_items)
    if math_imgs:
        print(f"math: {len(math_imgs)} formulas rendered")
        token_re = re.compile("|".join(t for t, _, _ in math_items))
        bodies = [token_re.sub(lambda m: math_imgs[m.group(0)], b) for b in bodies]

    cover = (
        '<div class="cover">'
        f"<h1>{TITLE}</h1>"
        f'<div class="sub">{"<br>".join(COVER_SUB)}</div>'
        f'<div class="meta">{COVER_META}</div>'
        "</div>"
    )
    toc_html = '<div class="toc"><h1>目次</h1>' + "".join(toc_items) + "</div>"
    doc = (
        "<html><head><meta charset='utf-8'></head><body>"
        + cover + toc_html + "".join(bodies) + "</body></html>"
    )
    weasyprint.HTML(string=doc, base_url=BASE).write_pdf(
        OUT, stylesheets=[weasyprint.CSS(string=STYLE, base_url=BASE)]
    )
    print("wrote:", OUT)


def verify():
    """テキスト層が壊れていないことを確認する（絵文字罠の検出網）。"""
    from pypdf import PdfReader

    reader = PdfReader(OUT)
    bad = []
    for i, page in enumerate(reader.pages):
        fonts = (page.get("/Resources") or {}).get("/Font") or {}
        for name, ref in fonts.items():
            font = ref.get_object()
            enc = font.get("/Encoding")
            enc_name = getattr(enc, "get_object", lambda: enc)()
            if enc_name is not None and str(enc_name) != "/Identity-H":
                bad.append((i + 1, str(name), str(enc_name)))
    if bad:
        sys.exit(
            f"error: Identity-H でないフォントエンコーディングを検出: {bad[:5]}\n"
            "本文にフォント未収録の文字が混入しています（テキスト抽出が壊れます）。"
        )
    text = "".join(p.extract_text() or "" for p in reader.pages)
    # TITLE は表紙の2行組のために <br> を含んでよいので、分割して検査する
    for seg in re.split(r"<br\s*/?>", TITLE):
        if seg.strip() and seg.strip() not in text:
            sys.exit(f"error: 抽出テキストに書名の一部「{seg.strip()}」が見つかりません。")
    if re.search(r"MJXTOKEN\d+X", text):
        sys.exit("error: 未置換の数式トークンが残っています。")
    print(f"verify ok: {len(reader.pages)} pages, encoding=Identity-H, text layer intact")


if __name__ == "__main__":
    build()
    verify()
