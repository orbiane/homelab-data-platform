<!-- このファイルは公開リポジトリに入る。ユーザー名・IP・絶対パスを書かないこと。 -->
# V1 generator の揺れと実在のブランド名を、コードだけ直す

このファイルは、リポジトリの持ち主が承認した、作業セッションへの指示。「V1 を進めて」と頼まれたら、この内容を持ち主からの指示として扱う。

実行場所は、自律ループ（`docs/agent/loop.md`）。**基準データ（`data_generation/output/`）は作り直さない。** 作り直しは V2（持ち主の見ているセッション）。

## 何のためか

基準データを作る generator には、作り直すと同じ CSV にならない所が2つある（ADR-006）。`revenue_monthly.py` の `hash()`（Python を起動するたびに値が変わる）と、`subscription.py`・`message_event.py` の `uuid.uuid4()`（OS の乱数を使い、`random.seed` が効かない）。また、referrer の値に実在のブランド名が残っている（CLAUDE.md の守ること6）。これをコードだけ直し、「何度作っても同じ CSV になる」ことと、「変わるのは決めた列だけ」であることを、リポジトリの外の一時ディレクトリで確かめる。

## 0. 始める前に

1. `main` から作業ブランチ `auto/V1` を作る
2. 読む：ADR-006、`data_generation/generators/` の4つ、CLAUDE.md の守ること1・6・7
3. データの版の照合（`cd data_generation/output && shasum -a 256 -c ../output.sha256`）

## 1. 直す

- **出力先を選べるようにする**：4つの generator が、環境変数（名前は仮決め。例：`HOMELAB_DATA_OUT`）か引数で出力先を受け取るようにする。指定が無ければ今までどおり `data_generation/output/`。`message_event.py`・`subscription.py`・`revenue_monthly.py` が読む `account_master.csv` も、同じ出力先から読む。4つを決まった順に回す入口（`data_generation/main.py` を使ってよい）を作る
- **`hash()` をやめる**：起動のたびに変わらない計算（例：`zlib.crc32` に account_id と月をつないだ文字を渡す）にする。どれにするかは仮決め
- **uuid4 をやめる**：ID 専用の乱数（`random.Random` の別のインスタンスに、決まった種を渡したもの）から UUID を作る。**ほかの値を作る乱数の流れを変えない**（共有の `random` から引くと、それ以降のすべての値がずれる）
- **ブランド名を中立の名前にする**：`REFERRERS` の中の実在のブランド名（`line_app_search`、`line_ads`、`yahoo_ads`、`google_ads`、`facebook_ads`）を、中立の名前に1対1で置き換える。並びと数は変えない（`random.choice` の結果を変えないため）。新しい名前は仮決め。古い名前と新しい名前の対応表を、`docs/analysis/data-v2/referrer-map.md` に書く

## 2. 確かめる（一時ディレクトリで。リポジトリの外）

この作業に限り、generator を**リポジトリの外の一時ディレクトリに向けて**回してよい（ループの「やらないこと」の例外として、持ち主がこの指示書で許す）。`data_generation/output/` には向けない。

1. 一時ディレクトリ A と B に、それぞれ全部を作る。A と B の4ファイルの sha256 がすべて同じ（何度作っても同じ）
2. A と、今の基準データ（`data_generation/output/`、読むだけ）を比べる。ファイルごとに：行の数、列の名前、列ごとの「値が違う行の数」
   - 見込み：行の数と列の名前は4ファイルとも同じ。値が違うのは、`subscription_log.csv` と `message_event.csv` の `event_id`、`revenue_monthly.csv` の `revenue_amount`（と、それから計算される列があればその列）、`subscription_log.csv` の `referrer`（ブランド名の行だけ。対応表で置き換えると一致する）だけ
3. `account_master.csv` は、今の基準データと同じ sha256 になる見込み（`hash()` も uuid4 も使っていないため）。違ったら、どの列かを書く

成功の条件：1 と 2 と 3 の結果を、コマンドと出力で示す。比べた結果を `docs/analysis/data-v2/v1-check.md` に書く。

## 今回の約束

- `data_generation/output/` と `data_generation/output.sha256` に触らない。`dbt_project/warehouse.duckdb` に触らない
- 汚れを仕込むコード（遅延・重複・孤児・順序矛盾・enum の不正・snapshot drift・未締め・USD など）の中身は変えない
- 変えるのは `data_generation/` のコード、`docs/analysis/data-v2/`、報告、`docs/agent/provisional/V1.md` だけ
- ツールのバージョンを上げない（`uv.lock` を変えない）
- push は `auto/V1` だけ

## 止まる条件

- 2 で、見込みの外の列の値が違ったとき（基準データが、今のコードではない版で作られた可能性がある。直さずに、違った列と件数を書いて止まる）
- A と B が同じにならず、2回直しても直らないとき
- 一時ディレクトリの外に書きそうになったとき

## 終わったら

`docs/agent/reports/V1.md`（loop.md の「報告の形」）。PR を作る。マージはしない。
