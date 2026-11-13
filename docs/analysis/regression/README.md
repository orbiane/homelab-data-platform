<!-- このファイルは公開リポジトリに入る。ユーザー名・IP・絶対パスを書かないこと。 -->
# 回帰の試験（第1段：数字の層と文書の層）

決めた数字（5-4 の13問の正解）を、定義や文書を変えるたびに解き直し、前に合っていたものが崩れていないかを見る。ADR-007 の関所は「決定メモのパスがあるか」という形しか見ない（ADR-007 の H1）。この試験は中身を見る。作ったのは R1（`docs/orders/R1-regression-numbers-docs.md`）。

## 何を試すか

| 層 | 道具 | 中身 |
|---|---|---|
| 数字 | `run_numbers.py` | `bank.json` の13問を、(a) SL の道具（`agent/sl_mcp/server.py` の `query_metrics`・`list_metrics` を import して呼ぶ）と、(b) SQL（`sql/<ID>.sql` を server の `run_sql` で流す）の2通りで解き、それぞれを期待値と比べる。問ごとに「合う／外れる／未決」と件数を出す |
| 文書 | `check_docs.py` | git の履歴から `dbt_project/**/_metrics.yml` にあったことのある指標の名前を集め、今の manifest に無い名前（廃止した名前）が、今を説明する文書に単語として出てくるかを見る |

- 今を説明する文書：`README.md`（リポジトリ直下）、`CLAUDE.md`、`agent/sl_mcp/README.md`、ADR-006 の「基準値」の節。ほかの ADR と `docs/analysis/` は過去の記録なので見ない
- 廃止した名前が出てきても、同じ行に「その名前を消したコミットが指した決定メモのパス」（`docs/business/...md`）があれば、履歴の記述として外れに数えない（数えなかった行も一覧に出す）
- 名前が決定メモのパスの中にだけ出てくる行（例：`2026-11-06-ctr-opened.md` の `-ctr-`）も外れに数えず、別の一覧に出す。`-` は単語の区切りになるので、パスの中の名前にも当たるため

## 回し方

リポジトリの直下で（JST 02:50〜03:15 は道具が maintenance を返すので回さない）：

```
cd data_generation/output && shasum -a 256 -c ../output.sha256   # まずデータの版を照合する
uv run --frozen --project agent/sl_mcp python docs/analysis/regression/run_numbers.py [--out results/<日付>.md]
uv run python docs/analysis/regression/check_docs.py [--out results/<日付>.md]
```

- `run_numbers.py` は server の依存（mcp）が要る。依存の無い Python（例 `uv run python ...`）で起動されたときは、上の `--project agent/sl_mcp` の形で自分を起動し直す
- 終了コード：`run_numbers.py` は 0＝外れ0、1＝外れが1件以上、2＝道具が maintenance か busy を返した（試験にならない）。`check_docs.py` は 0＝外れ0、1＝外れが1件以上
- `--out` を付けると、画面と同じものをそのファイルの末尾に足す

## bank.json の形

1問が1つの要素。欄：

- `id`、`question`：questions.md の ID と問の文
- `sl`：SL の呼び出しのリスト。`tool`（`query_metrics` か `list_metrics`）、`args`（`query_metrics` の欄）、`expect`。C3 は2つ（確定で絞らない／絞る）
- `sql`：`file`（`sql/<ID>.sql`）と `expect`
- `expect`：`kind`（server の返す kind。SL が断るのが正解の問は `unknown_name`、空の結果が正解の問は `empty`）。`ok` のときは、`key`（行を見分ける列）、`rows`（鍵 → 列 → 値）、`exact_keys`（true なら期待に無い行があっても外れ）。鍵は列の値を `|` でつなぎ、空（NULL）は `(空)`。`derive`（2つの列を割った値を足す）と `absent_metrics`（`list_metrics` に出てはいけない名前）も使える
- `expected`（人が読む形の正解）、`tolerance`（`abs` が許す幅と、その理由）、`source`（出どころ）、`decided`（決めた日）
- `status`：`有効` か `未決`（未決は理由を書く。未決の問は比べない）
- `known_errors`：その問で過去に出た×と印。`docs/analysis/5-4/run_002/scores.md` と `docs/analysis/stage2/run_001/final_scores.tsv` から写したもの（記録の本の名前、札・印・規則）。ここで新しく判定したものは無い

許す幅は questions.md の決めごと6（正解と一番近い罠の値の差より小さい幅）から取った。件数と金額は 0、B3・D1 の率は 0.0005。

## SQL を answer_queries.sql から写して変えた所

`sql/<ID>.sql` は `docs/analysis/5-4/answer_queries.sql` の該当のブロック。数え方は変えていない。

- B5・C1・C2・C3：先頭の `create temp view latest_revenue` を、同じ中身の CTE（`with latest_revenue as (...)`）にした。1問ずつ1つの文で動かすため
- ほかの問（A1・A3・B2・B3・B4・D1・D2・D5・D6）は、ブロックのまま
- 先頭の検算（`mismatch_vs_flag`）は写していない（問ではないため）

## 期待値の変え方（ADR-009 の決定4）

期待値は、エージェントが変えてよい。変えるときは次の記録を残す。

1. 期待値の変更だけのコミットに分ける。コミットメッセージは `expected:` で始める
2. その問の `source` の欄（または `history` の欄）に、作業 ID・日付・前の値・変えた理由・2通り（(a) SL と (b) SQL）で出した値を書く。決定メモがあるときは、そのパスも書く
3. 作業の報告（`docs/agent/reports/<ID>.md`）の7に書く
4. 許す幅は広げない。広げたいときは、決めごと6のどの罠との差かを書いて、持ち主に聞く

## この試験で言えないこと

- **正解の値も、SL の呼び出しも、SQL も、どれも Claude が書いた。** 人が承認したのは questions.md の値（2026-10-28）と、決定メモ・ADR-009 の決め。(a)(b) が同じ間違いを共有していれば、両方とも「合う」になる
- 数字の層は、決めた13問の数字しか見ない。問に無い指標や切り口が崩れても気づかない
- 文書の層は、指標の **名前** しか見ない。説明文の古さ（例：README の「seeded, deterministic」）や、名前を変えずに数え方だけを変えた場合は捕まらない
- エージェント（`claude -p`）に解かせてはいない（第3段の R3 でやる）
- データの版が変われば、多くの問が外れる。そのときは試験より先に、データの版の照合が合わないことを見る
