<!-- このファイルは公開リポジトリに入る。ユーザー名・IP・絶対パスを書かないこと。 -->
# V2 基準データを作り直し、新しい版にする

このファイルは、リポジトリの持ち主が承認した、作業セッションへの指示。「V2 を進めて」と頼まれたら、この内容を持ち主からの指示として扱う。

実行場所は、持ち主の機械の Claude Code で、**持ち主が見ている（承認の画面が出る）セッション**。権限モードは Manual。理由：基準データの作り直しと warehouse への書き込みは、止まる類（ADR-009 の決定3、CLAUDE.md の守ること7）。作り直しそのものは、持ち主が ADR-009 の Q4 で承認した。1つずつの操作は、承認の画面で承認する。

## 何のためか

V1 で直した generator で、基準データを作り直して版2にする。これは「データが変わる」腐敗を、わざと1回起こすことでもある。**回帰の試験の期待値は、ここでは直さない。** 毎晩の見張り（W3 で据え付けた）と回帰の試験が、この変化を捕まえるかを V3 で見るため。

## 0. 始める前に

1. `main` を pull し、作業ブランチ `owner/V2` を作る
2. 読む：ADR-006、`docs/analysis/data-v2/v1-check.md`、`docs/analysis/regression/README.md`、W2 の README（毎晩の見張りの結果の置き場所）
3. データの版の照合（版1のまま合うこと）

## 1. 版1を残す

- 今の `data_generation/output/` の4ファイルと、`dbt_project/warehouse.duckdb` を、リポジトリの外の `~/homelab-snapshots/<日付>-v1/` に写す。写したものの sha256 が元と同じことを示す
- 版1での回帰の試験の結果を取っておく（`docs/analysis/regression/run_numbers.py` の出力を、`docs/analysis/data-v2/before.md` に）

## 2. 作り直す

- V1 の入口で、`data_generation/output/` に作る（承認の画面で承認）
- 新しい `data_generation/output.sha256` を作る
- `dbt_project/` で `dbt build`（承認の画面で承認）。ERROR が 0。WARN の数とその件数（順序矛盾・孤児など）を、版1の数と並べる。見込み：同じ（変えたのは ID・金額・referrer の名前だけ）

## 3. 書く

- `docs/decisions/ADR-010-baseline-data-v2.md`：何を変えたか（V1）、なぜか、版1と版2の指紋、変わった数字と変わらない数字の表（基準値：`revenue_amount`、`subscription_count`、`delivered_count`、`clicked_count`、`opened_count`、`ctr_per_open`。値は SL の道具と SQL の2通りで出して一致したもの）、版1の写しの場所
- ADR-006 の先頭に「<作り直した日> に ADR-010 で版2にした」を1行足す（ほかは変えない）
- CLAUDE.md：環境の落とし穴の `hash()` の行と、守ること6の referrer の行を、ADR-010 の事実に合わせる
- `docs/analysis/data-v2/after.md`：版2での `run_numbers.py` の出力（外れたまま。期待値は直さない）

## 今回の約束

- 回帰の試験の期待値（bank）は変えない（V3 でやる）
- 汚れを仕込むコードは変えない
- 定義のファイルと `docs/business/` に触らない
- 毎晩の `dbt build` の時間（JST 02:50〜03:15）を避ける
- push は `owner/V2` だけ（持ち主の承認の後）

## 止まる条件

- 版1の写しの sha256 が合わないとき
- `dbt build` の ERROR が 0 でないとき、WARN の件数が版1と違うとき（どの検査かを書いて止まる）
- 作った CSV の sha256 が、V1 の一時ディレクトリの結果と違うとき

## 終わったら

`docs/agent/reports/V2.md`（loop.md の「報告の形」）。PR を作る。マージは持ち主がする。
