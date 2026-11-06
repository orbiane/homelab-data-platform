# pre-commit から読み込む、ADR-007 の R6（コミットの入口）。
# definition_guard 一時ディレクトリ
#   定義のファイル（dbt_project/models/ の下の _metrics.yml・_semantic_models.yml）を
#   変えるコミットで、次のどれかなら理由を出して 1 を返す。
#   - 決定メモ（docs/business/ の下）の追加・変更と、定義の変更が同じコミットにある
#   - 定義のファイルごとに、足した行に決定メモのパスが無い
#   - 足した行にある決定メモのパスが HEAD に無い

definition_guard() {
  dir=$1
  how='通すには：定義のファイルで足す行に、HEAD にある決定メモのパス docs/business/<名前>.md を書く。決定メモが無いなら、止まって人に聞く（ADR-007）'

  git diff --cached --name-only --no-renames -z >"$dir/staged0" || return 1
  tr '\0' '\n' <"$dir/staged0" >"$dir/staged"
  # 定義のファイル＝models の下の .yml・.yaml のうち、名前が決まったものか、
  # ステージした中身か HEAD の中身に行頭の metrics:・semantic_models: があるもの（消す・移すときも捕まえる）
  grep -E '^dbt_project/models/.*\.ya?ml$' "$dir/staged" >"$dir/ymls" || :
  : >"$dir/defs"
  while IFS= read -r f; do
    case "${f##*/}" in
      _metrics.yml|_semantic_models.yml) echo "$f" >>"$dir/defs"; continue ;;
    esac
    if { git show ":$f" 2>/dev/null; git show "HEAD:$f" 2>/dev/null; } |
      grep -q -E '^[[:space:]]*(metrics|semantic_models)[[:space:]]*:'; then
      echo "$f" >>"$dir/defs"
    fi
  done <"$dir/ymls"
  grep -E '^docs/business/' "$dir/staged" >"$dir/memos"

  if [ ! -s "$dir/defs" ]; then
    echo "pre-commit（ADR-007）: 定義のファイルの変更 0 件（調べたファイル $(wc -l <"$dir/staged" | tr -d ' ') 件）"
    return 0
  fi

  ng=0
  if [ -s "$dir/memos" ]; then
    echo "pre-commit（ADR-007）: 決定メモの追加・変更と定義の変更が同じコミットにあるので止めました"
    sed 's/^/  決定メモ: /' "$dir/memos"
    sed 's/^/  定義: /' "$dir/defs"
    echo "  決定メモは人が別のコミットで入れます。$how"
    ng=1
  fi

  if ! git rev-parse --verify -q HEAD >/dev/null; then
    echo "pre-commit（ADR-007）: HEAD が無いので、決定メモを確かめられません。止めました"
    return 1
  fi

  while IFS= read -r f; do
    git diff --cached --no-color --no-ext-diff --text -U0 -- "$f" |
      grep -E '^\+' | grep -v -E '^\+\+\+ ' >"$dir/added" || :
    grep -o -E 'docs/business/[A-Za-z0-9._-]+\.md' "$dir/added" | sort -u >"$dir/cited" || :
    if [ ! -s "$dir/cited" ]; then
      echo "pre-commit（ADR-007）: $f で足した行（$(wc -l <"$dir/added" | tr -d ' ') 行）に決定メモのパスが無いので止めました"
      echo "  $how"
      ng=1
      continue
    fi
    while IFS= read -r m; do
      if git cat-file -e "HEAD:$m" 2>/dev/null; then
        echo "pre-commit（ADR-007）: $f は HEAD にある決定メモ $m を書いています"
      else
        echo "pre-commit（ADR-007）: $f が書いている決定メモ $m が HEAD に無いので止めました"
        echo "  $how"
        ng=1
      fi
    done <"$dir/cited"
  done <"$dir/defs"

  return $ng
}
