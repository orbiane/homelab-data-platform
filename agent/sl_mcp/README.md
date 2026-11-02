# sl_mcp

## 何のサーバーか

段階2で、エージェントにセマンティックレイヤー（SL）を使わせるための、自前の小さな MCP サーバー。
手元の dbt Core + MetricFlow（`mf`）を包み、`list_metrics` / `get_dimensions` / `query_metrics` / `run_sql` の4つの道具を出す。
dbt 公式の dbt-mcp は、Semantic Layer の道具が dbt Platform の API を通るので、手元の `mf` では動かない。

サーバーの中で強制していること：

- `query_metrics` は欄で受け取り、`mf` のコマンドはサーバーが組み立てる。登録されていない指標・切り口と、`{{ }}` の無い where は、`mf query` に渡す前に断る
- `run_sql` は DuckDB の CLI を `-safe -readonly` で開く（書き込み・外のファイル・ドットコマンドを止める）
- 返事に必ず `kind` を入れ、結果あり・空・語彙に無い・エラー・DB が使用中・build の時間帯を分ける
- JST 02:50〜03:15（毎晩の dbt build）は断る。`mf` と `run_sql` の呼び出しは1つずつ順に処理する

## 道具の説明文に、データの罠の注意を書かない理由

段階1（5-4）の LLM は、品質フラグ・孤児・空の結果の意味などの注意を受け取っていない。
説明文に注意を足すと、5-4 との結果の違いが SL のおかげか、注意のおかげか、分けられなくなる。
そのため説明文には道具の使い方だけを書き、`list_metrics` が返す指標の説明は `semantic_manifest.json` の description をそのまま返す（5-4 で渡したものと同じ）。

説明文を「よく」しようとして、罠の注意を足さないこと。

## run_sql を `-safe` で開いている理由

DuckDB の CLI の「.」で始まる命令（`.shell`、`.output` など）は、SQL より手前で CLI が処理する。
そのため、`-readonly`（読み取り専用）と `enable_external_access=false`（外部アクセスの遮断）の外を通り、シェルの実行やファイルの書き出しができてしまう。
5-4 の `docs/analysis/5-4/run_001/harness.py` の `run_t2s`（`-readonly` と `SET enable_external_access=false;`）にも同じ穴があった。
`-safe` を付けると、これらの命令が止まり、外部アクセスも切れて設定も固まる。`-safe` を外さないこと。

5-4 の記録（`run_001` と `run_002` の `runs/*.json`、143本・157試行）で、LLM が書いたクエリは143本（sl の mf コマンド 53本、t2s の SQL 90本）。
そのうち「.」で始まる行を含むものは0本だった。5-4 で、この穴が実際に使われた跡は無い。

## 順番を説明文で頼むだけにして、仕組みで強制しない理由

「まず SL の道具を使い、SL で答えられないときだけ `run_sql` を使う」という順番は、道具の説明文で頼んでいるだけで、サーバーは強制しない。
エージェントが説明文の順番を守るかを観察するための、意図した設計である。

## SQL だけの形（`SL_MCP_MODE=sql`）を足した理由

段階2の試験では、同じモデルに、SL の集計の道具がある窓口と無い窓口の両方で同じ問を解かせ、SL のあり・なしだけを変えて比べる（5-4 の `sl` と `t2s_desc` の差に当たる）。
起動時の環境変数 `SL_MCP_MODE=sql` を入れると、`list_metrics` と `run_sql` の2つだけを出す。指標の説明は読めるが、`get_dimensions` と `query_metrics` は無い。

- 説明文から、順番の文（「まず SL の道具を使い…」）だけを外す。ほかの文（kind の意味、答えが得られないときの文）は既定の形と同じ。罠の注意は、こちらにも書かない
- 変数が無いとき（既定）の道具と説明文は、この形を足す前と1バイトも変えていない
- `sl` と `sql` 以外の値では起動しない（書き間違いで既定の形に落ちて、気づかずに比べることを防ぐ）
- `check.py` の条件8で、道具が2つだけ見えること、説明文に `query_metrics` と `get_dimensions` の名前が出てこないこと、ほかの文が既定と同じことを確かめる

## Bash で mf と duckdb を打つ道を閉じた理由

MCP のサーバーは道具を足すだけで、エージェントから Bash の道を取り上げない。
Bash で `mf` や `duckdb` を直接打つと、サーバーの柵（`{{ }}` の確かめ、`kind`、`-safe`）を素通りする。
段階2では、エージェントが説明文の順番を守るかを4つの道具の中で観察するので、`.claude/settings.json` の deny に `Bash(mf *)` と `Bash(duckdb *)` を入れて閉じた。
4つの道具は allow に1つずつ名前で書いた（`mcp__sl__*` とまとめて書くと、道具を足したときに承認なしで使えてしまうため）。

deny はコマンドの文字に当たるだけなので、フルパス（`~/.local/bin/mf`）や `sh -c` などの書き方はすり抜ける。
Manual モード（承認を毎回聞くモード）なら、それらは承認の画面で止まる。

## 知っている穴（直していない）：query_metrics の where

`query_metrics` の where は自由な文字で、`mf` を通って DuckDB の SQL にそのまま入る。
`run_sql` の `-safe` は、この道には掛かっていない。

試し（2026-11-02、MCP を通さず Python から `server.query_metrics` を1回呼んだ。読むだけ）：

- metrics `revenue_amount`、group_by `revenue_record__currency`
- where `{{ Dimension('revenue_record__currency') }} IN (SELECT 'JPY' FROM read_csv('../data_generation/output.sha256'))`
- 結果は kind `ok`、行は `JPY 45440100`（ADR-006 の JPY 45,440,100 と同じ）

where の中の SQL が、リポジトリの中の別のファイル（`data_generation/output.sha256`）を読めた。書き込みの試しはしていない。
今は、悪意のあるエージェントではなく、間違えるエージェントが相手なので直さない。段階3で扱う。
