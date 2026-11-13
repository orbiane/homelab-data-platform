<!-- このファイルは公開リポジトリに入る。ユーザー名・IP・絶対パスを書かないこと。 -->
# 同じ snapshot_date の行が2つ以上ある組を数える（M4）

- 日付：2026-11-14
- 作業：`NEXT.md` の M4（数えるだけで、直さない）
- データの版：`cd data_generation/output && shasum -a 256 -c ../output.sha256` で4ファイルとも OK

## 何を数えたか

`dbt_project/models/staging/stg_revenue_monthly.sql` は、`is_latest_snapshot` を次の形で付ける。

```sql
row_number() over (
    partition by account_id, revenue_month
    order by snapshot_date desc
) = 1 as is_latest_snapshot
```

並べ方は `snapshot_date` だけなので、同じ `account_id × revenue_month` の中に同じ `snapshot_date` の行が2つ以上あると、どれに印が付くかは決まらない。そういう組がいくつあるかを数えた。

最新の行の所だけではなく、組の中のどの `snapshot_date` でも重なりを数えた（指示書の言い方「同じ snapshot_date の行が2つ以上ある組」に合わせた）。

## 結果

**重なりのある組は 0 組。調べた組は 100 組（183 行）。** mart と raw の両方で同じだった。

| 数えた所 | 行 | 組（account_id × revenue_month） | 重なりのある組 |
|---|---|---|---|
| staging（ビュー） | 数えられなかった（下の1） | — | — |
| mart `main_mart.fct_revenue`（staging の写し） | 183 | 100 | 0 |
| raw `data_generation/output/revenue_monthly.csv` | 183 | 100 | 0 |

0 組なので、「どの組か」と「選ばれる行で金額が変わりうるか」は、書くものが無い。

## 1. staging：MCP の道具 `run_sql` では開けなかった

`main_staging.stg_revenue_monthly` はビューで、中で CSV を `read_csv_auto('../data_generation/output/revenue_monthly.csv')` として読む（`dbt_project/models/staging/_sources.yml` の `external_location`）。`run_sql` はファイル操作を止めた設定で DB を開くため、エラーになった。

```sql
select count(*) as total_rows, count(distinct (account_id, revenue_month)) as total_groups
from main_staging.stg_revenue_monthly
```

```
{"kind":"sql_error", ..., "text":"Permission Error: Cannot access file \"../data_generation/output/revenue_monthly.csv\" - file system operations are disabled by configuration"}
```

## 2. mart：`main_mart.fct_revenue` で、staging の代わりに数えた

`fct_revenue` はテーブル（`information_schema.tables` で `BASE TABLE`）。`dbt_project/models/mart/fct_revenue.sql` は `ref('stg_revenue_monthly')` の列を選ぶだけで、where も distinct も無い。なので、中身は前回の `dbt build` のときの staging と同じ行になる。行の数は、下の raw の CSV（183 行）と同じだった。

数え方1：組の数と、(組, snapshot_date) の数を比べる。

```sql
select count(*) as total_rows,
       count(distinct (account_id, revenue_month)) as total_groups,
       count(distinct (account_id, revenue_month, snapshot_date)) as distinct_triples,
       sum(case when is_latest_snapshot then 1 else 0 end) as latest_rows
from main_mart.fct_revenue
```

```
{"total_rows":183,"total_groups":100,"distinct_triples":183,"latest_rows":"100"}
```

`distinct_triples` が `total_rows` と同じ 183 なので、(組, snapshot_date) の重なりは無い。`latest_rows` は組の数と同じ 100。

数え方2：重なりそのものを出す。

```sql
select account_id, revenue_month, snapshot_date, count(*) as n
from main_mart.fct_revenue
group by account_id, revenue_month, snapshot_date
having count(*) > 1
```

```
{"kind":"empty","message":"条件に合う行が0件だった。", ... "rows":[]}
```

数え方3：重なりのある組を数える（分母は上の 100 組）。

```sql
select count(*) as tied_groups from (
  select account_id, revenue_month
  from main_mart.fct_revenue
  group by account_id, revenue_month
  having count(*) > count(distinct snapshot_date)
) t
```

```
{"tied_groups":0}
```

## 3. raw：CSV をシェルで数えた

raw は CSV で、DB の中には無い。`run_sql` からは読めない（上の1と同じ理由）。リポジトリの中の CSV を、シェルで文字列のまま数えた。CSV の日付は `2025-12-05` のように時刻を含まない形なので、staging の `cast(... as date)` で重なりが新しく生まれることは無い。

```
$ wc -l data_generation/output/revenue_monthly.csv
     184 data_generation/output/revenue_monthly.csv
```

見出し1行と、データ 183 行。

```
$ cut -d, -f1-3 data_generation/output/revenue_monthly.csv | sort | uniq -d | wc -l
       0
```

(account_id, revenue_month, snapshot_date) が2回以上出る組み合わせは 0。

```
$ cut -d, -f1-2 data_generation/output/revenue_monthly.csv | sort -u | wc -l
     101
```

見出しの1行を引くと、組は 100。

## まだ言えないこと

- staging のビューそのものは数えていない。mart は前回の `dbt build` のときの写しで、そのあと CSV が変わっていれば食い違う。今回は sha256 の照合が OK で、行の数も同じだった
- `row_number()` の並べ方が `snapshot_date` だけ、という作りはそのまま。今のデータでは重なりが 0 なので結果は1通りに決まる。データを作り直すと（`NEXT.md` の V2）、重なりが出ることがありうる
