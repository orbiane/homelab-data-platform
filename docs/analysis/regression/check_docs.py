"""回帰の試験の文書の層（R1）。廃止した指標の名前が、今を説明する文書に残っていないかを見る。

1. git の履歴から、dbt_project の下の _metrics.yml にあったことのある指標の名前を集める
2. 今の manifest（dbt_project/target/semantic_manifest.json）に無い名前を「廃止した名前」とする
3. 今を説明する文書（下の DOCS）に、廃止した名前が単語として出てくる行を外れとする。
   ただし同じ行に、その名前を廃止したコミットが指した決定メモのパス（docs/business/...md）がある行は、
   履歴の記述として外れに数えない（一覧には出す）

使い方（リポジトリの直下で）：uv run python docs/analysis/regression/check_docs.py [--out 結果のファイル]
終了コード：0 外れ 0 件／1 外れが1件以上
"""
import argparse
import json
import pathlib
import re
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[3]
MANIFEST = REPO / "dbt_project" / "target" / "semantic_manifest.json"
METRICS_GLOB = ":(glob)dbt_project/**/_metrics.yml"
# 今を説明する文書。(パス, 節の見出し or None)。節を指したときは、その見出しから次の同じ深さ以上の見出しの前まで
DOCS = [
    ("README.md", None),
    ("CLAUDE.md", None),
    ("agent/sl_mcp/README.md", None),
    ("docs/decisions/ADR-006-generated-data-version.md", "## 基準値"),
]
NAME_LINE = re.compile(r"^  - name:\s*(\S+)\s*$", re.M)  # metrics: の直下の要素だけ（字下げ2）
MEMO = re.compile(r"docs/business/[\w.\-]+\.md")


def git(*args):
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, check=True).stdout


def history():
    """古い順に (コミット, {パス: 名前の集合}) を返す。"""
    shas = git("log", "--all", "--reverse", "--format=%H", "--", METRICS_GLOB).split()
    out = []
    for sha in shas:
        paths = git("ls-tree", "-r", "--name-only", sha, "--", "dbt_project").split()
        names = {}
        for p in paths:
            if p.endswith("/_metrics.yml"):
                names[p] = set(NAME_LINE.findall(git("show", f"{sha}:{p}")))
        out.append((sha, names))
    return out


def removal_memos(hist, name):
    """name が消えたコミットごとに、そのコミットの _metrics.yml の差分とメッセージにある決定メモのパスを集める。"""
    memos, prev = set(), False
    for sha, names in hist:
        now = any(name in s for s in names.values())
        if prev and not now:
            text = git("show", "--format=%B", sha, "--", METRICS_GLOB)
            memos |= set(MEMO.findall(text))
        prev = now
    return memos


def doc_lines(path, section):
    lines = (REPO / path).read_text().splitlines()
    if section is None:
        return list(enumerate(lines, 1))
    depth = len(section) - len(section.lstrip("#"))
    out, inside = [], False
    for i, line in enumerate(lines, 1):
        if line.strip() == section:
            inside = True
        elif inside and re.match(r"^#{1,%d} " % depth, line):
            break
        if inside:
            out.append((i, line))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", help="結果を Markdown でこのファイルにも書く")
    args = ap.parse_args()

    hist = history()
    past = set().union(*(s for _, names in hist for s in names.values()))
    current = {m["name"] for m in json.loads(MANIFEST.read_text())["metrics"]}
    retired = sorted(past - current)
    memos = {n: removal_memos(hist, n) for n in retired}

    hits, excused, n_lines = [], [], 0
    for path, section in DOCS:
        lines = doc_lines(path, section)
        n_lines += len(lines)
        for i, line in lines:
            for n in retired:
                if re.search(r"(?<![A-Za-z0-9_])" + re.escape(n) + r"(?![A-Za-z0-9_])", line):
                    entry = f"{path}:{i}: `{n}` — {line.strip()}"
                    if any(m in line for m in memos[n]):
                        excused.append(entry)
                    else:
                        hits.append(entry)

    out = [
        f"- 履歴で見たコミット：{len(hist)} 件（{METRICS_GLOB}）",
        f"- 過去の名前（{len(past)}）：{', '.join(sorted(past))}",
        f"- 今の名前（manifest、{len(current)}）：{', '.join(sorted(current))}",
        f"- 廃止した名前（{len(retired)}）：" + ", ".join(f"{n}（廃止したコミットの決定メモ：{', '.join(sorted(memos[n])) or '無し'}）" for n in retired),
        f"- 調べた文書：{len(DOCS)} 本、{n_lines} 行（" + "、".join(p + (f" の「{s.lstrip('# ')}」の節" if s else "") for p, s in DOCS) + "）",
        f"- 外れ：{len(hits)} 件",
    ]
    out += [f"  - {h}" for h in hits]
    out.append(f"- 決定メモのパスが同じ行にあるので数えなかった行：{len(excused)} 件")
    out += [f"  - {e}" for e in excused]
    text = "\n".join(out)
    print(text)
    if args.out:
        with pathlib.Path(args.out).open("a") as f:
            f.write(text + "\n")
    sys.exit(1 if hits else 0)


if __name__ == "__main__":
    main()
