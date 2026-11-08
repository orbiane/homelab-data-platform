<!-- このファイルは公開リポジトリに入る。ユーザー名・IP・絶対パスを書かないこと。 -->
# R1 回帰の試験 第1段：13問の数字と、文書の指標の名前

このファイルは、リポジトリの持ち主が承認した、作業セッションへの指示。「R1 を進めて」と頼まれたら、この内容を持ち主からの指示として扱う。

実行場所は、自律ループ（`docs/agent/loop.md`）。持ち主の見ているセッションで進めてもよい。理由：warehouse と `mf` は持ち主の機械にしか無い。

## 何のためか

決めた数字（13問の正解）を、定義や文書を変えるたびに解き直して、前に合っていたものが崩れていないかを見る試験（回帰の試験）を作る。ADR-007 の関所は「決定メモのパスがあるか」という形しか見ない（ADR-007 の H1）。この試験は中身（数字）を見る。

第1段では、エージェント（`claude -p`）は回さない。作るのは2つの層：
- 数字の層：13問の正解を、SL の道具（`query_metrics`）と SQL（`run_sql`）の2通りで出し直し、期待値と比べる
- 文書の層：今を説明する文書に、もう定義に無い指標の名前が残っていないかを見る

試験が外れることを先に確かめる。まず「段階2の時点の正解」で作って回し（段階3で `ctr` を消したので外れるはず）、そのあと決定メモに沿って正解を直し、もう一度回す。

## 0. 始める前に

1. `main` から作業ブランチ `auto/R1` を作る（持ち主の見ているセッションなら `owner/R1`）
2. `CLAUDE.md`、`docs/analysis/5-4/questions.md`、`docs/decisions/ADR-006-generated-data-version.md`、`docs/decisions/ADR-007-definition-change-guard.md`、`docs/business/2026-11-06-ctr-opened.md` を読む
3. データの版の照合（`cd data_generation/output && shasum -a 256 -c ../output.sha256`）。manifest（`dbt_project/target/semantic_manifest.json`）に `ctr_per_open` と `opened_count` があるか確かめる。無ければ止まる（`dbt parse`・`dbt build` は回さない）

## 1. 作るもの（`docs/analysis/regression/`）

1. `bank.tsv`（形は任せる。JSON Lines でもよい）：13問（questions.md の A1・A3・B2・B3・B4・B5・C1・C2・C3・D1・D2・D5・D6）を1問ずつ。欄：
   - 問の ID、問の文
   - SL の呼び出し：`query_metrics` の引数（questions.md の「SL の上限」の `mf query` を欄に直したもの）。SL が断るのが正解の問（D1・D2・D5）は、期待する kind。C3 は2つの呼び出し（確定で絞る／絞らない）
   - SQL：`docs/analysis/5-4/answer_queries.sql` の該当のブロック。1問ずつ動く形に写してよい（先頭の temp view を CTE にする、など）。数え方は変えない。写して変えた所を README に書く
   - 期待値と、許す幅（questions.md の決めごと6から取る）
   - 期待値の出どころ（questions.md の節、または決定メモのパス）と、決めた日
   - 状態：有効／未決（未決は理由を書く）
   - 知られた間違い：その問で過去に出た×と印。`docs/analysis/5-4/run_002/scores.md` と `docs/analysis/stage2/run_001/final_scores.tsv` から写す（記録の本の名前、札・印・規則）。自分で新しく判定しない
2. `run_numbers.py`：bank の各問で、(a) `agent/sl_mcp/server.py` の `query_metrics` を import して呼ぶ（`agent/sl_mcp/check.py` と同じ形。`mf` を直接呼ばない） (b) SQL を server の `run_sql` で流す。(a)(b) を別々に期待値と比べ、問ごとに「合う／外れる／未決」を出す。最後に件数（調べた問・合う・外れる・未決）を出す。外れが1件以上なら終了コード 1
3. `check_docs.py`：過去に `_metrics.yml` にあった指標の名前を git の履歴から集め、今の manifest に無い名前（廃止した名前）が、今を説明する文書に単語として出てくるかを見る
   - 今を説明する文書：`README.md`（リポジトリ直下）、`CLAUDE.md`、`agent/sl_mcp/README.md`、`docs/decisions/ADR-006-generated-data-version.md` の「基準値」の節。ほかの ADR と `docs/analysis/` の下は過去の記録なので見ない
   - 同じ行に、その名前を廃止した決定メモのパス（`docs/business/...`）がある行は、履歴の記述として外れに数えない（数えなかった行も一覧に出す）
   - 出すもの：集めた過去の名前・今の名前・廃止した名前、調べた文書と行の数、外れの一覧。外れが1件以上なら終了コード 1
4. `README.md`（このフォルダ）：何を試すか、回し方、期待値の変え方（道具の出力に合わせて変えない。変えるときは決定メモのパスと、2通りで出した値を書く）、この試験で言えないこと（正解の値・SL の呼び出し・SQL はどれも Claude が書いた。人が承認したのは questions.md の値）
5. `results/<日付>.md`：下の 2 と 6 の出力

## 2. 1回目（段階2の時点の正解で）

bank を「段階2の時点の正解」（questions.md の値のまま）で作り、`run_numbers.py` と `check_docs.py` を回す。見込み：

- 外れるのは B3 の (a)（`ctr` が無い）と D1 の (a)（`opened_count` が指標になったので、断るはずの呼び出しが通る）だけ。B3・D1 の (b) と、ほかの11問の (a)(b) は合う
- 文書の外れは3か所：`README.md` の2か所（`mf query` の例と Metrics の表）、ADR-006 の基準値の表の `ctr` の行

見込みと違ったら、直さずに止まって報告する。

成功の条件 E1：1回目が見込みどおり（問ごとの (a)(b) の表と、文書の外れの一覧で示す）。ここで一度コミットして push する（bank は段階2の時点、道具、README、1回目の結果）。

## 3. B3 の期待値を決定メモに合わせる

決定メモ `docs/business/2026-11-06-ctr-opened.md` の数え方に変える。値は2通りで出す：(a) `query_metrics` の `ctr_per_open`、(b) `run_sql` で、メモの数え方（分母は event_type が opened の行だけ）で新しく書いた SQL。小数6桁で一致したときだけ期待値にする。出どころに、メモのパスと2つの値を書く。B3 の SQL は新しく書いたものに替える（`answer_queries.sql` は変えない）。

成功の条件 E3（前半）：(a)(b) が小数6桁で一致することを、出力で示す。

## 4. D1 は未決にする

D1 は期待値を変えず、状態を「未決」にする。理由は「`opened_count` が指標になった。`opened_count` ÷ `delivered_count` を SL の答えとして認めるかは、持ち主が決める（NEXT.md の Q2）」。`run_numbers.py` は、未決を外れに入れず、消さずに数える。

## 5. 文書を直す

- `README.md`（リポジトリ直下）：`mf query` の例を `ctr_per_open` に、Metrics の表を今の定義（`opened_count`、`ctr_per_open` = clicked / opened）に合わせる
- ADR-006 の基準値の表：今ある値は変えない。`ctr` の行の後ろに、廃止の日付と決定メモのパスを足す。`opened_count` と `ctr_per_open` の行を足す（値は (a)(b) の2通りで出して一致したもの）

成功の条件 E3（後半）：ADR-006 に足した2行の値が、それぞれ (a)(b) で一致。

## 6. 2回目

もう一度回し、結果に足す。

成功の条件 E2：13問のうち合う12（(a)(b) とも）・未決1（D1）・外れる0。`check_docs.py` の外れ0件（調べた文書と行の数も出す）。

## 7. コミットの分け方と確かめ

- コミット1：bank（段階2の時点）・道具・README・1回目の結果（2 で済み）
- コミット2：bank の B3・D1 の変更と、2回目の結果
- コミット3：`README.md` と ADR-006
- 成功の条件 E4：変わったファイルが、`docs/analysis/regression/` の下、`README.md`、ADR-006、`NEXT.md`（R1 の行の状態と PR の欄だけ）、`docs/agent/reports/R1.md` だけ（`git diff --stat main...HEAD` で示す）
- 成功の条件 E5：個人情報の検査（git の hook）が、どのコミットでも通る

## 8. 持ち主に決めてほしいこと（報告に必ず書く）

- Q1：今回は、この指示書の承認の範囲で、B3 の期待値をエージェントが書き換えた。今後、試験の正解（期待値）を、エージェントが書き換えてよいか。チャットの推す案は「書き換えは ADR-007 の守る場所に入れる（決定メモが要る・毎回聞く）」。理由：エージェントが正解を書き換えられると、試験に通すために正解を変える近道ができる
- Q2：D1 の正解

## 今回の約束

- 期待値を、道具の出力に合わせて書き換えない。変えてよいのは 3 の B3 だけ。外れた問は外れたまま記録する
- 許す幅を広げない
- 変えないもの：定義のファイル、`.claude/`、`.githooks/`、`agent/`、`docs/business/`、`docs/analysis/5-4/`（`answer_queries.sql`・`questions.md`・scores を含む）、`docs/analysis/stage2/`
- Bash で `mf`・`duckdb` を直接打たない（server を import する）。warehouse に書かない
- push は作業ブランチだけ。区切りごとに push する

## 止まる条件

- 見込みの外の外れ・合い（E1 の外）。データの版の照合が合わない。manifest に新しい指標が無い。maintenance が返る
- 同じ条件で2回直しても通らない
- 範囲の外で見つけたもの（ほかの古い文書など）は、直さずに報告の一覧へ（探し方と件数つき）

## 終わったら

`docs/agent/reports/R1.md` に、E1〜E5 ごとに実行したコマンドと出力、食い違った点、まだ怪しい点、8 の2つ。PR を作る。マージはしない。
