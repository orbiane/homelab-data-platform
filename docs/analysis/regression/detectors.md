<!-- このファイルは公開リポジトリに入る。ユーザー名・IP・絶対パスを書かないこと。 -->
# 回帰の試験 第2段：過去の間違いの検出器（R2）

答えの数字ではなく、道具の呼び出し（`run_sql` の SQL、`query_metrics` の引数、5-4 の `mf query` の文字）から、知られた間違いを見つける検出器を作った。人が確定した判定（段階2 の `final_scores.tsv`、5-4 の `scores.md`）を物差しにして、どこまで当たるかを測った。指示書は `docs/orders/R2-regression-detectors.md`。

- 検出器：[detectors.py](detectors.py)（1つの間違いに1つの関数）。自己試験：[test_detectors.py](test_detectors.py)（手で書いた例 41 件。記録は使わない）
- 当てる台本：[apply_detectors.py](apply_detectors.py)（`stage2` か `54`。`--version v1〜v4` で前の版の数を出し直せる。2026-11-14 に `--version v1`・`v3` が、コミット済みの v1・v3 の結果と同じ数になることを確かめた。`R2_stage2_v1_rerun.md` は、作り替える前の切り替え `--v1` で作ったもの）
- 5-4 の人の判定の写し：[human_54.tsv](human_54.tsv)（台本が 5-4 の scores.md と 157 件突き合わせ、合わない所 0）
- 結果：`results/R2_stage2_v1.md`〜`v4.md`、`results/R2_54_v3.md`・`v4.md`（本ごとの表と、当たった根拠）

回し方（リポジトリの直下で。warehouse は読まない）：

```
uv run python docs/analysis/regression/test_detectors.py
uv run python docs/analysis/regression/apply_detectors.py stage2 [--version v1|v2|v3|v4] [--out results/<名前>.md]
uv run python docs/analysis/regression/apply_detectors.py 54 [--out results/<名前>.md]
```

## 作り方

1. **最初の版は、記録の `calls` の中身を見る前に書き、コミットした**（`2c7d758`）。材料は、questions.md の原因の札と各問の「やりがち」、final_scores.tsv の tags・mark・note、段階2 と 5-4 の scores.md の規則と印の節。列の名前は 5-4 の `context_t2s_desc.txt` と staging の SQL で、記録の形はハーネスのコードで確かめた
2. 段階2 の78本に当て（作りの段）、v2〜v4 で直した。直すたびにコミットし、前の版の数も残した（下の「版の移り」）
3. 固めた版（v4）を 5-4 の117本に当てた（試しの段）。**ここでは直していない**

## 検出器の一覧（v4）

| 検出器 | 当てる問 | 当たる形 | SL の呼び出し | 対応づける人の札・印の言葉 |
|---|---|---|---|---|
| `year_less_month` 年を見ずに月で絞る | B5・C3・D6 | WHERE・HAVING に `month(…)`・`extract(month …)` があり、同じ述語に年（日付の文字、`year()`、4桁の年、between など）が無い | where を見る（TimeDimension に日付を書くので、ふつうは当たらない） | 年、年を見ず |
| `quality_flag` 品質フラグ | A1・A3・B2・B3・D1 | WHERE・HAVING に `is_valid_*`（v2 から。FILTER・CASE で分けて数えるのは当てない） | where を見る | 品質フラグ |
| `unfinalized_excluded` 未確定の月を外す | C1・C2・D6 | WHERE に `is_finalized`。v3 から、`case when is_finalized then 金額`・`filter (where is_finalized)` の確定だけを足す列も | where を見る | 確定の月だけ、is_finalized |
| `orphan_dropped` 孤児を落とす | B4・B5・C2 | dim_account と内部結合、dim_account を左にした left join、`in (select … dim_account)`、結合した側の `is not null` | 判定できない（定義が左結合） | 孤児 |
| `snapshot_all` snapshot を全部足す | B5・C1・C2 | 売上を足すのに、最新の版に絞る仕組み（is_latest_snapshot、max(snapshot_date)、row_number など）が無い | 判定できない（定義が最新の版） | snapshot |
| `currency_mixed` 通貨を混ぜる | C1・C2・D5・D6 | 売上を足すのに、`currency` がクエリのどこにも無い | revenue_amount を聞いて、group_by にも where にも currency が無い | 通貨 |
| `d5_final_only` 確定値にだけある行を差に入れる | D5 | snapshot_date を見て売上を足すのに、2版ある組に絞る条件（版の数 = 2・> 1、版どうしの日付を比べる結合）が無い | 判定できない | 確定値にだけある行、版の取り方 |
| `empty_as_zero` 空の結果を 0 と読む | C3・D6 | 答えの文に「0 円」「売上は 0」「売上が無かった」、0 を別の読み方と並べる | 答えの文を見る | 空の結果 |
| `enum_mixed` 不正な・存在しない event_type | A1・B2・B3・D1 | クエリのどこかに `lower(event_type)`・ilike、または正規の5値以外の値との比較 | 判定できない | enum、存在しない値、LOWER |
| `dedupe` 定義の含める重複を除く | B2・B3 | 配信の表で `select distinct`・`count(distinct …)` | 判定できない | 重複 |
| `long_format` 縦持ちをそのまま数える | B2・B3・D1 | 配信の表を count し、`event_type` がクエリのどこにも無い | 判定できない | 縦持ち |
| `u_prefix` U をそろえずに数える | D2 | `count(distinct contact_id)` があり、そろえる式（`'U' \|\|`、like 'U%'、replace など）が無い | 判定できない | U プレフィックス |
| `empty_rows_dropped` 業種が空の行を捨てる | B4 | WHERE に `industry is not null`・`industry <> ''` | 判定できない | 空の行 |

- **見る呼び出し**（コミット1で決め、あとで狭めていない）：結果が返った呼び出しだけ。列や表を探すクエリ（information_schema など）と、例の行を見る下調べ（集計の関数が無く limit 20 以下）は見ない。5-4 は最後の試行のクエリだけ（答えはそこから書かれた）。v2 から、run_sql の複数の文は文ごとに分けて見る
- **数字の照合**：5-4 の `auto_score.py` の `judge` をそのまま呼ぶ（期待値は段階2の時点＝questions.md。B3 は 13.4%）。A3 を route 別の数で答えていない本は、referrer の数が warehouse を読まないと分からないので「判定できない」
- **見立て**：数字の照合が×なら×、○で検出器が1つでも当たれば「印」（値は合ったが数え方が違う、の見立て）、○で当たらなければ○
- **検出器ごとの分け方**：一致＝当たって、人も×か印で、札・印の言葉がこの検出器に対応する／誤検出＝当たったが、人は○で印なし／別の札＝当たったが、人の×・印の言葉はこの検出器に対応しない（人が×の理由として書かなかった、もう1つの間違い）／見落とし＝当たらなかったが、人の言葉が対応する／当たらず／判定できない／対象外（当てる問でない）。合計は本の数

## 2. 段階2 の78本（作りの段、v4）

| 検出器 | 一致 | 誤検出 | 別の札 | 見落とし | 当たらず | 判定できない | 対象外 | 計 |
|---|---|---|---|---|---|---|---|---|
| year_less_month | 5 | 0 | 0 | 0 | 13 | 0 | 60 | 78 |
| quality_flag | 2 | 2 | 0 | 0 | 26 | 0 | 48 | 78 |
| unfinalized_excluded | 2 | 0 | 0 | 1 | 15 | 0 | 60 | 78 |
| orphan_dropped | 1 | 1 | 1 | 0 | 7 | 8 | 60 | 78 |
| snapshot_all | 0 | 0 | 0 | 0 | 9 | 9 | 60 | 78 |
| currency_mixed | 0 | 2 | 0 | 0 | 22 | 0 | 54 | 78 |
| d5_final_only | 4 | 2 | 0 | 0 | 0 | 0 | 72 | 78 |
| empty_as_zero | 0 | 0 | 0 | 0 | 12 | 0 | 66 | 78 |
| enum_mixed | 1 | 8 | 0 | 0 | 6 | 9 | 54 | 78 |
| dedupe | 1 | 5 | 0 | 0 | 0 | 6 | 66 | 78 |
| long_format | 0 | 0 | 0 | 0 | 12 | 6 | 60 | 78 |
| u_prefix | 0 | 3 | 0 | 0 | 3 | 0 | 72 | 78 |
| empty_rows_dropped | 0 | 0 | 0 | 0 | 4 | 2 | 72 | 78 |

本の名前：

- 一致：year_less_month＝sql_mcp_B5_r1・r2・r3、sql_mcp_C3_r2・r3／quality_flag＝sl_mcp_D1_r1、sql_mcp_B3_r2／unfinalized_excluded＝sql_mcp_C2_r2・r3／orphan_dropped＝sql_mcp_C2_r1／d5_final_only＝sl_mcp_D5_r1・r2・r3、sql_mcp_D5_r1／enum_mixed・dedupe＝sql_mcp_B3_r2
- 見落とし：unfinalized_excluded＝sql_mcp_C2_r1
- 誤検出：quality_flag＝sql_mcp_A1_r3、sql_mcp_A3_r3／orphan_dropped＝sql_mcp_B4_r2／currency_mixed＝sl_mcp_C2_r1・r3／d5_final_only＝sql_mcp_D5_r2・r3／enum_mixed＝sql_mcp_A1_r1・r2・r3、sql_mcp_B3_r1・r3、sql_mcp_D1_r1・r2・r3／dedupe＝sql_mcp_B2_r1・r2・r3、sql_mcp_B3_r1・r3／u_prefix＝sl_mcp_D2_r1、sql_mcp_D2_r2・r3
- 別の札：orphan_dropped＝sql_mcp_C2_r3（人の札は「その他（確定の月だけ）」で、孤児の行は表に残っている）

### 見立てと人の判定（本ごと）

| 見立て ＼ 人 | ○ | 印 | × | 計 |
|---|---|---|---|---|
| ○ | 33 | 0 | 0 | 33 |
| 印 | 19 | 6 | 3 | 28 |
| × | 12 | 1 | 4 | 17 |
| 計 | 64 | 7 | 7 | 78 |

- **人が×か印の14本**（×7、印7）は、14本とも見立てが×か印になった。人の判定を独立に数えた数（final_scores.tsv の axis1 が×か mark が空でない本）も14本で同じ
- 見立てだけが×か印の本は31本。内訳は、数字の照合の限界で×になった12本（sql_mcp_B4 の3本は業種が空の行を分けた表で規則B の○、C3・D6 の9本は文で判定する問）と、検出器が当たった○の19本
- **突き合わせの別の数え方**：検出器ごとの表は、どの行も合計 78。見立ての表も合計 78。数字の照合は、記録に残る自動の下書き（`stage2/run_001/auto_axis1.tsv`）と78本すべて同じ

### 版の移り（段階2。直すたびにコミットした）

| 版 | 直したこと | 種類 | 変わった数（前の版 → この版） |
|---|---|---|---|
| v1 | 最初の版（記録を読む前） | — | 見立てと人の両方が×か印 13 本、人だけ 1 本（sl_mcp_D5_r1） |
| v2 | run_sql の複数の文を、文ごとに分けて見る | 切り出しの直し | unfinalized_excluded：一致 3 → 1、見落とし 0 → 2（v1 の一致のうち2本は、次の文の `is_finalized` まで WHERE として切り出した不具合で当たっていた）／u_prefix：誤検出 1 → 3／orphan_dropped：誤検出 2 → 1 |
| v2 | quality_flag を WHERE・HAVING だけにする | **狭めた** | 誤検出 8 → 2、一致 2 → 2。理由：FILTER・CASE で有効と無効を並べた本は、人がすべて○（規則B の分けて示す形） |
| v2 | enum_mixed も WHERE・HAVING だけにする（試して戻した） | 狭めた | 一致 1 → 0、誤検出 8 → 4、見落とし 0 → 1（sql_mcp_B3_r2。勧めた数え方を FILTER の列で出していた）。見落としが出たので v3 で戻した |
| v3 | unfinalized_excluded に、確定だけを足す列（CASE・FILTER）も当てる | 広げた | 一致 1 → 2、見落とし 2 → 1、誤検出 0 → 0 |
| v4 | `sum(case when … then revenue_amount)` も「売上を足す」に数える | 広げた | d5_final_only：一致 3 → 4、見落とし 1 → 0、誤検出 2 → 2。見立てで人だけが×か印の本 1 → 0 |

誤検出が5本以上増える直しは無かった（指示書の止まる条件に当たっていない）。

## 3. 5-4 run_002 の117本（試しの段、v4。直していない）

当てた本：117本（t2s 39、t2s_desc 39、sl 39）。SL の組は `mf query` の文字から `--where`・`--group-by`・`--metrics` を取り出し、当てられない検出器は「判定できない」とした。v3 で当てた数と v4 で当てた数は同じだった。

| 検出器 | 一致 | 誤検出 | 別の札 | 見落とし | 当たらず | 判定できない | 対象外 | 計 |
|---|---|---|---|---|---|---|---|---|
| year_less_month | 1 | 0 | 5 | 0 | 17 | 4 | 90 | 117 |
| quality_flag | 15 | 0 | 4 | 1 | 21 | 4 | 72 | 117 |
| unfinalized_excluded | 2 | 0 | 1 | 0 | 19 | 5 | 90 | 117 |
| orphan_dropped | 8 | 0 | 0 | 4 | 6 | 9 | 90 | 117 |
| snapshot_all | 4 | 0 | 0 | 0 | 14 | 9 | 90 | 117 |
| currency_mixed | 16 | 4 | 2 | 5 | 4 | 5 | 81 | 117 |
| d5_final_only | 0 | 0 | 2 | 0 | 4 | 3 | 108 | 117 |
| empty_as_zero | 9 | 0 | 1 | 0 | 8 | 0 | 99 | 117 |
| enum_mixed | 10 | 0 | 0 | 0 | 13 | 13 | 81 | 117 |
| dedupe | 0 | 0 | 0 | 0 | 12 | 6 | 99 | 117 |
| long_format | 1 | 0 | 0 | 4 | 12 | 10 | 90 | 117 |
| u_prefix | 3 | 0 | 0 | 0 | 3 | 3 | 108 | 117 |
| empty_rows_dropped | 0 | 0 | 0 | 0 | 6 | 3 | 108 | 117 |

- **5-4 の印の9本は、9本とも、言葉の対応する検出器が当たった**
  - quality_flag：t2s_B2_r2、t2s_desc_B2_r1・r2・r3
  - year_less_month：t2s_desc_B5_r3
  - unfinalized_excluded：t2s_D6_r3
  - u_prefix：t2s_desc_D2_r1・r2・r3
  - t2s_desc_B2_r3 の印の「LOWER(event_type)」は、enum_mixed も当たった（一致に数えた）
- 見落とし：quality_flag＝t2s_B3_r2／orphan_dropped＝t2s_B4_r2、t2s_C2_r1・r2、t2s_desc_C2_r1／currency_mixed＝sl_C2_r2、t2s_D5_r2・r3、t2s_desc_C2_r2、t2s_desc_D5_r3／long_format＝t2s_B3_r2・r3、t2s_D1_r2・r3。見落としの理由は、この段では読んでいない（直さない段のため）
- 誤検出：currency_mixed＝t2s_D6_r1、t2s_desc_D6_r1・r2・r3（「今月」の売上を通貨を見ずに足したが、データが無く空。人は○）
- 別の札：year_less_month が t2s_B5_r1・r2、t2s_C3_r3、t2s_desc_C3_r1・r3 に当たった。人の札は snapshot・空の結果などで、年を見ない絞り方は書かれていない（×の理由が別にあるので、書く必要が無かったと読める）

| 見立て ＼ 人 | ○ | 印 | × | 答えなし | 計 |
|---|---|---|---|---|---|
| ○ | 21 | 0 | 1 | 0 | 22 |
| 印 | 4 | 9 | 3 | 0 | 16 |
| × | 0 | 0 | 65 | 1 | 66 |
| 答えなし | 0 | 0 | 0 | 7 | 7 |
| 判定できない | 3 | 0 | 3 | 0 | 6 |
| 計 | 28 | 9 | 72 | 8 | 117 |

- 人だけが×か印：sl_C2_r2（通貨別の表のあとで円とドルを足した。呼び出しは通貨で分けていて、間違いは答えの文の中）、t2s_A3_r1・r2・r3（A3 は数字の照合が判定できず、検出器も当たらなかった）
- 見立ての「判定できない」6本は、すべて A3（route 別で答えていない本。referrer の数は warehouse を読まないと分からない）。数字の照合と自動の下書き（`5-4/run_002/auto_axis1.tsv`）の食い違いも、この A3 の6本だけ

## 人の目（チャット）が見落とした5本

段階2 の印のうち、2026-11-03 のチャットの読みで挙がっていなかった「年を見ずに月だけで絞った」5本（sql_mcp_B5_r1・r2・r3、sql_mcp_C3_r2・r3）は、**`year_less_month` が v1（記録を読む前の版）から5本とも当て、誤検出は0本**。根拠は5本とも `where month(revenue_month)=2`（C3 は `=4`）。5-4 の同じ形の t2s_desc_B5_r3 も当てた。ただし、この形は v1 の材料（段階2 の scores.md・final_scores.tsv）に SQL の断片のまま書いてあった。人が見つけたあとの形を写した規則で、人より先に見つけたのではない（下の「言えないこと」）。

## 拾えなかった間違いの種類

- **主な答えをどれにしたか（規則A・C）**：検出器は「その数え方の呼び出しがあったか」しか見ない。分けて並べた表のどの列を勧めたかは答えの文にあり、呼び出しからは分からない。段階2 の誤検出の多く（enum_mixed 8、dedupe 5、u_prefix 3、d5_final_only 2）は、下調べや並べた列に当たったもの。逆に sql_mcp_C2_r1（確定の月だけを勧めた）は、呼び出しが確定と未確定を group by で分けただけで、見落とした
- **答えの文の中の間違い**：sl_C2_r2（円とドルを答えの文で足した）。答えの文から見る検出器は `empty_as_zero` だけ
- **検出器を作っていない札**：代用（SL の D1・D5）、言語の対応づけ、期間（D6 の「今月」をデータのある月で代用）、未締め（C3 の暫定値を確定として返す）、可能性どまり（C3）、mf の書き方のエラー、アカウント数を数える（その他）、別の列（B2 の売上テーブルの配信数）
- **SL の呼び出し**：孤児・snapshot・重複・enum・縦持ち・U・業種の空は、SL の定義が決めるので「判定できない」にした。SL の組で当てられるのは、where・group_by・metrics に出る間違い（年、品質フラグ、未確定、通貨）と、答えの文の `empty_as_zero` だけ

## この検出器で言えないこと

- **チャットが見落とした5本を v1 から当てたことは、「人が見つけて書いた形を規則に写せた」ことしか示さない。** v1 の材料の段階2 の scores.md と final_scores.tsv に、この5本の形が `month(revenue_month)=2`（C3 は `=4`）と SQL の断片のまま書いてあった。人の知らない間違いを検出器が見つけた、とは言えない。5-4 の t2s_desc_B5_r3 も、5-4 の scores.md に同じ形が書いてあった
- **検出器も、当てる台本も、対応づけの言葉も、Claude が書いた。** 独立した物差しは人の判定（final_scores.tsv と 5-4 の scores.md）だけ。5-4 の人の判定は Claude が手で写した（scores.md との機械の突き合わせ 157 件は合ったが、札の言葉の写しは軸1・印ほど機械で確かめていない）
- **段階2 の数は、作りに使った記録の数。** v2〜v4 は段階2 の結果を見て直したので、段階2 の一致の数は当てはめの結果。作りに使っていないのは 5-4 だけ
- **記録の数が少ない。** 段階2 で人が×か印の本は14本、5-4 で81本。問は13問だけで、同じ問の3回はよく似た呼び出しになる
- **5-4 は 5-4 の時点の物差し。** 人の札は1本に1つとは限らず、×の本には目立つ理由だけが書かれていることがある（上の「別の札」）。その場合、検出器の当たりを誤りとも正しいとも言えない
- **「一致」は、言葉の対応づけ（コミット1で決めた正規表現）に頼る。** 「その他（…）」の中身の言葉で対応づけたので、札の書き方が変われば数も変わる
- **見立ての「印」は、検出器が1つ当たれば付く。** 段階2 では人が○の本の19本に付いた。見立てをそのまま採点に使えるほどの精度ではない
