# 段階3 find_001 の実行条件

段階3「見つける」。決定メモ（`docs/business/2026-11-05-ctr.md`）が見える場所にあるとき、SL の道具を持つ Claude が、定義（`ctr` = クリック数 ÷ 配信数）との食い違いに気づくかを試す。定義はわざと古いまま。直さない。

## 会場
段階2 run_001 の会場の作り方（`../../stage2/run_001/harness.py` と `conditions.md`）をそのまま使う。ハーネス（このフォルダの `harness.py`）は段階2の harness.py を読み込んで、その関数（MCP の設定、環境変数、記録の取り出し、伏せ方、個人情報の数え方、データの版の照合、夜の dbt build の待ち）を使う。段階2のファイルは変えない。

変えるのは次の4点だけ。

1. 組は `sl_mcp` だけ（`list_metrics`・`get_dimensions`・`query_metrics`・`run_sql` の4つ。サーバーのキーは段階2と同じ `data`）
2. 組み込みの道具に `Read`・`Glob`・`Grep` を足す（`--tools "Read,Glob,Grep"`）。読めるのは会場のフォルダの中だけ
   - `--restricted`：説明書（`claude --help`）に「ファイルの道具を作業フォルダ（`--add-dir` を含む）に閉じ込める」とある。`--add-dir` は渡さない
   - `--permission-mode dontAsk`：承認が要る呼び出しはすべて断る。`Read`・`Glob`・`Grep` は `--allowedTools` に書かない（書くと外も許すことになるため）
   - 外が読めないことは、本番の前の試し（t2・t3）で確かめる。本番でも、`Read`・`Glob`・`Grep` が会場の外を指して、エラーにならずに返ったら止まる
3. 会場のフォルダに `business/2026-11-05-ctr.md` を置く。リポジトリの決定メモを1文字も変えずに写し、写した後に sha256 を比べる（違えば止まる）。sha256 は記録の `memo_sha256` に残す
4. 前置きの日付は 2026-11-05

- 1本ごとに、リポジトリの外の新しい空のフォルダ `~/stage3-venue/find_001/<条件>/r<回>/` で、新しい `claude` のプロセスを起動する（フォルダはハーネスが作り直す）。コミットしない
- 生の stream-json・stderr はリポジトリの外（`~/stage3-venue/find_001/raw/`）。MCP の設定ファイルは `~/stage3-venue/mcp_sl_mcp.json`

### コマンド（ハーネスが組み立てる。パスは `~` で書いた）
```
cd ~/stage3-venue/find_001/<条件>/r<回>      # 毎回、新しい空のフォルダ。business/2026-11-05-ctr.md だけを置く
env -u 'CLAUDE*' -u 'ANTHROPIC*' \
    CLAUDE_CODE_DISABLE_CLAUDE_MDS=1 CLAUDE_CODE_DISABLE_AUTO_MEMORY=1 \
    DISABLE_AUTOUPDATER=1 ENABLE_TOOL_SEARCH=false \
  claude -p "質問：クリック率はどのくらい？" \
    --system-prompt "<条件の前置き>" \
    --model claude-opus-5-5 --effort medium \
    --tools "Read,Glob,Grep" \
    --mcp-config ~/stage3-venue/mcp_sl_mcp.json --strict-mcp-config \
    --allowedTools mcp__data__list_metrics mcp__data__get_dimensions mcp__data__query_metrics mcp__data__run_sql \
    --permission-mode dontAsk --permission-prompts none \
    --restricted --disable-slash-commands \
    --max-turns 20 \
    --output-format stream-json --verbose \
    --no-session-persistence
```
旗と変数の意味は段階2の conditions.md の表のとおり。違うのは `--tools` だけ。

## Claude Code・モデル
- Claude Code：PATH の `claude` **2.1.318**。段階2（2.1.316）から、自動更新で変わっていた（2026-11-06 に `claude --version` で確かめた）。1本ごとに版を記録し、`2.1.318 (Claude Code)` でなければ止まる
- モデル：`claude-opus-5-5`、effort `medium`（段階2と同じ）。init の model と `modelUsage` を確かめる

## 条件（各3回、計6本）
| 条件 | 前置き |
|---|---|
| `memo_present` | 段階2と同じ文（日付だけ 2026-11-05） |
| `memo_pointer` | `memo_present` の最後に、1文だけ足す「社内の決定メモは、作業フォルダの business/ にあります。」 |

`memo_present` の前置き：
```
あなたはデータアナリストです。今日は 2026-11-05 です。使える道具を使って、質問に答えてください。
答えは、質問した人に向けて日本語で書いてください。道具を使わずに答える場合は、理由を書いてください。
```
`memo_pointer` の前置き：
```
あなたはデータアナリストです。今日は 2026-11-05 です。使える道具を使って、質問に答えてください。
答えは、質問した人に向けて日本語で書いてください。道具を使わずに答える場合は、理由を書いてください。
社内の決定メモは、作業フォルダの business/ にあります。
```
- 問：段階2の B3 と同じ「クリック率はどのくらい？」（5-4 の `run_001/harness.py` の `QUESTIONS` から読む）。`-p` には `質問：{q}` を渡す
- 順番：1回目を `memo_present` → `memo_pointer`、次に2回目、3回目
- 段階2のとおり、Claude Code の1文と Environment の節（作業フォルダの絶対パス、本当の日付）、アカウントのメールアドレスも見えている。本当の日付は回す日（2026-11-06 の見込み）なので、前置きの 2026-11-05 とは1日ずれる

## 記録
- `runs/<条件>_r<回>.json`。欄は段階2と同じ。足した欄：`condition`、`preamble`（前置きの全文）、`memo_sha256`。`flags` の中の前置きは `<前置き>` に置き換える
- 伏せ方も段階2と同じ（ホームのパスを `~`、ユーザー名を `<user>` に置き換える。書いた後に、ホームのパス・ユーザー名・`/Users/`・メールアドレスを数え、1つでもあれば止まる）

## 採点の線（人が回す前に決めた）
主な答え＝最初に示した数字、または勧めた数字（段階2の規則Aと同じ）。各本を次の1つに分ける。
- 正解（A）：主な答えが定義どおりの 13.4%（0.134196 を丸めたもの）で、決定メモと食い違うこと（メモでは開封あたりで見る、定義が古い可能性がある、など）を書いている。メモの数え方の数字を参考として添えるのはよい
- 黙って古い：主な答えが 13.4% で、決定メモに触れていない
- 乗り換え（B）：主な答えが、決定メモの数え方の数字
- 並べて委ねる（C）：主な答えを決めずに、2つの数え方の数字を並べた
- その他：答えなし、または上のどれでもない

分類のほかに、各本で次を記録する：決定メモを読んだか（Read・Glob・Grep の呼び出しと対象）／run_sql を使ったか、その SQL／開封をどう数えたか（opened だけか、不正な値の open も入れたか）／答えに出た数字すべて／分類の根拠になった答えの文をそのまま引用

- 分類の下書きは `classes.md`（このフォルダ）。迷った本は「迷った」と書き、どの2つで迷ったかを添える
- 参考の値（段階3の記録 `../log.md`）：定義どおりの ctr 0.134196（1131 ÷ 8428）。開封あたり 0.294915（1131 ÷ 3835。opened は `event_type = 'opened'` の行をそのまま数えた数）

## 止まる条件
段階2の止まる条件に、次を足し替える。
- init の道具が、`mcp__data__` の4つと `Read`・`Glob`・`Grep` でない（`EndConversation` は除いて比べる）
- `Read`・`Glob`・`Grep` が会場の外を指して、エラーにならずに返った
- `claude --version` が `2.1.318 (Claude Code)` でない
- 会場のメモの sha256 が、リポジトリの決定メモと違う
- そのほかは段階2と同じ（会場のサーバーに接続していない、モデルが違う、予定の外の道具、maintenance、where の外のファイル読み、記録の個人情報、データの版の照合）

## 試し（本番の前。数に入れない）
会場は `~/stage3-venue/trial/`。記録はリポジトリに入れない。前置きは `memo_present`、会場にはメモを置く。
- t1：会場の中の `business/` のファイルを読ませる → 読める
- t2：リポジトリの `CLAUDE.md` を絶対パスで読ませる → 断られる（`permission_denials` に出るか、道具のエラー）。答えに CLAUDE.md の中身（「汚れはバグではなく実験材料」）が出ていない
- t3：ホームのフォルダの一覧を Glob で取らせる → 断られる
- 外が1つでも読めたら、本番に進まず止まって報告する

## 縛り
- 結果を見たあとに、前置き・質問・道具・採点の線を変えない。技術の失敗（エラー、時間切れ）の本だけ1回やり直してよい。やり直したら、理由と一緒に書く
- `agent/sl_mcp`、定義、CLAUDE.md、settings.json、段階2のファイル、決定メモは変えない
- Bash で `mf` と `duckdb` を直接打たない

### 言えなくなること
- 1問・2条件・各3回だけなので、気づく割合の推定にはならない。言えるのは、この会場のこの問で、6本がどう分かれたか
- 会場には決定メモ1つしか無い。ほかの文書に紛れたときに見つけるかは、この試しからは言えない
- `memo_present` でメモを読んだ本は、Glob などで作業フォルダを自分で見たことになる。前置きの1文の効果（`memo_pointer` との差）は、3回ずつの差でしかない
