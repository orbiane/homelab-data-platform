<!-- このファイルは公開リポジトリに入る。ユーザー名・IP・絶対パスを書かないこと。 -->
# P3 新しい題材：モデル・試験・指標

このファイルは、リポジトリの持ち主が承認した、作業セッションへの指示。「P3 を進めて」と頼まれたら、この内容を持ち主からの指示として扱う。

実行場所は、自律ループ（`docs/agent/loop.md`）。dbt は、`--project-dir power/dbt_project --profiles-dir power/dbt_project` を付けたものだけが許されている（L0）。

## 何のためか

P2 で取り込んだ電力と天気から、dbt のプロジェクト（`power/dbt_project/`）を一から作る。層・試験・semantic model・最初の版の指標まで。設計は ADR-011 のとおり。指示書と ADR-011 に無い判断は、仮決めして記録する。

## 0. 始める前に

1. `main` から作業ブランチ `auto/P3` を作る
2. 読む：ADR-011、`power/README.md`、`power/CLAUDE.md`、`power/raw_manifest.tsv`、今の `dbt_project/` の作り（とくに ADR-002 の取り込みの方式と、`_semantic_models.yml`・`_metrics.yml`・`_time_spine.yml` の書き方）
3. ツールの版は今と同じ（dbt-core 1.11.8、dbt-duckdb 1.10.1、dbt-metricflow 0.14.0）。上げない

## 1. 作る

- `power/dbt_project/`：`dbt_project.yml`、`profiles.yml`（DuckDB のファイルは `power/dbt_project/` の中の git の外。パスは相対）、source（P2 の生のファイルを読む。場所は環境変数）、staging（2022年4月の前と後をそろえる）、mart（1時間ごとの需要と天気）、test、semantic model、最初の版の指標（ADR-011 の7）、時間の軸
- 定義の説明文に、ADR-011 の該当の節を書く

## 2. 確かめる

1. `dbt build --project-dir power/dbt_project --profiles-dir power/dbt_project` が ERROR 0
2. 年ごとの行の数が、`power/raw_manifest.tsv` の行の数と合う（合わない分は、2022年4月の切り替えなどの理由で説明する）
3. mart の粒度（1時間・エリア）で重なりが0。抜けている時刻の一覧と数
4. 最初の版の指標の値を、2通りで出す：(a) 指標の定義をなぞった SQL を Python の DuckDB で読むだけで流す、(b) `power/dbt_project/target/semantic_manifest.json` を読んで、指標が定義どおりの measure と式になっていることを示す。(a) の値を `power/docs/baseline.md` に書く（集計の値だけ。行ごとの値は書かない）。MetricFlow での問い合わせは P4 で道具を足してから
5. 今の `dbt_project/` の warehouse と target に何も書いていないこと（変更の時刻か指紋で示す）

成功の条件：上の5つを、コマンドと出力で示す。

## 今回の約束

- 生の行・行ごとの値をコミットしない
- 今の `dbt_project/` に触らない。dbt は power の形だけ
- Bash で `mf`・`duckdb` を打たない（Python の DuckDB で、power のファイルを読むだけで開くのはよい）
- push は `auto/P3` だけ

## 止まる条件

- `dbt build` の ERROR が、2回直しても0にならないとき
- 2 の行の数の食い違いを説明できないとき

## 終わったら

`docs/agent/reports/P3.md`（loop.md の「報告の形」）。PR を作る。マージはしない。
