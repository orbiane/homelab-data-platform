# ADR-007: 定義の書き換えは、人が書いた決定メモにひも付ける

- 日付：2026-11-06
- 状態：採用

## 状況
- 段階3で、決定メモ `docs/business/2026-11-05-ctr.md`（クリック率は開封した数あたりで見る）と、SL の定義 `ctr`（クリック数 ÷ 配信数）が食い違う状態を、わざと作った。dbt test は何も捕まえなかった（`docs/analysis/stage3/log.md`）
- SL の道具を持つ Claude は、決定メモの場所を教えると9回中9回、定義が古いことに気づいた。ただし答え方を指示しないと、どちらの数字を正とするかも、開封の数え方も、自分で決めた（`docs/analysis/stage3/find_001`・`find_002`）
- エージェントは定義のファイルを書き換えられる。今の守りは settings.json の ask（`Edit(**/_metrics.yml)` と `Edit(**/_semantic_models.yml)`）だけで、Write と Bash からの書き換えは通りうる

## 決定（人が選んだ、2026-11-06）
定義の書き換えは、人が書いた決定メモにひも付いていれば許す。見つけることと直す作業はエージェントに任せる。どの数え方を正とするかは人が決め、`docs/business/` に書く。

## 決まり
守る場所は3つ。
- 定義：`dbt_project/models/` の下の `_metrics.yml` と `_semantic_models.yml`
- 決定メモ：`docs/business/` の下
- 守りそのもの：`.claude/settings.json`、`.claude/hooks/` の下、`.githooks/` の下

道具の入口（Claude Code の PreToolUse hook）
- R1 定義は Edit でだけ変える。Write での書き換えは止める（差分が承認の画面に出るように）
- R2 定義の Edit は、書き込む文に決定メモのパス（`docs/business/<名前>.md`）が入っていて、そのファイルが HEAD にコミット済みのときだけ通す。通したあとは、ふだんの承認の流れ（settings.json の ask）に進む
- R3 決定メモの場所には、エージェントは書けない。人が書く手順：GitHub の画面で `docs/business/` にファイルを足してコミットし、Claude Code に git pull させる
- R4 守りそのものの書き換えは、どのモードでも毎回人に聞く（hook が ask を返す）
- R5 Bash で、守る場所の名前と書き換えの印（`>`、`tee`、`sed`、`perl`、`python`、`awk`、`cp`、`mv`、`rm`、`truncate`、`dd`、`ln`、`patch`、`git apply`、`git checkout`、`git restore`）を両方含むコマンドは止める。git の hook を飛ばす書き方（`--no-verify`、git commit の `-n` を含む短いオプションのまとまり、`core.hooksPath`）も止める

コミットの入口（`.githooks/pre-commit`）
- R6 定義の変更をコミットするとき、定義のファイルで足した行に、HEAD にある決定メモのパスが無ければ止める。決定メモの追加・変更と定義の変更を同じコミットに入れたら止める。今までの個人情報の検査はそのまま走らせる

共通
- hook が自分のエラーや時間切れで落ちたときは、止める側に倒す
- 止めるときは、理由と、どうすれば通るか（決定メモのパスを書く／決定メモが無いなら止まって人に聞く）を返す
- 定義のファイル＝`dbt_project/models/` の下の `.yml`・`.yaml` のうち、(1) 名前が `_metrics.yml` か `_semantic_models.yml`、または (2) 中身に、行頭（前の空白は許す）の `metrics:` か `semantic_models:` のキーがあるもの
- (2) の中身は、道具の入口では「今のファイルの中身」と「書き込む文（Edit・MultiEdit の new_string、Write の content）」の両方を見る。コミットの入口では「ステージした中身」と「HEAD の中身」の両方を見る（消す・移すときも捕まえる）
- R5 の守る場所の名前に、`dbt_project/models` の下の `.yml`・`.yaml` のパス（正規表現 `models/\S*\.ya?ml`）を足す

## 関所を2か所に置く理由
- 道具の入口は、書く前に止められる。でも Bash の中身を読み切れない（スクリプトのファイルに書いてから走らせる、など）
- コミットの入口は、どの道から変えても必ず見る。でも、ファイルはもう変わったあとで、コミットしなければ効かない

## 採らなかった案
- エージェントには定義を一切書かせない：一番強いが、直す作業を全部人がやることになる
- 止めずに、変えたあとで確かめる：一番軽いが、勝手な書き換えも一度は入る。確かめた結果を人が見る必要が残る（人が見て見張るのは当てにならない。段階2）

## 名前だけで決めていた穴を塞いだ（2026-11-06）
- 最初の版（2026-11-06）は、定義を名前（`_metrics.yml`・`_semantic_models.yml`）だけで決めていた。dbt は models の下のどの名前の YAML に書いた指標や semantic model も受け付けるので、名前の違う新しいファイルに定義を書くと、道具の入口とコミットの入口の両方を素通りできた
- そこで、定義かどうかを名前と中身（行頭の `metrics:`・`semantic_models:`）で決めるように直した。試しは T21〜T26・C07〜C09・L6

## 知っている穴（塞いでいない）
- H1 形の検査である。決定メモの中身と変更が合っているか、関係の無いメモを書いていないかは見ない
- H2 Bash を持つエージェントは、名前を出さないスクリプトで決定メモを書き、別のコミットで通し、そのあと定義を変えられる。最後の関所は、人の push の承認と、GitHub 上の確かめ
- H3 コミットの前のファイルも効く。Airflow の DAG はリポジトリの作業中のファイルで毎晩 dbt build を回すので、コミットを止めても、作業中の書き換えはその夜の build に入る
- H4 hook の ask は、bypassPermissions のモードでは聞かずに通る、という報告がある（未確認。Desktop では Bypass を選べない）

## 試し
`docs/analysis/stage3/guard_cases.md`（人が回す前に決めた表）

## 段階2の記録（ここにまとめる）
- 段階2のアクセスの決め（自前の MCP サーバー、run_sql は `-safe -readonly`、Bash の `mf`・`duckdb` を deny）は `agent/sl_mcp/README.md` と `docs/analysis/stage2/run_001/conditions.md` が正
- 採点の確定で Claude Code が人に求めた3つ（sl_mcp_C2_r1、印の5本、C1・C3 の軸2）は、判定のままにした（人、2026-11-04）
