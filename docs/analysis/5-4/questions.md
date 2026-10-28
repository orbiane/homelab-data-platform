# 5-4 質問セット：セマンティックレイヤー vs Text-to-SQL

- 基準データ：`data_generation/output.sha256` と一致する CSV 4本（ADR-006）。作成時に 4本とも OK を確認
- 正解の値はすべて **下書き（未確定）**。確定は人間が行う
- 参考値のクエリ：[reference_queries.sql](reference_queries.sql)（mart だけを読む）
- 「SL の上限」は、人（Claude）が書いた `mf query` の結果。SL を正しく使ったときに取れる最良の答え
- `mf query` は `dbt_project/` で実行。dbt-metricflow 0.14.0

## 評価の決めごと（承認済み）

1. SL の側も、T2S と同じ LLM に答えさせる。LLM には SL の語彙（メトリクスとディメンションの一覧と説明）だけを渡し、`mf query` を書かせる。人（または Claude）が書いた `mf query` の結果は、「SL を正しく使ったときの上限」として別に記録する
2. 採点は2つの軸に分ける。軸1「数字は正しいか」。軸2「定義の外や意味のない数字だと分かる答え方をしたか（指摘する、断る、聞き返す）」。D 型で SL が断ったら、軸1 は「答えなし」、軸2 は○とする
3. 「確定した売上」は、`is_finalized = true` の月の、最新 snapshot の値とする
4. T2S に見せるスキーマは、まず mart だけ。raw は時間が余れば足す
5. 正解は「合意済みの定義どおりの値」。ただし、通貨の合算のように定義そのものが意味をなさない場合は、指摘するか通貨別に答えるのを正解とする。データの期間の外は「データがない」が正解

## 型
- **A 対照**：罠のない質問
- **B SL が防ぐ罠**：定義に書ける罠（多重計上、数え方、孤児）
- **C SL でも防げない罠**：定義に書けない意味の問題（通貨、未締め）
- **D 定義の外**：SL の語彙にないことを聞く

| ID | 型 | 質問 |
|---|---|---|
| A1 | A | メッセージの種類ごとのクリック数を出して |
| A3 | A | 流入経路ごとの登録数は？ |
| B2 | B | 配信数は全部でいくつ？ |
| B3 | B | クリック率はどのくらい？ |
| B4 | B | 業種ごとの配信数 |
| B5 | B | 2月の確定した売上（円）はいくら？ |
| C1 | C | 売上の合計はいくら？ |
| C2 | C | 契約プラン別に売上を比べたい |
| C3 | C | 4月の確定した売上（円）はいくら？ |
| D1 | D | 開封率は？ |
| D2 | D | 登録した人は何人？（重複なし） |
| D5 | D | 売上の最初の見積もりと確定値は、どれくらい違った？ |
| D6 | D | 今月の売上は？ |

---

## A1「メッセージの種類ごとのクリック数を出して」
- **型**：A 対照
- **試す罠**：なし
- **SL の想定**：答えられる（`clicked_count` × `message_type`）
- **T2S がやりがち**：ほぼ正解のはず。不正な enum の `CLICK`（29行）を混ぜると少し増える
- **正解の下書き（未確定）**：flex 168 / image 215 / imagemap 272 / text 225 / video 251（計 1,131）
- **SL の上限**：上と一致
  ```
  mf query --metrics clicked_count --group-by message_event__message_type
  ```
- **採点の注意**：`CLICK` を混ぜたら軸1 は×

## A3「流入経路ごとの登録数は？」
- **型**：A 対照（言い方が列名と素直に対応しない）
- **試す罠**：「流入経路」が route（5種）か referrer（16種）か
- **SL の想定**：答えられる（`subscription_count` × `route`）
- **T2S がやりがち**：referrer で16行返す
- **正解の下書き（未確定）**：route 別：qr_code 796 / search 641 / ad 300 / link_share 207 / other 91（計 2,035）
- **SL の上限**：上と一致
  ```
  mf query --metrics subscription_count --group-by subscription_event__route
  ```
  - semantic model 名で `subscription__route` と書くとエラーになる。dimension の接頭辞は primary entity 名の `subscription_event`
- **採点の注意**：⚠ referrer 別も誤りとは言い切れない。referrer で答えて「route でも出せる」と聞き返したら軸2 ○

## B2「配信数は全部でいくつ？」
- **型**：B SL が防ぐ罠（言い方が列名と素直に対応しない）
- **試す罠**：縦持ち（1配信 × 1人 × 1イベント種別で1行）の数え方
- **SL の想定**：答えられる（`delivered_count` ＝ event_type が delivered の行数）
- **T2S がやりがち**：全行数 13,871 / 配信本数（message_id の数）120 / 売上テーブルの請求ベースの配信数 166,215（最新 snapshot だけなら 92,788）
- **正解の下書き（未確定）**：8,428（完全重複 82行を含む。定義どおり）
- **SL の上限**：8,428
  ```
  mf query --metrics delivered_count
  ```
- **採点の注意**：重複を除いた 8,346 は定義と違うので軸1 ×。「配信本数なら 120」と併記するのは可

## B3「クリック率はどのくらい？」
- **型**：B SL が防ぐ罠
- **試す罠**：分母と分子の選び方
- **SL の想定**：答えられる（`ctr` ＝ clicked_count ÷ delivered_count）
- **T2S がやりがち**：クリック ÷ 全行 0.081537 / 不正 enum 込み 0.137262 / 重複除去 0.135514
- **正解の下書き（未確定）**：0.134196（約 13.4%）
- **SL の上限**：0.134196
  ```
  mf query --metrics ctr --decimals 6
  ```
- **採点の注意**：丸めは小数第3位（13.4%）まで一致すれば軸1 ○とするか、人間が決める

## B4「業種ごとの配信数」
- **型**：B SL が防ぐ罠
- **試す罠**：孤児（dim_account に無い account_id）。内部結合で落ちる
- **SL の想定**：答えられる（左結合なので業種が空の行に残る）
- **T2S がやりがち**：内部結合で孤児 119件を落とす（業種が空 2,446）。または業種が空の行ごと捨てる
- **正解の下書き（未確定）**：業種が空 2,565 / entertainment 1,481 / healthcare 1,463 / real_estate 867 / education 745 / food_and_beverage 588 / retail 492 / beauty 227（計 8,428）
  - 業種が空の 2,565 は、2つの別物の混合：**業種が空の2アカウント（acct_000001, acct_000017）の配信 2,446** と **孤児の配信 119**
- **SL の上限**：上と一致。業種が空の行は、表では空欄（`NULL` と表示されない）
  ```
  mf query --metrics delivered_count --group-by account__industry
  ```
- **採点の注意**：業種が空の行を落としたら軸1 ×。空の行の中身（業種不明と孤児の混合）に触れたら軸2 ○

## B5「2月の確定した売上（円）はいくら？」
- **型**：B SL が防ぐ罠（言い方が列名と素直に対応しない）
- **試す罠**：snapshot の多重計上。2月は確定済みで、両方の snapshot が is_finalized = true なので、「確定」で絞っても多重計上が残る
- **SL の想定**：答えられる（measure に最新 snapshot 限定が埋め込み）
- **T2S がやりがち**：is_finalized = true で絞って全 snapshot を足し 10,448,341
- **正解の下書き（未確定）**：5,476,600（孤児1行 120,000 を含む。孤児を除くと 5,356,600）
- **SL の上限**：JPY 5,476,600（is_finalized = True）
  ```
  mf query --metrics revenue_amount --group-by revenue_record__currency,revenue_record__is_finalized --where "{{ TimeDimension('metric_time', 'month') }} = '2026-02-01'"
  ```
- **採点の注意**：内部結合で 5,356,600 を返したら、孤児の扱いが定義と違うので軸1 ×

## C1「売上の合計はいくら？」
- **型**：C SL でも防げない罠
- **試す罠**：通貨の混在（JPY と USD を無変換で足す）
- **SL の想定**：答えられるが罠を防げない（警告なしで混在合計を返す）
- **T2S がやりがち**：全 snapshot を足して 87,395,105。または混在合計 49,621,900
- **正解の下書き（未確定）**：「混在合計は意味がない」と指摘する、または通貨別：JPY 45,440,100 / USD 4,181,800
- **SL の上限**：通貨別に分ければ JPY 45,440,100 / USD 4,181,800。分けずに聞くと 49,621,900 が警告なしで返る
  ```
  mf query --metrics revenue_amount --group-by revenue_record__currency
  mf query --metrics revenue_amount        # 49621900
  ```
- **採点の注意**：49,621,900 だけを返したら軸1 ×・軸2 ×。メトリクスの説明に通貨混在の注意があるので、LLM が説明を読んだかが軸2 に出る

## C2「契約プラン別に売上を比べたい」
- **型**：C SL でも防げない罠（言い方が列名と素直に対応しない）
- **試す罠**：通貨の混在。USD の2アカウントは free と light にいる
- **SL の想定**：答えられるが罠を防げない
- **T2S がやりがち**：混在合計に加えて多重計上（free 16,229,281 / light 9,628,192 / standard 61,417,632）
- **正解の下書き（未確定）**：通貨別：free JPY 6,640,400・USD 2,448,200 / light JPY 3,733,000・USD 1,733,600 / standard JPY 34,946,700 / プランが空（孤児）JPY 120,000
- **SL の上限**：上と一致（通貨でも分けた場合）。分けないと free 9,088,600 / light 5,466,600 / standard 34,946,700 / 空 120,000
  ```
  mf query --metrics revenue_amount --group-by account__plan_type,revenue_record__currency
  ```
- **採点の注意**：プランが空の 120,000 を落としたかは、軸1 では問わない（主題は通貨）。⚠ 人間が決める

## C3「4月の確定した売上（円）はいくら？」
- **型**：C SL でも防げない罠
- **試す罠**：未締め。4月は is_finalized = false で、snapshot は1版だけ
- **SL の想定**：答えられるが「未確定」とは言わない
- **T2S がやりがち**：is_finalized を見ずに 7,958,500 を「確定」として返す
- **正解の下書き（未確定）**：「4月はまだ確定していない（暫定値は 7,958,500）」
- **SL の上限**：
  - 確定で絞らない：JPY 7,958,500（is_finalized = False と一緒に表示される）
  - is_finalized = true で絞る：`Query returned an empty result set`（エラーではない。終了コード 0）
  ```
  mf query --metrics revenue_amount --group-by revenue_record__currency,revenue_record__is_finalized --where "{{ TimeDimension('metric_time', 'month') }} = '2026-04-01'"
  ```
- **採点の注意**：空の結果を「売上 0」と答えたら軸1 ×。7,958,500 だけを「確定」として返したら軸1 ×・軸2 ×

## D1「開封率は？」
- **型**：D 定義の外
- **試す罠**：`opened_count` は measure としてはあるが、metric になっていない
- **SL の想定**：答えられない
- **T2S がやりがち**：0.455 を返す（不正 enum の `open` 込みなら 0.4576）
- **正解の下書き（未確定）**：SL は「定義にない」と断るのが正解。T2S の値は軸1 で 0.455 を正とする
- **mf の止まり方**：`mf query` に measure を直接聞くオプションは無い（`--metrics` だけ）。
  ```
  mf query --metrics opened_count
  ERROR: Got error(s) during query resolution.
    The given input does not exactly match any known metrics.
    Suggestions:
      ['delivered_count', 'clicked_count', 'revenue_amount', 'subscription_count', 'ctr']
  ```
- **採点の注意**：SL 側の LLM が ctr を「開封率」として返したら軸1 ×・軸2 ×

## D2「登録した人は何人？（重複なし）」
- **型**：D 定義の外
- **試す罠**：人数（contact の重複を除いた数）の measure が無い。`subscription_count` はイベント数
- **SL の想定**：答えられない。ただし LLM が `subscription_count` 2,035 を人数として返す危険がある
- **T2S がやりがち**：2,000（正しく数える）か 2,035
- **正解の下書き（未確定）**：2,000 人。イベント 2,035 との差 35 は、再登録 30件と異常な日付の複製 5件
- **mf の止まり方**：人数の metric も contact の dimension も無い
  ```
  mf query --metrics subscription_count --group-by subscription_event__contact_id
  ERROR: The given input does not match any of the available group-by-items
    for SimpleMetric('subscription_count').
    Suggestions: ['subscription_event__account', 'subscription_event__dt__day',
      'subscription_event__route', 'subscription_event', 'subscription_event__referrer', 'account__status']
  ```
- **採点の注意**：SL 側が 2,035 を返したら軸1 ×・軸2 ×（「SL も止まらない」反例として記録）

## D5「売上の最初の見積もりと確定値は、どれくらい違った？」
- **型**：D 定義の外
- **試す罠**：snapshot_date を dimension として公開していない（ADR-004 で意図的）
- **SL の想定**：答えられない
- **T2S がやりがち**：正しく答えられる可能性がある（SL が負ける側の対照）。最初の snapshot の取り方を間違えることはありうる
- **正解の下書き（未確定）**：円、2版ある 76 組：
  - 2025-11：8,249,016 → 8,887,700（+638,684）
  - 2025-12：7,712,884 → 8,307,800（+594,916）
  - 2026-01：7,376,621 → 7,951,800（+575,179）
  - 2026-02：4,971,741 → 5,356,600（+384,859）
  - 2026-03：6,318,475 → 6,857,700（+539,225）
  - 2026-04 は1版だけ（未締め）
- **mf の止まり方**：
  ```
  mf query --metrics revenue_amount --group-by revenue_record__snapshot_date
  ERROR: The given input does not match any of the available group-by-items
    for SimpleMetric('revenue_amount').
    Suggestions: ['revenue_record__account', 'revenue_record__is_finalized',
      'revenue_record__revenue_month__month', 'revenue_record__currency', 'account__status', 'account__plan_type']
  ```
- **採点の注意**：USD を混ぜたら軸1 ×。T2S が通貨を分けて正しく答えたら、SL に勝った問題として記録

## D6「今月の売上は？」
- **型**：D 定義の外（データの期間の外）
- **試す罠**：「今月」（2026-10）のデータは無い。データは 2026-04 まで
- **SL の想定**：空の結果を返す
- **T2S がやりがち**：最新月の4月を「今月」とみなして 8,809,500（通貨混在）を返す
- **正解の下書き（未確定）**：「データがない（売上は 2026-04 まで）」
- **mf の止まり方**：エラーではなく空の結果（終了コード 0）
  ```
  mf query --metrics revenue_amount --group-by revenue_record__currency --where "{{ TimeDimension('metric_time', 'month') }} = '2026-10-01'"
  🕳 Query returned an empty result set
  ```
- **採点の注意**：空の結果を「0円」と答えたら軸1 ×。T2S の答えでは、「今月」をどの月と解釈したかを記録する

---

## SL の想定と mf の実際の動きの食い違い

| ID | 想定 | 実際 |
|---|---|---|
| A3 | 答えられる | 答えられる。ただし dimension の接頭辞は `subscription_event__`（primary entity 名）で、semantic model 名の `subscription__` はエラーになる。LLM が語彙一覧を正しく写さないと止まる |
| B4 | 答えられる（業種が空の行が NULL で残る） | 答えられる。ただし業種が空の行は、表で空欄になり `NULL` と表示されない。LLM が空欄の行を読み落とす余地がある |
| C3 | 答えられるが「未確定」と言わない | 想定どおり。ただし is_finalized = true で絞ると、エラーではなく空の結果になる。D6（期間の外）と見分けがつかない |
| D6 | 空の結果を返す | 想定どおり。エラーではなく終了コード 0 なので、「断った」のか「0件」なのかを LLM が区別できるかが問題になる |

D1・D2・D5 は想定どおりエラーで止まった。D1 は、`mf` に measure を直接聞く手段が無いことも確かめた。
