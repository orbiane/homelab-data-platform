<!-- このファイルは公開リポジトリに入る。ユーザー名・IP・絶対パス・旧ドメインの語彙を書かないこと。 -->
# homelab-data-platform

架空の messaging SaaS ドメインで、汚れたデータを**意図的に**仕込んだ小さな DWH（dbt + DuckDB）と、その上のセマンティックレイヤー（MetricFlow）。
目的は、AI エージェント時代のデータ基盤がどう失敗するかを、実データで示すこと。

**汚れはバグではなく実験材料。直したくなっても直さない。**

## 役割分担

- 設計判断（スキーマ、汚れの扱い、層の設計、メトリクス定義）は人間が決める。Claude は選択肢とトレードオフを出して止まる
- コードの生成・実行・調査は Claude が行い、人間がレビューする
- Phase 5-4（Semantic Layer vs Text-to-SQL 比較）の正解値は人間が確定する。Claude が作るのは正解 SQL の下書きまで

## 守ること

1. **仕込んだ汚れを消さない。** staging / mart で汚れを除外・補正・重複排除する変更をしない。品質フラグは汚れを「見えるようにする」ためのもので、集計から除外しない（理由は `docs/decisions/`）
   - 全テーブル共通: contact_id の約 1 割で U プレフィックスが欠落
   - message_event: 遅延到着 / 完全重複 / 孤児（dim_account に無い account_id、189 行）/ 順序矛盾 / enum 不正・null / click_url 整合違反
   - revenue: snapshot drift / 未締め / ゼロと欠損の混同 / USD 混入（2 アカウント）/ 孤児（1 行）
   - subscription: 孤児は無い（2,035 行中 0 件）。dim_account で業種が空のアカウントが 2 つあり、結合すると 440 行の industry が NULL になる
   - `dbt build` の WARN は意図的な汚れ検知。ERROR=0 が正常
2. **メトリクス定義を勝手に変えない。** `_metrics.yml` と `_semantic_models.yml` は、差分を提案して承認を待つ
3. **ツールのバージョンを上げない。** 比較実験の再現性のため固定（dbt-core 1.11.8 / dbt-duckdb 1.10.1 / dbt-metricflow 0.14.0）。`mf` が表示する `pip install --upgrade` の案内には従わない
4. **git の履歴を書き換えない。** filter-repo / rebase / reset --hard / force push をしない。push は人間の承認後
5. **公開リポジトリである。** ユーザー名、IP・MAC アドレス、ホームディレクトリを含む絶対パス、クレデンシャルをコミットしない。パスは相対パスか `~` で書く。`~/.dbt/profiles.yml` をリポジトリにコピーしない
6. **語彙は架空ドメインのもの**（account / contact / subscription / message_event）。実在サービス固有の用語を持ち込まない
7. **データを作り直す前に聞く。** `data_generation/` の generator 再実行と `warehouse.duckdb` への書き込みは、調査中の証拠を消すことがある

## 環境の落とし穴

- dbt コマンドは `dbt_project/` の中で実行する（相対パス依存）
- `mf` は `~/.local/bin/mf` への symlink で、uv の管理外。見つからない・壊れていると思っても、再インストールせずに報告する
- `mf` には環境変数 `DBT_PROFILES_DIR` が要る（シェル設定で `~/.dbt` を指している）。profiles が見つからないと言われたら、まず `echo $DBT_PROFILES_DIR`
- `dbt sl` 系は使わない（dbt Platform 前提）。`mf query` / `mf list metrics` を使う
- DuckDB を読むだけなら `duckdb -readonly dbt_project/warehouse.duckdb`
- Airflow は `airflow/` の Docker Compose。UI はホスト側ポート 8081（8080 は Docker が占有）。DAG は毎日 JST 03:00 に `dbt build` を実行する
- Docker Desktop は macOS の再起動後に自動起動しない（`open -a Docker`）
- 生成データの版は `data_generation/output.sha256` で照合する（`cd data_generation/output && shasum -a 256 -c ../output.sha256`）。数値を出す前や比較実験の前に照合し、合わなければ止めて報告する
- `revenue_monthly.py` は `hash()` を使っているため、再実行すると金額が変わる（ADR-006）

## 作業の進め方

- ファイル名・カラム名・数値を記憶で書かない。実物を見てから書く
- 数値を報告するときは、実行したコマンドと出力を添える
- チェックの結果を報告するときは、検査した対象の件数も添える（「0件」が「何も無い」のか「何も見ていない」のかを区別するため）
- 分からないことを推測で埋めない。確かめるコマンドを走らせる
- 設計判断の根拠は `docs/decisions/`（ADR-001〜005）にある。関係する変更の前に読む
- 計画を出すときは、各ステップで何を確かめれば成功と言えるかを書く
- 作業の最後に、何をしたか・なぜか・根拠・まだ怪しい点・人間に決めてほしいことを、平易な日本語で短く報告する
- 専門用語は初めて使うときに一言で説明する
