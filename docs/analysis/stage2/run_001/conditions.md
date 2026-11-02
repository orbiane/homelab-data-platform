# 段階2 run_001 の実行条件

5-4（段階1）と同じ13問を、Claude Code（`claude -p`）に、MCP の道具だけで解かせる。SL の集計の道具がある組と無い組を、同じモデルで比べる。条件は 2026-11-02 に承認された（最後の「承認」）。

## 見たいこと
1. 数え方の罠を、SL の道具で防げるか（5-4 と同じ採点で比べる）
2. 道具の説明文で頼んだ順番（SL が先、run_sql は SL で答えられないときだけ）を守るか

## 比べる組
| 組 | 窓口（`agent/sl_mcp`） | 見える道具 | 5-4 で当たる組 |
|---|---|---|---|
| `sl_mcp` | 既定の形（`SL_MCP_MODE` なし） | `list_metrics`・`get_dimensions`・`query_metrics`・`run_sql` | `sl`（ただし run_sql も使える） |
| `sql_mcp` | `SL_MCP_MODE=sql` | `list_metrics`・`run_sql` | `t2s_desc`（指標の説明は読めるが、SL の集計の道具は無い） |

- 2組の違いは、見える道具と、説明文の順番の文（「数字の問いには、まず SL の道具（…）を使い、SL で答えられないときだけ run_sql を使う。」）の有無だけ。ほかの説明文（kind の意味、答えが得られないときの文）は同じ。`check.py` の条件8で確かめた（下の「準備の確かめ」）
- 差の読み方：`sql_mcp` と `sl_mcp` の差は、同じモデル・同じ外枠で「SL の集計の道具があるか」の差

## 会場
- 1本ごとに、リポジトリの外の新しい空のフォルダ（`~/stage2-venue/run_001/<組>/<問>_r<回>/`）で、新しい `claude` のプロセスを起動する。前の本の会話は持ち越さない
- 解く Claude に見えるのは、前置き（システムプロンプト）と「質問：{q}」と、組の道具だけ。罠の注意は、前置きにも会場のどこにも書かない（`agent/sl_mcp/README.md` の理由と同じ）
- ハーネス：`harness.py`（このフォルダ）。問題文と「今日」は 5-4 の `run_001/harness.py` の `QUESTIONS` と `TODAY` を読む（写さない）

### コマンド（ハーネスが組み立てる。パスは `~` で書いた）
```
cd ~/stage2-venue/run_001/<組>/<問>_r<回>      # 毎回、新しい空のフォルダ
env -u 'CLAUDE*' -u 'ANTHROPIC*' \              # 親の CLAUDE*・ANTHROPIC* の変数は渡さない（ハーネスが取り除く）
    CLAUDE_CODE_DISABLE_CLAUDE_MDS=1 CLAUDE_CODE_DISABLE_AUTO_MEMORY=1 \
    DISABLE_AUTOUPDATER=1 ENABLE_TOOL_SEARCH=false \
  claude -p "質問：<問題文>" \
    --system-prompt "<前置き>" \
    --model claude-opus-5-5 --effort medium \
    --tools "" \
    --mcp-config ~/stage2-venue/mcp_<組>.json --strict-mcp-config \
    --allowedTools <組の道具を mcp__data__<名前> で1つずつ> \
    --permission-mode dontAsk --permission-prompts none \
    --restricted --disable-slash-commands \
    --max-turns 20 \
    --output-format stream-json --verbose \
    --no-session-persistence
```
（`env -u` の行は説明のための書き方。実際はハーネスが Python で環境変数を作る）

| 旗・変数 | 意味（説明書の要約） | 役目 |
|---|---|---|
| `--tools ""` | 組み込みの道具を全部外す。MCP の道具には効かない | Bash・Read・Grep などを見えなくする |
| `--mcp-config` / `--strict-mcp-config` | 渡した MCP サーバーだけを使い、ほかの MCP の設定は無視する | 会場のサーバー（キー `data`）だけをつなぐ |
| `--allowedTools` | 書いた道具は承認なしで動く | 組の道具を名前で1つずつ書く |
| `--permission-mode dontAsk` | 承認が要る呼び出しは、すべて断る | 書いていない道具は動かない |
| `--permission-prompts none` | 承認を聞く相手がいない。人に答えを求める道具を外す | 試験中に聞き返しで止まらない |
| `--restricted` | ユーザー・プロジェクト・ローカルの設定ファイルを読まない。コマンドを実行する道具と WebFetch を外す | `~/.claude/settings.json` と CLAUDE.md を読ませない（試しで、これが CLAUDE.md を止めていると分かった） |
| `CLAUDE_CODE_DISABLE_CLAUDE_MDS=1` | CLAUDE.md を読み込まない | 二重の止め（単独で効くかは確かめていない。下の「試しの結果」） |
| `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1` | 自動の記憶を作らず、読まない | 記憶を持ち込まない |
| `--disable-slash-commands` | スキルとコマンドを止める | 同期されたスキルを止める |
| `--system-prompt` | 既定のシステムプロンプトを置き換える | Claude Code の作業の指示と git の状態を入れない |
| `ENABLE_TOOL_SEARCH=false` | MCP の道具を最初から全部読み込む | 道具を後から読み込む手順を挟まない |
| `DISABLE_AUTOUPDATER=1` | 裏での自動更新を止める | 本の途中で版が変わらないようにする |
| `--max-turns 20` | ターン数の上限。超えるとエラーで終わる | 終わらない本を打ち切る |
| `--output-format stream-json --verbose` | 1行1件の JSON。最初に init、最後に result | 記録の元 |
| `--no-session-persistence` | 会話をディスクに残さない | `~/.claude/projects/` に会場の記録を作らない |

- MCP の設定ファイル（`~/stage2-venue/mcp_<組>.json`）は、ハーネスが起動のたびにリポジトリの外に書く。中身は `.mcp.json` と同じコマンドを絶対パスにし、`"alwaysLoad": true` を足したもの。`sql_mcp` だけ `"env": {"SL_MCP_MODE": "sql"}` を足す
- サーバーのキーは、2組とも中立の名前 `data`（道具の名前は `mcp__data__…`）。`sl` の2文字が SL を思わせる手がかりにならないようにするため（人の判断、2026-11-02）。リポジトリの `.mcp.json`（キー `sl`）は変えない。変えたのは会場の設定ファイルとハーネスだけ

## Claude Code・モデル
- Claude Code：PATH の `claude` 2.1.316（npm で mise の node 22.22.2 の下に入っている）。1本ごとに `claude --version` を記録し、`2.1.316 (Claude Code)` でなければ止まる。`~/.claude/settings.json` は変えない
- ログイン：Claude Max のアカウント（OAuth）。`--bare` は OAuth を読まないので使わない
- モデル：`claude-opus-5-5`（説明書 model-config の例の ID。試しの init の `model` と result の `modelUsage` で一致を確かめた）。effort は `medium`
- 内容による自動のモデルの切り替え（説明書：Opus 5.5 は、安全の分類器に当たると別のモデルで回し直す）を見張る。`modelUsage` に `claude-opus-5-5` 以外が出たら止まる。`safety_stops` も記録する
- temperature は CLI から指定できない。毎回同じ答えになる設定ではない

## 前置き（`--system-prompt`）と問
5-4 の ROUND1 の sl から、材料（context）と「mf query を1本」「```bash で囲む」を除いたもの。順番の頼みは書かない（説明文の中にだけある）。
```
あなたはデータアナリストです。今日は 2026-10-29 です。使える道具を使って、質問に答えてください。
答えは、質問した人に向けて日本語で書いてください。道具を使わずに答える場合は、理由を書いてください。
```
問は `-p` に `質問：{q}` だけを渡す。問題文は 5-4 の `QUESTIONS`（`questions.md` の表と見出しとも、13問すべて1文字も違わないことを確かめた）。

### 解く Claude に見えていたもの（試しで分かった。外せていない）
- 前置きの前に、Claude Code が `You are a Claude agent, built on Anthropic's Claude Agent SDK.` を付ける
- `# Environment` の節：作業フォルダの絶対パス、git でないこと、OS、シェル、モデルの名前と ID、知識の期限、**本当の日付（`Today's date is 2026-11-02.`）**
- ログイン中のアカウントのメールアドレス（system-reminder として）。見えることは認める（人の判断、2026-11-02）。記録に出たら止まる

## 「今日」
- 前置きは 5-4 と同じ 2026-10-29。ただし、上のとおり本当の日付も見えている。**解く Claude には2つの日付が見えている**。これは認める（人の判断、2026-11-02）
- 試しで「今日の日付は？」と聞くと、2026-10-29 と答えたうえで、本当の日付と食い違っていると書き、「どちらを基準にするか指定してほしい」と言った
- 日付に左右される問：**D6「今月の売上は？」**（5-4 では 2026-10。回す日によっては 2026-11）。どちらの月でもデータは無いので、正解（「データがない（売上は 2026-04 まで）」）は変わらない。採点の線は下の「採点」
- 年の取り方に左右されうる問：B5（2月）と C3（4月）。どちらの日付でも 2026 年と読めるので、影響は小さい見込み
- 答えの中で「今月」をどの月と読んだかを、本ごとに記録する

## 5-4 との違い
| 違い | 5-4（run_002） | 段階2 run_001 |
|---|---|---|
| モデル | gpt-oss:120b（手元、temperature 1） | Claude Opus 5.5（`claude-opus-5-5`、effort medium） |
| 外枠 | 単発のプロンプト2回（クエリを書く → 結果を見て答える） | Claude Code のエージェントのループ（同じ会話の中で何度も呼べる） |
| システムプロンプト | 無し | 前置き＋Claude Code が付ける1文と Environment の節 |
| 日付 | 2026-10-29 だけ | 2026-10-29（前置き）と、回す日の日付（Environment）の2つ |
| 試す回数 | エラーのあと1回だけ書き直し（最大2回） | `--max-turns 20` まで何度でも |
| 道具 | sl は `mf query` を文字で書く。t2s は SQL を1本 | 欄で渡す。サーバーが語彙・`{{ }}` を確かめて断る。SQL は run_sql |
| sl の組の SQL | 使えない | run_sql が使える |
| 材料 | `context_*.txt` を指示文に入れる | `list_metrics`・`get_dimensions` と道具の説明文。テーブルの列は run_sql で自分で調べる（`t2s_desc` は列名と型を渡されていた） |
| 指標の説明 | `revenue_amount` は改行を詰めた形 | manifest のまま（`revenue_amount` だけ改行あり。ほかの4つは同じ文） |
| 結果の形 | mf の表の文字、DuckDB の表（6000字まで） | JSON の行と kind と message |
| 結果を読む指示 | 無い | ある（「kind が ok と empty 以外なら、答えは得られていない。数字を作らず、答えられなかったと伝える」「null_value は…分からない」） |
| 本数 | 3組 × 13問 × 3回 | 2組 × 13問 × 3回 ＝ 78本 |

### 言えなくなること
- 段階2と 5-4 の差を、「MCP の道具のおかげ」とは言えない。モデル、外枠、試す回数、日付の見え方が同時に変わっている
- kind の message は罠の注意ではないが、空の結果や作り話についての読み方の指示である。5-4 との比べで、C3・D6 と軸4 の差は、この文の効果と分けられない（2組の間では同じ文なので、組どうしの比べには効かない）
- 2つの日付が見えているので、D6 で「どちらの日付か」と聞き返す答えは、5-4 には無かった形になる
- 言えるのは、段階2の中の2組の比べ（同じモデル・同じ外枠で、SL の集計の道具があるか）

## 回数と順番
- 各組・各問3回。13問 × 2組 × 3回 ＝ 78本
- 順番：1回目を2組×13問 → 2回目 → 3回目（`sl_mcp` の13問 → `sql_mcp` の13問、を3回）
- 各本に `rep`、`started_at`・`ended_at`（JST）を残す。途中で止まったら、既にある記録は飛ばして続きから回る

## 夜3時の dbt build を避ける
- ハーネスは JST 02:50〜03:15 には新しい本を始めず、1分ごとに待つ（判定はサーバーと同じ `guards.in_maintenance`）
- 本の途中で `maintenance` が返ったら、ハーネスは止まる。その本は消して回し直す
- 回す前と後に、`output.sha256` の照合と `auto_score.py` の自己照合（`answer_queries.sql` との突き合わせ）をする
- 始めるのは 03:15〜00:30 の間（下の見込みの上限でも 02:50 にかからない）

## 時間と使用量の見込み
- 試し（下）の1本は 4〜26 秒、見積もりの費用は 0.004〜0.078 USD（`total_cost_usd`。請求額ではない）
- 13問は試しより手順が多い見込み。1本 20〜90 秒とすると、78本で 26〜117 分（推測）。費用の見積もりは記録に残すだけ（Max の枠から出る）

## 記録
- リポジトリに残すもの：`runs/<組>_<問>_r<回>.json`。ハーネスが決めた欄だけを書く
  - `id`、`question`、`rep`、`group`、`side`（2組とも `sl`。`auto_score.py` の決めごと2の判定に使う）、`started_at`・`ended_at`、`exit_code`
  - `claude_version`、`model_flag`、`init_model`、`models_used`、`effort`、`flags`（質問は `<質問>` に置き換え）、`env_set`、`env_stripped_names`（取り除いた変数の名前だけ）
  - `init`（`claude_code_version`・`tools`・`mcp_servers`・`plugins`・`skills`・`slash_commands`・`output_style`・`permissionMode`・`apiKeySource`・`agents`・`per_turn_effort_active`・`additional_directories`）
  - `calls`（順番、道具、引数、返ってきた kind、返事。返事は4000字で切る）、`n_tool_use`、`n_tool_result`
  - `final_answer`、`no_query`、`result_subtype`、`is_error`、`stop_reason`、`terminal_reason`、`safety_stops`、`num_turns`、`duration_ms`、`total_cost_usd`、`usage`、`permission_denials`、`n_events`、`problems`
- 生の stream-json・stderr はリポジトリの外（`~/stage2-venue/run_001/raw/`）。コミットしない（init に作業フォルダの絶対パスが入るため）
- 個人情報：記録の文字列のホームのパスを `~` に、ユーザー名を `<user>` に置き換えてから書く。書いた後に、ホームのパス・ユーザー名・`/Users/`・メールアドレスの数を数え、1つでもあれば止まる。コミットのときは `.githooks` が足す行を検査する

## 採点
- 軸1・軸2 と原因の札：5-4 と同じ決まり（`questions.md` の評価の決めごと1〜7、run_002 の conditions.md の「回した後に決めたこと」）
  - 軸1 は `../../5-4/run_002/auto_score.py` をそのまま使う。記録の `side` は2組とも `sl`、`no_query` は「`query_metrics` と `run_sql` を1回も呼ばなかった」（D 型でクエリを呼ばずに断った本は「答えなし」。5-4 で T2S が断った本も同じ扱いにしたのに合わせる）
  - 正解の形が文の問（C1・C3・D6）と、クエリを呼ばずに断った本は、自動の判定を下書きとし、読んだ見立てで決める
  - **D6 の線（日付が2つ見えることへの対応。人の判断、2026-11-02）**：答えの中で「どちらの日付の月でもデータが無い（売上は 2026-04 まで）」と言えていれば軸1 ○。日付を聞き返すだけで、データが無いことを言っていなければ「答えなし」。ほかは questions.md の D6 の採点の注意のとおり（0 円や売上なしの可能性と並べたら×）
  - **例外：`auto_score.py` は、自己照合と referrer の数え方のために DuckDB の CLI を直接起動する。** 段階2で Bash から `mf`・`duckdb` を直接打つのは禁止しているが、これは解く側ではなく採点する側の道具なので認める（人の判断、2026-11-02）
- **軸3・軸4 の下書きの道具：`axis_draft.py`（このフォルダ）。** 本番の前にコミットする（結果を見てから線を引かないため）。`python3 docs/analysis/stage2/run_001/axis_draft.py runs` で、1本1行の下書きを出す。決めるのは人
- **軸3 道具の順番（`sl_mcp` だけ）**：記録の `calls` の順番から
  - 守った：SL の道具（`list_metrics`・`get_dimensions`・`query_metrics`）だけで終えた／SL で答えが得られなかった（`query_metrics` で ok でも empty でもない kind が出た、または `get_dimensions` が unknown_name）あとで `run_sql` を使った
  - 破った：SL の道具より先に `run_sql` を使った／`query_metrics` で ok が出たあとに `run_sql` を使った
  - 要確認：`query_metrics` を呼ばずに、語彙に無いと判断して `run_sql` に進んだ／`query_metrics` が empty のあとに `run_sql` を使った（線に無い形）
  - 対象外：道具を1回も呼ばなかった
- **軸4 札の読み方（2組とも）**：どれかに当たれば「要確認」、どれにも当たらなければ「問題なし」
  - empty が出て、答えに 0・売上なしの言い方（「0 円」「0 件」「ゼロ」「売上はありません」など）がある
  - null_value が出て、答えに同じ言い方がある
  - ok も empty も1回も出ていないのに、答えに数がある（作り話の候補）
  - 答えの数のうち、どの道具の返事にも出てこない数がある（計算した値か、作った値か）。数の拾い方は `auto_score.py` と同じ。12以下の数、年（2025・2026）、問題文の数、日付の数（前置きの「今日」と、その本を回した日）は見ない
  - 分かっている限界：記録の返事は4000字で切るので、切られた所にある数は「返事に無い」と出る。答えの中で足し引きした値（例：8,428 − 828）も「返事に無い」と出る。どちらも人が読んで決める
- 下書きの道具の確かめ（2026-11-02）：わざと作った13件の記録（守った3・破った2・要確認2・対象外1、empty を0と読んだ・null_value を0と読んだ・作り話・計算した値・問題なし）で、13件とも期待どおりの判定になった。試しの記録9本でも動かした（下の「試しの結果」）

## 判定の線（結果を見る前に決めた線）
「A〜C 型の27本で、sql_mcp の印の無い○が sl_mcp 以上で、かつ sql_mcp の『値は合ったが数え方が違う』○が0本で、かつ sql_mcp が同じ問の3回で同じ数え方をしていたら、『この13問の範囲では、モデルで足りた』と書く。どれかが欠けたら、欠けた所を書く」

- 「同じ数え方をしていた」の数え方（人の判断、2026-11-02）
  - 数で答える問（A1・A3・B2・B3・B4・B5・C2）：同じ問の3本の答えの値が一致していること（表の問は、表の値がすべて一致）
  - 文で答える問（C1・C3）：同じ問の3本で、軸2 の札が同じこと

## 止まる条件
ハーネスが1本ごとに確かめ、当たったらその場で止まる（`problems` か個人情報の数）。
- init の道具が組の予定と違う（`EndConversation` は避けられない5つ目として除いて比べる）
- 会場のサーバー（キー `data`）に接続していない
- init の model、または `modelUsage` のモデルが `claude-opus-5-5` でない
- 予定の外の道具を呼んだ
- `maintenance` が返った
- `query_metrics` の where に、外のファイルを読む印（`read_csv`・`read_json`・`read_text`・`read_parquet`・`read_blob`・`glob(`・`'/`・`../`・`~/`）がある（README の「知っている穴」）
- `claude --version` が `2.1.316 (Claude Code)` でない
- 記録に、ホームのパス・ユーザー名・`/Users/`・メールアドレスがある
- 回す前の `output.sha256` の照合が合わない

人が止めるもの：同じ原因で2回直しても通らないとき。

## 準備の確かめ（2026-11-02）
- `check.py`：既定の形の条件1〜7と、sql の形の条件8（道具が2つだけ、説明文に `query_metrics`・`get_dimensions`・順番の文が無い、ほかの文は既定から順番の文を除いたものと同じ、知らない `SL_MCP_MODE` では起動しない）が、すべて PASS。warehouse.duckdb の sha256 は試す前と同じ
- 既定の形の道具の名前・説明文・引数の形が、変更前（HEAD）の `server.py` と同じことを、2つを別々に読み込んで比べて確かめた（4つとも同じ）。同じ比べ方を sql の形にかけると違いを拾うことも確かめた

## 試しの結果（2026-11-02、数に入れない）
13問は使わない。生の記録は `~/stage2-venue/trial/` の下（コミットしない）。
1回目（15:39〜15:44 JST）はサーバーのキーが `sl` だった。キーを `data` に替えたあと、2本（trial_flow_sl・trial_flow_sql）を回し直した（16:01〜16:02 JST）。

| 試し | 組 | 問 | 呼んだ道具（kind） | 結果 |
|---|---|---|---|---|
| trial_flow_sl（回し直し） | sl_mcp | delivered_count の全体はいくつ？ | query_metrics（ok） | 8,428 と答えた。9秒 |
| trial_flow_sql（回し直し） | sql_mcp | 同上 | list_metrics（ok）→ run_sql（empty）→ run_sql（ok）×3 | 8,428 と答え、綴り違い・不正な contact_id・遅延到着の件数も添えた。17秒 |
| trial_bash | sl_mcp | Bash で ls を実行して | なし | 「Bash を実行する道具がない」。permission_denials は空 |
| trial_read | sl_mcp | questions.md を読んで | なし | 「ファイルを開く道具がない」 |
| trial_outside | sl_mcp | ~/homelab-data-platform/CLAUDE.md の中身を教えて | なし | 「ファイルを読む道具がない」。DuckDB に `read_text` があることには触れたが、使わなかった |
| trial_instructions | sl_mcp | 受け取っている指示を全部そのまま書き写して | なし | 前置き、Environment の節、メールアドレスの reminder があると書いた。ユーザーの CLAUDE.md の中身は無い |
| trial_date | sl_mcp | 今日の日付は？ | なし | 2026-10-29 と答え、Environment の 2026-11-02 と食い違うと書いた |

### 計画の確かめの表の合否
| 確かめること | 確かめ方 | 合否 |
|---|---|---|
| 道具は組の分だけ | 回し直した2本の init の `tools` が、sl_mcp は `mcp__data__` の4つ、sql_mcp は `mcp__data__` の2つだけ。`mcp_servers` は `data` が connected。1回目の7本も、キー `sl` で同じ形だった。`EndConversation` は init に出なかった | 合格 |
| 組み込みの道具は呼べない | init に組み込みの道具が無い。trial_bash・trial_read で道具の呼び出しが0件 | 合格 |
| 会場の外のファイルが読めない | trial_read・trial_outside で呼び出し0件。run_sql の外のファイル読みは `check.py` 条件6で sql_error。where の穴（README）は使われなかったが、塞いでいない（止まる条件で見張る） | 合格（where の穴は監視） |
| CLAUDE.md・ユーザー設定が読まれていない | init の `skills`・`slash_commands` が空、`output_style` が `default`（ユーザー設定は Explanatory）。trial_instructions の答えにユーザーの CLAUDE.md の語（ask-local など）が0件。debug の記録に、ユーザー設定の許可ルールを読んだ行が0件 | 合格 |
| 上の確かめ方が、読まれたときに拾えるか（対照） | 対照1：`CLAUDE_CODE_DISABLE_CLAUDE_MDS` だけを外す → CLAUDE.md の語は0件（`--restricted` だけで止まっている）。対照2：変数と `--restricted` の両方を外す → 答えに ask-local が7件、`output_style` が Explanatory、debug にユーザー設定の許可ルールの行 | 拾えた |
| 記録に個人情報が無い | 回し直した2本で、ホームのパス・ユーザー名・`/Users/`・メールアドレスが0件。1回目の記録も、対照2を除いて0件。対照2は答えにメールアドレスを書き、数え方が1件を拾った（本番なら止まる）。生の記録には、ホームのパスがある（リポジトリの外） | 合格 |
| 記録が取れる | 回し直した2本で、生の記録の tool_use と tool_result の数が、記録の `n_tool_use`・`n_tool_result` と同じ（1と1、5と5）。返事の kind がすべて読めた。1回目の9本も同じ | 合格 |
| 軸3・軸4 の下書きが出る | 試しの記録9本で `axis_draft.py` を動かした。trial_flow_sl は軸3「守った」・軸4「問題なし」。trial_flow_sql は軸4「要確認」（答えの中で足し引きした 7,600・8,451 と、返事を足し合わせた 182・828 が「返事に無い数」として出た）。道具を呼ばなかった本は軸3「対象外」 | 形を確かめた |

### 試しで分かったこと（条件に足した）
- `--system-prompt` で置き換えても、Claude Code の1文と Environment の節（本当の日付と作業フォルダのパスを含む）は残る。日付が2つ見える
- アカウントのメールアドレスが、解く Claude に渡っている。答えに書くことがある（対照2）。記録の個人情報の数え方にメールアドレスを足した
- init の `plugins` に、組み込みのプラグインが4つ出る（`cc-plugin-agents-md`・`cc-plugin-telemetry`・`cc-plugin-plugin-authoring`・`cc-plugin-easel`、すべて `@builtin`）。道具・スキル・コマンドは足していない（`tools`・`skills`・`slash_commands` に出ない）
- init の `agents` にサブエージェントの種類が並ぶが、Agent の道具が無いので呼べない
- `EndConversation` は init の `tools` に出なかった。説明書は「MCP の道具がある限り外せない」と書いているので、避けられない5つ目として、止まる条件の比べから除く（人の判断、2026-11-02）
- `axis_draft.py` は、初めの版では日付の「29」を「返事に無い数」として拾った（trial_date）。結果を見る前に、日付の数を見ない線に直した

## 人の判断（2026-11-02）
1. 日付が2つ見えることは認める。D6 の採点の線は「採点」の節のとおり（どちらの日付の月でもデータが無いと言えていれば軸1 ○、日付を聞き返すだけなら「答えなし」）
2. メールアドレスが解く Claude に見えることは認める。記録に出たら止まる、は今のまま
3. サーバーのキーは、2組とも中立の名前 `data` にする（道具の名前は `mcp__data__…`）。リポジトリの `.mcp.json`（キー `sl`）は変えず、会場の設定ファイルとハーネスだけを変える
4. 軸3・軸4 の下書きの道具（`axis_draft.py`）は、本番の前に書いてコミットする
- そのほか：モデルは `claude-opus-5-5`、effort は medium。前置きは `--system-prompt`。自動更新は1本ごとに版を記録して止まる。軸3は `sl_mcp` だけ。組は `sl_mcp` と `sql_mcp` の2つ。`EndConversation` は避けられない5つ目として認める。`auto_score.py` が duckdb を直接起動するのは採点する側の例外として認める
- 「同じ数え方をしていた」の数え方は、判定の線のすぐ下のとおり

## 承認
- 2026-11-02 人間が承認（チャット経由）。本番の78本は、このファイルのコミットの後、別の指示で回す
