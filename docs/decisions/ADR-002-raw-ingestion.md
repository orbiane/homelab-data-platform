# ADR-002: raw の取り込みに external_location を使い、seeds を採用しない

- Status: Accepted
- Date: 2026-07-05

## 背景

生成した CSV を dbt に取り込む方法を決める必要がある。dbt には `seeds` という
CSV 取り込み機能があり、最も手軽な選択肢である。

## 選択肢

**A. dbt seeds を使う。** `dbt seed` で CSV がテーブルとして取り込まれる。設定不要。

**B. dbt-duckdb の external_location を使い、CSV を source として参照する。**
`_sources.yml` に相対パスを書き、DuckDB が直接 CSV を読む。

## 決定

**B を採用する。**

## 理由

seeds は CSV を dbt プロジェクトの一部として扱う。これは
「外部から届いたデータを取り込む」という現実の構図と異なる。具体的に失うものが2つある。

**source freshness が使えない。** seeds には「いつ更新されたか」の概念がない。
上流データの停止を検知する仕組みが成立しなくなる。これは後のガバナンス演習で
中心的に扱う機構である。

**source 定義そのものの学習機会を失う。** 実務ではデータは常に外部から来る。
source の宣言、freshness の設定、テストの付与といった作業は、seeds では発生しない。

## 帰結

- CSV のパスは相対パス（`../data_generation/output/*.csv`）で記述する。
  絶対パスをリポジトリに含めないため、実行時のカレントディレクトリに依存する。
  dbt は必ず `dbt_project/` 内から実行する必要がある。
- Airflow から実行する際も同様で、DAG の bash_command で `cd` してから
  `dbt build` を呼ぶ形になる。この制約は BashOperator の作業ディレクトリが
  一時領域であるため、明示的に対処が必要だった。
