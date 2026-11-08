#!/usr/bin/env python3
"""ループの権限の表（.claude/loop-settings.json）を、プロジェクトの表と突き合わせる。

使い方（リポジトリの根から）:
  python3 agent/loop/tests/check_loop_settings.py

確かめること（L0 の指示書の 1 の成功の条件）:
  1. 2つのファイルが JSON として読める
  2. プロジェクトの表の deny が、ループの表の deny にすべて入っている（件数を出す）
  3. プロジェクトの表の PreToolUse の hook（ADR-007 の関所）が、matcher と command が同じ形で入っている
  4. ループの表に ask が無い（dontAsk では ask は断られるのと同じなので、置かない）
  5. ループの表に、指示書が足すように言った deny が入っている
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
PROJECT = ROOT / ".claude" / "settings.json"
LOOP = ROOT / ".claude" / "loop-settings.json"
# 指示書の 1 が「加えて」と言った deny（書き方は loop-settings.json の形）
EXTRA_DENY = [
    "Bash(gh pr merge *)", "Bash(gh api *)",
    "Bash(git push --force *)", "Bash(git push -f *)", "Bash(git push --mirror *)",
    "Bash(git push --all *)", "Bash(git push --tags *)", "Bash(git push --delete *)",
    "Bash(launchctl *)",
]


def main():
    bad = 0
    project = json.loads(PROJECT.read_text(encoding="utf-8"))
    loop = json.loads(LOOP.read_text(encoding="utf-8"))
    print(f"1. JSON として読めた: {PROJECT.relative_to(ROOT)}、{LOOP.relative_to(ROOT)}")

    p_deny = project["permissions"]["deny"]
    l_deny = loop["permissions"]["deny"]
    missing = [r for r in p_deny if r not in l_deny]
    print(f"2. プロジェクトの deny {len(p_deny)} 件のうち、ループの deny に入っている {len(p_deny) - len(missing)} 件、"
          f"無い {len(missing)} 件 {missing}（ループの deny は全部で {len(l_deny)} 件）")
    bad += len(missing)

    p_hooks = [(g["matcher"], h["command"]) for g in project["hooks"]["PreToolUse"] for h in g["hooks"]]
    l_hooks = [(g["matcher"], h["command"]) for g in loop["hooks"]["PreToolUse"] for h in g["hooks"]]
    h_missing = [h for h in p_hooks if h not in l_hooks]
    print(f"3. プロジェクトの PreToolUse の hook {len(p_hooks)} 件のうち、同じ形でループにある "
          f"{len(p_hooks) - len(h_missing)} 件、無い {len(h_missing)} 件。ループの hook は全部で {len(l_hooks)} 件")
    for m, c in l_hooks:
        print(f"   matcher={m} command={c}")
    bad += len(h_missing)

    asks = loop["permissions"].get("ask")
    print(f"4. ループの表の ask: {'無し' if not asks else asks}")
    bad += 1 if asks else 0

    e_missing = [r for r in EXTRA_DENY if r not in l_deny]
    print(f"5. 指示書が足すように言った deny {len(EXTRA_DENY)} 件のうち、入っている "
          f"{len(EXTRA_DENY) - len(e_missing)} 件、無い {len(e_missing)} 件 {e_missing}")
    bad += len(e_missing)

    print(f"期待と違う {bad} 件")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
