# 5-4 run_001 の実行条件

最初の一周（基準の記録）。条件は Claude Code が決めたまま回したもので、事前の承認は受けていない。次の組からは、このファイルの形で条件を書いて承認を受けてから回す。

## 対象とデータ
- 質問：questions.md の13問。LLM には質問文だけを渡す（ID・型・罠の説明は渡さない）
- データ：`data_generation/output.sha256` と 4本とも一致（実行前に照合）
- warehouse：2026-10-29 03:00 に Airflow の `dbt build` で作り直されたもの（記録の `Artifact Modified Time`）。作り直しの後も、`answer_queries.sql` の出力は確定時と同じ（53行、代表値一致）
- ツールの版：dbt-core 1.11.8 / dbt-duckdb 1.10.1 / dbt-metricflow 0.14.0

## LLM
- モデル：gpt-oss:120b（Ollama の ID `714d86958b6e`）
- 呼び方：`ask-local` 経由で Ollama の `/api/generate`（`stream: false`）。temperature・seed は指定していない（Ollama の既定値。同じ入力でも答えは揺れる）
- SL 側と T2S 側で同じモデル（評価の決めごと1）
- 回数：各問1回。26本（13問×2側）、試行は書き直しを含めて30回

## 指示文
- 指示文の本文は `harness.py` の `ROUND1`（クエリを書かせる）、`RETRY`（書き直させる）、`ROUND2`（結果を見て答えさせる）にある
- 両側とも「今日は 2026-10-29 です」と日付を渡した
- 両側とも「クエリを書かずに答える場合は、理由を書いてよい」と書いた（断ることを両側に同じ条件で許す）

## 渡した情報（ここが両側で違う）
| | T2S | SL |
|---|---|---|
| ファイル | `context_t2s.txt` | `context_sl.txt` |
| 中身 | mart の4表の列名と型だけ | 指標の名前と説明文、指標ごとに使えるディメンション、`mf query` の書き方 |
| 作り方 | `information_schema.columns` から機械的に作った | 説明文は `_metrics.yml` から手で写した（後で空白を除いて照合、5件とも一致）。ディメンションは `mf list dimensions` の出力から写した。書き方は `mf query --help` の要約に、`--help` に無い `TimeDimension()` の書き方を1行足した |

- 列の説明・指標の説明は、T2S には渡していない。評価の決めごと1（SL には語彙と説明を渡す）と4（T2S には mart だけ）の組み合わせで生じた偏りで、run_001 の SL と T2S の差は「SL か T2S か」と「説明があるか」を分けられない
- `_models.yml` の列の説明は account_id と currency だけで、品質フラグ（`is_valid_*`）の説明は無い

## 流れと書き直し
1. LLM がクエリを1本書く（SQL か `mf query`）。ブロックが無ければ、その文章を答えとする
2. Claude Code のハーネスが実行する
3. エラーなら、エラーの文（末尾2,000字）を付けて1回だけ書き直させる（最大2回）
4. 最後の試行の結果（末尾6,000字）を LLM に返し、日本語で答えさせる。エラーのままでも返す

## 実行の安全策
- T2S：`duckdb -readonly` で開き、先頭に `SET enable_external_access=false` を足す（外部ファイルの読み書きを止める。実行前に、CSV を読む SQL が止まることを確認）
- SL：シェルを通さず実行。`mf query` 1行だけを許し、オプションは `--metrics --group-by --where --start-time --end-time --limit --order --decimals --quiet --explain` だけ
- SL の出力から、mf の版の案内（`pip install --upgrade` など）とスピナーの行を消してから LLM に渡した。30回の試行の結果に、案内の文は0件

## 記録の後からの手直し
- `runs/sl_B5.json`・`sl_C3.json`・`sl_D5.json`・`sl_D6.json` の mf のエラー出力にあった、ホームディレクトリを含む絶対パス12個（6行）を `~/` に置き換えた。ほかは実行時のまま

## 次の組（run_002）で決めること（未承認）
- 説明つきの T2S：T2S に、SL と同じ指標の説明文を渡す。説明文は `_metrics.yml` から機械的に作る（手で写さない）
  - 渡すのは説明文だけか。measure の式（`_semantic_models.yml` の `expr`）まで渡すか
  - run_001 の `context_sl.txt` は手で写したもの。run_002 で SL 側も機械的に作り直すか、run_001 のものをそのまま使うか
- 回数：各問何回か
- 日付・書き直しの回数・指示文は、run_001 と同じでよいか
