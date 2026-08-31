# ADR-004: latest snapshot のフィルタを semantic_model 側に常時適用する

- Status: Accepted
- Date: 2026-08-31

## 背景

ADR-001 の決定により、`fct_revenue` は同一の
`account_id × revenue_month` に対して複数のスナップショット行を持つ。
`SUM(revenue_amount)` を素朴に書くと多重計上する。

確定値を得るには `is_latest_snapshot = true` でのフィルタが必要だが、
このフィルタをどの層に置くかを決める必要がある。

## 選択肢

**A. semantic_model の measure 定義に埋め込む（常時適用）。**
`expr` に `case when is_latest_snapshot then revenue_amount else 0 end` を書く。
セマンティックレイヤー経由のどのクエリも、このフィルタを迂回できない。

**B. metric ごとに指定する。**
`revenue_confirmed` と `revenue_all_snapshots` を別メトリクスとして定義する。
柔軟だが、新しいメトリクスを追加する人がフィルタを書き忘れる余地が残る。

**C. mart にフィルタ済みモデルを追加する。**
`fct_revenue_confirmed` を作り、それを semantic_model の対象にする。

## 決定

**A を採用する。** `snapshot_date` は dimension として公開しない。

## 理由

セマンティックレイヤーの目的は曖昧性の排除である。B は柔軟性の名の下に、
そもそも潰そうとしていた問題（人によって計算が異なる）を温存する。
「正しく書けば正しい答えが出る」仕組みは、「間違えようがない」仕組みに劣る。

C は mart にモデルを増やす。集計もフィルタもしない thin mart の方針に反する。
また同じ実体に対して2つのテーブルが存在する状態は、それ自体が定義の分岐点になる。

## 帰結

- スナップショット履歴を使った分析（初回見積もりと確定値の乖離など）は、
  セマンティックレイヤー経由ではできない。必要になった時点で
  専用の semantic_model を別に立てる。「確定売上」と「見積もり推移」は
  そもそも異なる意味を持つ指標であり、1つのモデルに両方の役割を持たせる方が濁っている。
- `SUM` に `case when` を埋め込む形になるため、`agg: sum` の対象が
  素の金額カラムではなくなる。measure の description に明記した。
- この決定により多重計上は構造的に不可能になったが、
  同じテーブルにある別の問題（通貨混在）は防げていない。ADR-005 を参照。
