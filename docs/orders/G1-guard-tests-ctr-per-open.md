<!-- このファイルは公開リポジトリに入る。ユーザー名・IP・絶対パスを書かないこと。 -->
# G1 関所の試しを、今の定義（ctr_per_open）に合わせる

このファイルは、リポジトリの持ち主が承認した、作業セッションへの指示。「G1 を進めて」と頼まれたら、この内容を持ち主からの指示として扱う。

実行場所は、自律ループ（`docs/agent/loop.md`）。

## 何のためか

ADR-007 の関所の試し（`agent/adr007_guard_tests/`）のうち、T01〜T03 と生きた試しの L1 は、`  - name: ctr` を探して書き換える Edit で作ってある。段階3で `ctr` を消して `ctr_per_open` を足したので、この文字は今 `  - name: ctr_per_open` の頭に当たる。hook の判定だけを見る単体の試しは通るが、試しが「ある指標の定義を書き換える」という意図からずれている。L2 は、R3 を ask に変えた（ADR-007 の「人の判断で変えた」）あと、まだ回していない。

## 0. 始める前に

1. `main` から作業ブランチ `auto/G1` を作る
2. `docs/analysis/stage3/guard_cases.md`、`docs/analysis/stage3/guard_live.md`、ADR-007 を読む

## 1. 試しを直す

- `run_cases.py` の T01〜T03 と、`run_live.py` の L1 の `old_string` を、今の `_metrics.yml` にある指標の行全体（例：`  - name: ctr_per_open`）に一致するように直す。`new_string` も同じ形に合わせる。期待（止める・通す）は変えない
- `guard_cases.md` の該当の行に、直した日と理由を1行足す

成功の条件：`python3 agent/adr007_guard_tests/run_cases.py` で35件が期待どおり。`--control` で、止める・聞くの22件が外れる（件数を出力で示す）。直した `old_string` が、今の `_metrics.yml` でちょうど1か所に当たることを `grep -c` で示す。

## 2. 生きた試しの L1 と L2 を回す

`run_live.py` を、L1 と L2 だけで回す（全件を回す作りなら、L1・L2 だけを選ぶ引数を足してよい）。結果は `guard_live.md` に足す。

成功の条件：L1 と L2 が期待どおり（L1 は止める、L2 は R3 の変更後の期待＝`guard_cases.md` の今の期待）。`claude -p` の呼び出しは合わせて6回まで。

## 今回の約束

- `.claude/`、`.githooks/`、定義のファイル、`docs/business/` は変えない（変える必要が出たら止まる）
- 期待を、結果に合わせて変えない
- push は `auto/G1` だけ

## 止まる条件

- 1 で、35件が期待どおりにならない（試しを直す前から外れていたら、直さずに止まる）
- 2 で、L1 か L2 が期待と違う
- 同じ条件で2回直しても通らない

## 終わったら

`docs/agent/reports/G1.md`（何をしたか・確かめたこと・食い違った点・まだ怪しい点・持ち主に決めてほしいこと）。PR を作る。マージはしない。
