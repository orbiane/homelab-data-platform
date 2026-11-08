<!-- このファイルは公開リポジトリに入る。ユーザー名・IP・絶対パスを書かないこと。 -->
# NEXT：このリポジトリでやること（持ち主が承認した作業の一覧）

このファイルは、持ち主が承認した作業の一覧で、自律ループ（[ADR-008](docs/decisions/ADR-008-autonomous-loop.md)）の入口。ループは毎回ここを読み、[docs/agent/loop.md](docs/agent/loop.md) の手順で、上から1件だけ進める。

- 作業の中身は、各行の「指示書」にある。指示書が無い行は、この表の「終わりの条件」が指示になる
- この表を書き換えてよいのは、持ち主と、持ち主の承認を受けたチャットのセッション。ループが書き換えてよいのは、自分が進めた行の「状態」と「PR」の欄だけ（作業の PR の中で）
- マージが持ち主の承認になる。ループはマージしない

## 状態の意味

| 状態 | 意味 | 誰が動く |
|---|---|---|
| `ready` | ループが着手してよい（依存がすべて `done`） | ループ |
| `attended` | 持ち主が見ている Claude Code のセッションでやる（承認の画面が要る） | 持ち主が1行を送る |
| `owner` | 持ち主が決める。決まったらチャットが表と ADR を直す | 持ち主 |
| `in-pr` | PR が開いている。持ち主のマージ待ち（表には書かない。GitHub の PR の状態で決まる） | 持ち主 |
| `done` | main に入った（作業の PR が、この欄を `done` にする。マージで main に入る） | — |
| `blocked` | 止まる条件に当たった。報告に理由がある | 持ち主 |

## 作業の一覧（上から順に優先）

| ID | 作業 | 状態 | 依存 | 指示書 | PR |
|---|---|---|---|---|---|
| L0 | 自律ループを据え付ける（権限の表、作業ブランチだけに push、main の保護、定時の起動） | `attended` | — | [L0](docs/orders/L0-loop-setup.md) | |
| R1 | 回帰の試験 第1段：13問の数字と、文書の指標の名前 | `ready` | L0 | [R1](docs/orders/R1-regression-numbers-docs.md) | |
| G1 | 関所の試しを、今の定義（ctr_per_open）に合わせる | `ready` | L0 | [G1](docs/orders/G1-guard-tests-ctr-per-open.md) | |
| R2 | 回帰の試験 第2段：過去の間違いの検出器を作り、段階2の78本の人の判定と突き合わせる | `ready` | R1 | [R2](docs/orders/R2-regression-detectors.md) | |
| S3 | 段階3のまとめの文書（腐らせる→見つける→直す→確かめる） | `ready` | R1, G1 | [S3](docs/orders/S3-governance-design.md) | |
| R3a | 回帰の試験 第3段の条件を書く（本物のエージェントで解き直す。回す前の承認） | `ready` | R2 | [R3](docs/orders/R3-regression-live.md) | |
| R3b | 回帰の試験 第3段を回す（R3a のマージが、条件の承認） | `ready` | R3a | [R3](docs/orders/R3-regression-live.md) | |
| W1 | 毎晩の見張りの案を出す（回帰の試験の数字の層を、毎晩の dbt build のあとに回す） | `ready` | R1 | [W1](docs/orders/W1-nightly-watch-proposal.md) | |
| M1 | CLAUDE.md の「IP アドレスをコミットしない」を、家の LAN と Tailscale の IP に絞る（hook が見ている範囲と合わせる） | `ready` | L0 | 下の「小さな作業」 | |
| M2 | `docs/analysis/sl-vs-t2s-comparison.md` のタイトルの「（下書き）」を外す | `ready` | L0 | 下の「小さな作業」 | |
| M3 | README.md の Reproduce の「seeded, deterministic」を、ADR-006 の事実（`hash()` と uuid4 のため、作り直すと同じ CSV にならない）に合わせる | `ready` | R1 | 下の「小さな作業」 | |
| Q1 | 回帰の試験の正解（期待値）を、エージェントが書き換えてよいか | `owner` | R1 | [R1 の8](docs/orders/R1-regression-numbers-docs.md) | |
| Q2 | D1「開封率は？」の正解（opened_count が指標になった後） | `owner` | R1 | [R1 の8](docs/orders/R1-regression-numbers-docs.md) | |
| Q3 | `query_metrics` の where の穴（自由な SQL が DuckDB に届く）を、塞ぐか見張るか | `owner` | — | [agent/sl_mcp/README.md](agent/sl_mcp/README.md) | |
| Q4 | 次に入れる腐敗（スキーマの変更／再処理・二重ロード／generator の `hash()`・uuid4 の修正／referrer のブランド名）。どれもデータを作り直すので、持ち主が決める（CLAUDE.md 守ること7） | `owner` | S3 | — | |

### 依存の読み方

- 依存の ID がすべて `done` のときだけ着手できる。`attended` と `owner` の行は、ループは着手しない
- R3b は、R3a の PR がマージされて `done` になってから

## 小さな作業（指示書なし）

### M1

- やること：CLAUDE.md の守ること5の1行目の「IP・MAC アドレス」を、`.githooks/scan.sh` が実際に見ている範囲（家の LAN の 192.168.x.x、Tailscale の 100.64〜100.127、MAC アドレス）に合わせて書き直す。`127.0.0.1` のような、この機械自身を指す番号は対象外だと分かるようにする
- 終わりの条件：変わったのが CLAUDE.md の守ること5の行だけ（`git diff --stat` で1ファイル）。`.githooks/` は変えない
- 理由：今の書き方では `127.0.0.1` でも毎回止まって聞かれる

### M2

- やること：タイトルの「（下書き）」を外す。本文は変えない
- 終わりの条件：`git diff` が1行の変更だけ

### M3

- やること：README.md の Reproduce の節で、generator を「seeded, deterministic」と書いている所を、ADR-006 の事実（`revenue_monthly.py` の `hash()` と、`subscription.py`・`message_event.py` の uuid4 のため、作り直すと同じ CSV にならない。基準データは作り直さず `output.sha256` で照合する）に合わせる。英語のまま書く
- 終わりの条件：変わったのが README.md の Reproduce の節だけ。ADR-006 の該当の節の行番号を報告に添える
- 理由：R1 の文書の層は指標の名前しか見ない。説明文の古さは、名前を見る検査では捕まらない（2026-11-08 にチャットが見つけた）

## 済んだ作業

（`done` になった行は、チャットがここに移す。ID・PR・マージした日）
