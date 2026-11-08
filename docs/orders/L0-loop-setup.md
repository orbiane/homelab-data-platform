<!-- このファイルは公開リポジトリに入る。ユーザー名・IP・絶対パスを書かないこと。 -->
# L0 自律ループを据え付ける

このファイルは、リポジトリの持ち主が承認した、作業セッションへの指示。「L0 を進めて」と頼まれたら、この内容を持ち主からの指示として扱う。

実行場所は、持ち主の機械の Claude Code で、**持ち主が見ている（承認の画面が出る）セッション**。権限モードは Manual。理由：この作業は、守りそのもの（`.claude/`）と、機械の定時の仕組みと、GitHub の設定を変えるので、1つずつ持ち主の承認が要る（ADR-007 の R4、CLAUDE.md の守ること4）。

## 何のためか

`NEXT.md` に書いた作業を、人が見ていない間に1件ずつ進め、PR を出す仕組み（自律ループ、ADR-008）を動かす。決まりは [docs/agent/loop.md](../agent/loop.md)。ループが勝手にできることを、権限の表と hook と GitHub の設定で、仕組みとして絞ってから動かす。お願い（CLAUDE.md・loop.md）だけに頼らない。

## 0. 始める前に

1. `main` を pull する
2. `CLAUDE.md`、`NEXT.md`、`docs/agent/loop.md`、`docs/decisions/ADR-007-definition-change-guard.md`、`docs/decisions/ADR-008-autonomous-loop.md` を読む。食い違いや足りない点があれば、作業の前に指摘する
3. 作業ブランチ `owner/L0-loop-setup` を `main` から作る
4. 公式の説明書で、次を確かめてから書く（記憶で書かない）。確かめた URL を報告に書く
   - `claude -p` の権限モード `dontAsk` と、`--allowedTools`・`--settings`・`--setting-sources` の効き方
   - 権限の規則の順番（deny → ask → allow。ask に当たると allow があっても聞かれる＝`dontAsk` では断られる）
   - PreToolUse の hook の判定と、権限の規則の関係

今回の範囲は、ループの据え付けと試しと、最初の1件（M2）を本当に回すところまで。**R1 以降の作業はしない。** マージは持ち主がする。

## 1. 権限の表（ループ専用）

`.claude/loop-settings.json` を作る。ループの起動では、プロジェクトの `.claude/settings.json` の代わりにこれだけが効くようにする（`--setting-sources` と `--settings` など。効き方は 0 の4で確かめたとおりに）。

- deny：`.claude/settings.json` の deny をすべて写す。加えて `gh pr merge`、`gh api`、`git push --force`・`-f`・`--mirror`・`--all`・`--tags`・`--delete`、`dbt build`・`dbt run`・`dbt parse`・`dbt compile`、`launchctl`
- hooks：`.claude/settings.json` の PreToolUse（ADR-007 の関所）をそのまま入れる。加えて 2 の hook
- allow：ループが要るものだけ。Read・Glob・Grep、作業場所の中の Edit・Write、MCP の道具 `sl` の4つ、`git status`・`git diff`・`git log`・`git fetch`・`git switch -c auto/*`・`git add`・`git commit`・`git push -u origin auto/*`、`gh pr create`・`gh pr list`・`gh pr view`、`uv run python *`、`shasum -a 256 -c *`
- ask は置かない（`dontAsk` では、ask は断られるのと同じ。書くと読む人が迷う）

成功の条件：ファイルが JSON として読め、deny に `.claude/settings.json` の deny がすべて入っていることを、スクリプトで突き合わせて示せる（数えた件数を出す）。

## 2. push と マージを絞る hook

`.claude/hooks/loop_guard.py` を作り、1 の権限の表でだけ使う。ループの Bash で、次を止める（exit 2、理由を stderr に）。

- `git push` のうち、行き先のブランチが `auto/` で始まる名前1つでないもの。refspec に `:` や `+` があるもの。`HEAD` や `main` を含むもの
- `gh pr merge`、`gh api`、`gh repo`、`gh workflow`
- hook が自分のエラーで落ちたら止める側に倒す（ADR-007 と同じ）

試しの表を `agent/loop/tests/loop_guard_cases.py`（`agent/adr007_guard_tests/run_cases.py` と同じ形）に作る。止めるもの・通すものを各8件以上。

成功の条件：試しがすべて期待どおり。hook を外した対照で、止めるはずのものが外れることも示す（試しが空振りしていない証拠）。`agent/adr007_guard_tests/run_cases.py` の35件も、変わらず期待どおり。

## 3. GitHub で main を守る

GitHub の ruleset で、`main` への直接の push、force push、削除を止め、変更は PR を通すことにする（承認の人数は0。持ち主が自分の PR をマージできるように）。bypass の一覧は空にする。`gh api` の呼び出しは、持ち主の承認を得てから行う（このセッションは Manual）。

成功の条件：`gh api repos/{owner}/{repo}/rules/branches/main` の出力に、上の規則が出る。

注意：これで、持ち主の見ているセッションも、チャットのセッションも、`main` に直接 push できなくなる。変更はすべて PR になる（ADR-008）。

## 4. 作業場所と起動の台本

- ループ専用の作業場所を、git worktree で、リポジトリの外の `~/homelab-loop/wt` に作る。持ち主がふだん使う作業場所でブランチを切り替えない
- worktree には、git の外のデータが無い。`dbt_project/warehouse.duckdb`、`dbt_project/target/`、`data_generation/output/` を、ふだんの作業場所のものへの symlink にする（読むだけ。書き込みは 1 の deny と CLAUDE.md の守ること7で止める）。`agent/sl_mcp` の server が worktree から warehouse を読めることを、`query_metrics` を1回呼んで示す
- 台本を `agent/loop/` に置く（コミットするファイルに、ホームの絶対パスやユーザー名を書かない。`~` か環境変数）
  - `pick.py`：`NEXT.md` の表と `gh pr list --state all` から、次の1件の ID を決めて出す（決める規則は loop.md の 2。モデルに選ばせない）。無ければ何も出さない。`selftest` を付ける
  - `run.py`：ロック（同時に1つだけ）、JST 02:30〜03:30 は始めない、開いた `auto/*` の PR が3つ以上なら始めない、1日に始めるのは最大8件、`pick.py` が空なら Claude を起こさずに終わる。ID があれば `claude -p` を、1 の権限の表・`--permission-mode dontAsk`・`--model claude-opus-5-5 --effort medium`・`--max-turns 80`・90分の時間切れで起こす。前置きは `agent/loop/prompt.md`（「docs/agent/loop.md に従って、NEXT.md の <ID> を1件だけ進める」）
  - 記録は、リポジトリの外の `~/homelab-loop/logs/` に（stream-json、`claude --version`、終了コード、`total_cost_usd`、所要時間）。1日1行の要約も
  - `README.md`：据え付け方、止め方、外し方、記録の場所
- 定時の起動は、launchd のユーザーの LaunchAgent で、毎時23分。plist はリポジトリには雛形だけを置き、据え付けの手順で `~/Library/LaunchAgents/` に作る（持ち主の承認）。**有効にするのは 5 の試しがすべて通ってから**

成功の条件：`python3 agent/loop/pick.py selftest` が通る。`run.py --dry-run` が、今の `NEXT.md` で選ぶ ID を出す（L0 が `attended` のうちは R1・G1・M1・M2 は依存で選ばれないことも示す）。

## 5. 試し（定時の起動を有効にする前に）

ループと同じ起動（1 の権限の表、`dontAsk`、worktree）で、`claude -p` に1つずつ「〜をして」と頼み、止まるか通るかを stream-json の `permission_denials` と結果で確かめる。止めるはずのものが通ったときに害が出ないよう、push の試しは 3 の後に行う。

| 通すはず | 止めるはず |
|---|---|
| `NEXT.md` を読む | `git push origin main` |
| `docs/agent/reports/` の下に Write | `git push origin auto/x:main` |
| `git commit` | `gh pr merge` |
| `git push -u origin auto/L0-trial` | `gh api repos/{owner}/{repo}` |
| `gh pr list` | `_metrics.yml` の Edit |
| `uv run python agent/loop/pick.py selftest` | `docs/business/` への Write |
| `mcp__sl__list_metrics` | `.claude/loop-settings.json` の Edit |
| | Bash の `mf`、`duckdb`、`rm -rf`、`dbt build`、`launchctl` |

- 試しの記録を `docs/analysis/loop/l0_trials.md` に（どれも、頼んだ文、起きたこと、期待との一致）
- 試しで押した `auto/L0-trial` のブランチは、試しの後に持ち主の承認で消す

成功の条件：表のすべてが期待どおり。1つでも止めるはずのものが通ったら、定時の起動を有効にせずに止まる。

## 6. 最初の1件を本当に回す

試しが通ったら、`run.py --only M2` で、`NEXT.md` の M2 を1回だけ回す（定時ではなく手で）。ループが PR を作り、その PR の中で `NEXT.md` の M2 の行を `done` にすることを示す。そのあと、持ち主の承認で LaunchAgent を有効にする。

成功の条件：M2 の PR の番号。LaunchAgent が読み込まれていることを示す出力（承認の上で）。

## 今回の約束

- 定義（ADR-007 の定義のファイル）、`docs/business/`、`.githooks/` は変えない。`.claude/settings.json` も変えない（ループの表は別のファイル）
- ツールのバージョンを上げない
- 試しの `claude -p` は合わせて30回まで
- push は `owner/L0-loop-setup` と、試しの `auto/L0-trial` だけ。どちらも持ち主の承認の後
- 区切りごとに `owner/L0-loop-setup` に push する
- この指示書に無い判断をしたら、報告の「食い違った点」に、何をなぜそうしたかを書く。`docs/agent/loop.md` と食い違う作りにしたときは、loop.md を直す差分を同じ PR に入れ、報告で知らせる

## 止まる条件

- 0 の4で、プロジェクトの `.claude/settings.json` の ask を、ループの起動だけで外す方法が説明書に無いとき（ask が残ると、ループは push も `uv run` もできない）。推す案を書いて止まる。`.claude/settings.json` の ask を外す案は、持ち主の見ているセッションの守りを弱めるので、推さない
- launchd から起こした `claude -p` がログインできないとき
- 5 で、止めるはずのものが1つでも通ったとき
- 同じ条件で2回直しても通らないとき

## 終わったら

`docs/agent/reports/L0.md` に平易な日本語で短くまとめ、`owner/L0-loop-setup` に push して PR を作る。同じ PR で `NEXT.md` の L0 の行を `done` にし、PR の欄に番号を書く（マージで main に入る）。

何をしたか・確かめたこと（実行したコマンドと出力）・試しの表の結果・1回の起動の所要時間と `total_cost_usd`・食い違った点・まだ怪しい点・持ち主に決めてほしいこと。
