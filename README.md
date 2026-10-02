# textbook — 日本語教科書ドキュメント作成スキル

Claude Code 用のスキル（Codex CLI・Grok などの他エージェントでも利用可。後述）。日本語の教科書的ドキュメントを Markdown ソース + WeasyPrint 製 PDF として新規作成・増補する。LaTeX 数式（MathJax → SVG）と、数研出版チャート式に倣った例題ブロック（例題／指針／解答／検討／練習）に対応。

「〜の教科書を作って」「〜を体系的に学べる資料を作って」「〜の教科書に章を追加して」といったリクエストで発動する。

## リポジトリ構成

| ファイル | 内容 |
|---|---|
| [SKILL.md](SKILL.md) | スキル本体。ワークフロー・執筆規約・演習問題の書式・ビルド環境・トラブルシュートを定義 |
| [AGENTS.md](AGENTS.md) | Codex など AGENTS.md を読むエージェント向けの入口。SKILL.md への案内 |
| [templates/build_pdf.py](templates/build_pdf.py) | ビルドスクリプトの雛形。教科書ごとに冒頭の設定ブロック（TITLE / HEADER / OUT_NAME / 表紙）だけ書き換えて使う |

## インストール

```bash
git clone <このリポジトリ> ~/.claude/skills/textbook
```

ユーザーレベルのスキルとして `~/.claude/skills/textbook/` に置くと、Claude Code が自動で認識する。

### Codex CLI・Grok など他のエージェントで使う

SKILL.md は特定のエージェントに依存しない手順書で、ビルドも通常のシェルコマンドだけで完結する。

| エージェント | 使い方 |
|---|---|
| Claude Code | `~/.claude/skills/textbook/` に置くと自動認識 |
| Codex CLI | リポジトリを任意の場所に clone し、プロジェクトの `AGENTS.md` から本リポジトリの `AGENTS.md` / `SKILL.md` を参照させる（または `~/.codex/` 配下に置いて指示する） |
| Grok その他 | 「`<パス>/SKILL.md` に従って〜の教科書を作って」と指示して読ませる |

自動発動（フロントマターの description によるトリガー）は Claude Code の機能のため、他のエージェントでは明示的に SKILL.md を指定する。

## 文章推敲に yomiyasu を使用（任意）

読みやすさを上げるため、地の文の推敲に [nanaism/yomiyasu](https://github.com/nanaism/yomiyasu)（MIT License）を使うことができる。導入は `npx skills add nanaism/yomiyasu`。数式・コード・表・`:::` ブロック・見出し構造は対象外で、衝突する方針は本スキルの規約を優先する（詳細は SKILL.md の「文章推敲」）。yomiyasu を使って作った教科書は、その README の「特徴」に使用した旨を記載する。本スキル自体は yomiyasu を同梱しておらず、未導入でも動作する。

## 生成される教科書の構成

スキルは 1 冊ごとに次の形のリポジトリを作る。

```
<slug>-textbook/
├── src/
│   ├── 01_入門編.md      ← 編ごとに1ファイル（ゼロ埋め連番 = 掲載順）
│   ├── 02_実践編.md
│   └── ...
├── build_pdf.py          ← templates/build_pdf.py のコピー（設定ブロックのみ変更）
├── README.md             ← 構成表・特徴つき
└── <書名>.pdf            ← コミット物として直下に置く
```

`python3 build_pdf.py` で表紙・目次つきの A4 PDF を生成し、pypdf によるテキスト層検証（`verify ok`）まで一体で行う。

## 主な機能・設計判断

- **LaTeX 数式**: `$...$` / `$$...$$` をビルド時に MathJax（node）で SVG 化して組版する。ams 環境（`aligned` / `pmatrix` / `cases` 等）も使用可。MathJax は初回ビルド時に `~/.cache/textbook-mathjax` へ自動インストールされる。
- **チャート式例題ブロック**: `:::基本例題 ... :::指針 ... :::解答 ...` のマーカーを、青い帯のヘッダを持つ例題枠として組版する。数学・統計系の教科書向け。
- **テキスト層の健全性**: Noto Sans CJK JP にない文字（絵文字など）が 1 文字でも混ざると WeasyPrint が Identity-H でない CMap を吐き、PDF 全体のテキスト抽出が壊れる。ビルドスクリプトに置換・検査を組み込み、検証を通るまで完了としない。
- **シリーズ一貫性**: 既存の `*-textbook` シリーズと同じ章番号の通し方・文体（です・ます調）・見出し構造・README 規約を強制し、増補時も違和感なく混ざるようにしている。

## 依存環境

- Python: `markdown`, `weasyprint`, `pypdf`（目視確認用に PyMuPDF も推奨）
- Node.js（数式の SVG 化に使用）
- フォント: Noto Sans CJK JP（`~/.local/share/fonts` に配置し fontconfig 経由で参照）
