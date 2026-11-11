<!-- このファイルは公開リポジトリに入る。ユーザー名・IP・絶対パスを書かないこと。 -->
# agent/loop：自律ループの起動の台本（L0、ADR-008）

持ち主の機械で、毎時23分に Claude Code を人の見ていない形で起こし、`NEXT.md` の1件を進めて PR を出させる。手順の決まりは [docs/agent/loop.md](../../docs/agent/loop.md)。

## 何がどこにあるか

| もの | 場所 | 中身 |
|---|---|---|
| 起動の台本 | `agent/loop/run.py` | ロック、時間帯、1日の上限、作業場所の確かめ、ID の決定、`claude -p` の起動、記録 |
| 次の1件の決め方 | `agent/loop/pick.py` | `NEXT.md` の表と `gh pr list` から ID を決める。`selftest` 付き |
| 前置き | `agent/loop/prompt.md` | `claude -p` に渡す文。`<ID>` を置き換える |
| 権限の表 | `.claude/loop-settings.json` | ループだけに効く allow・deny・hook。ask は置かない |
| ループの関所 | `.claude/hooks/loop_guard.py` | push の行き先、gh のマージ、dbt の向きを止める |
| 試し | `agent/loop/tests/` | 権限の表の突き合わせ、関所の試しの表 |
| 据え付け | `agent/loop/install.py`、`agent/loop/launchd.plist.template` | 作業場所を作る、守りを写す、plist を書く |

機械の上（リポジトリの外）：

| もの | 場所 |
|---|---|
| ループ専用の作業場所（git worktree） | `~/homelab-loop/wt` |
| 守りの写し（launchd が起こすのはこちら） | `~/homelab-loop/bin`（`INSTALLED_FROM` に写した版） |
| 記録 | `~/homelab-loop/logs/` |
| LaunchAgent | `~/Library/LaunchAgents/com.homelab-data-platform.loop.plist` |

## 起動のしかた（run.py が組み立てるもの）

```
claude -p "<prompt.md>" \
  --setting-sources user \                       # プロジェクトの .claude/settings.json（ask を含む）を読まない
  --settings ~/homelab-loop/bin/.claude/loop-settings.json \
  --mcp-config ~/homelab-loop/wt/.mcp.json --strict-mcp-config \   # setting-sources から project を外すと .mcp.json も読まれないため
  --permission-mode dontAsk --permission-prompts none \
  --model claude-fable-5-2 --effort medium --max-turns 80 \   # 2026-11-10 から今週だけ（利用枠の都合。もとは claude-opus-5-5）
  --output-format stream-json --verbose
```

- 作業場所は `~/homelab-loop/wt`。起こす前に、消えていない変更があれば止まり、無ければ `origin/main` に戻す（detached）
- 時間切れは90分（SIGINT、だめなら SIGTERM）
- 環境変数 `HOMELAB_LOOP_ROOT`（守りの写しの場所）を渡す。ループの表の hook はこれで `loop_guard.py` を見つける。無いと hook が起動できず、`onFailure: block` で Bash はすべて止まる
- `~/.claude/settings.json`（ユーザーの設定）は読む。中の deny と env（`DBT_PROFILES_DIR`）もループに効く。ユーザーの設定に ask を足すと、ループではそれが断られる

## 据え付け方（持ち主が、ふだんの作業場所の根で）

1. `python3 agent/loop/tests/check_loop_settings.py` と `python3 agent/loop/tests/loop_guard_cases.py` と `python3 agent/loop/pick.py selftest` が通ることを見る
2. 作業場所：`python3 agent/loop/install.py worktree --dry-run` で中身を見てから、`--dry-run` を外して打つ
3. 守りの写し：`python3 agent/loop/install.py copy --ref origin/main`（L0 のマージ前の試しでは `--ref owner/L0-loop-setup`）
4. 試し：`python3 ~/homelab-loop/bin/agent/loop/run.py --dry-run` で、選ぶ ID と起こすコマンドを見る
5. plist：`python3 agent/loop/install.py plist`（書くだけ。読み込まない）
6. 読み込む（定時の起動が始まる）：`launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.homelab-data-platform.loop.plist`
7. 読み込まれたかを見る：`launchctl print gui/$(id -u)/com.homelab-data-platform.loop | head -20`

守り（`run.py`・`pick.py`・`prompt.md`・権限の表・ループの関所）を main で変えたら、3 をやり直す。やり直すまでは古い写しで動く（`runs.jsonl` の `guard_drift` に、main と違うファイルが出る）。

## 止め方

- 1回だけ止める：`~/homelab-loop/run.lock` を持っている `run.py` と、その子の `claude` を止める（`pkill -INT -f homelab-loop/bin/agent/loop/run.py` のあと `claude` の終了を待つ）
- 定時の起動を止める：`launchctl bootout gui/$(id -u)/com.homelab-data-platform.loop`
- 作業場所に変更を残すと、次の回は何もせずに止まる（`runs.jsonl` に `kind: stop`）。中身を見てから片づける

## 外し方

1. `launchctl bootout gui/$(id -u)/com.homelab-data-platform.loop`
2. `rm ~/Library/LaunchAgents/com.homelab-data-platform.loop.plist`
3. `git worktree remove ~/homelab-loop/wt`（変更が残っていれば、先に中身を見る）
4. `~/homelab-loop/bin` を消す。記録（`~/homelab-loop/logs`）は、要らなければ消す

## 記録

`~/homelab-loop/logs/` に残す（リポジトリには入れない）。

| ファイル | 中身 |
|---|---|
| `runs.jsonl` | 起動ごとの出来事。`kind` が `start`・`end`・`skip`・`stop`・`dry-run`。`end` に終了コード、`claude --version`、`total_cost_usd`、`duration_ms`、`num_turns`、`permission_denials` の件数、時間切れか、終わったあとの作業場所の汚れ |
| `daily.tsv` | 1日1行の要約（回数、ID、費用、分、0 でない終了の回数） |
| `YYYYMMDD/<時刻>-<ID>.jsonl` | `claude -p` の stream-json そのもの |
| `YYYYMMDD/<時刻>-<ID>.stderr.log` | `claude -p` の stderr |
| `launchd.out.log`・`launchd.err.log` | launchd から見た run.py の出力 |

## 知っている穴

- ADR-008 の K1〜K4 と同じ。特に、ループは `uv run python` を許されているので、スクリプトの中では権限の表も関所も効かない（K2）
- 守りの写しはリポジトリの外にあるが、ループのスクリプト（K2）からは書き換えられる。写しを見張るのは `guard_drift` の記録だけ
- 作業場所の symlink の先（ふだんの作業場所の warehouse・target・生成データ）は、ループの Edit・Write からは書けない（allow は symlink の先も作業場所の中にあるときだけ効く）。スクリプトからは書ける（K2）
