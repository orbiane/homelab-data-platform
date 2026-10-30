# pre-commit と commit-msg から読み込む、個人情報の検査の本体。
# scan_lines 名前 本文のファイル 場所のファイル
#   本文のファイルと場所のファイルは、同じ行番号どうしが対応する（1行に1つ）。
#   見つけた行を種類と一緒に全部出し、1件でもあれば 1 を返す。
#   検査語のファイルが無い・空のときも 1 を返す。

LC_ALL=C
export LC_ALL

scan_lines() {
  name=$1
  txt=$2
  loc=$3
  dir=$(dirname "$txt")

  words=$(git rev-parse --git-path info/private-words) || return 1
  if [ ! -f "$words" ]; then
    echo "$name: 検査語のファイル $words が無いので、コミットを止めました"
    return 1
  fi
  # 空の行は語として使わない（grep -F -f に空の行があると、すべての行に一致するため）
  tr -d '\r' <"$words" | grep -v -e '^[[:space:]]*$' >"$dir/words"
  if [ ! -s "$dir/words" ]; then
    echo "$name: 検査語のファイル $words が空なので、コミットを止めました"
    return 1
  fi

  : >"$dir/hits"
  grep -n -i -F -f "$dir/words" "$txt" | awk -F: '{ print $1 "\t検査語" }' >>"$dir/hits"
  find_kind() {
    grep -n -E -e "$2" "$txt" | awk -F: -v k="$1" '{ print $1 "\t" k }' >>"$dir/hits"
  }
  find_kind 'ホームの絶対パス' '/Users/[A-Za-z0-9._-]+'
  find_kind 'ホームの絶対パス（-でつないだ形）' '-Users-[A-Za-z0-9._]+'
  find_kind '家の LAN の IP' '(^|[^0-9.])192\.168\.[0-9]{1,3}\.[0-9]{1,3}([^0-9]|$)'
  find_kind 'Tailscale の IP' '(^|[^0-9.])100\.(6[4-9]|[7-9][0-9]|1[01][0-9]|12[0-7])\.[0-9]{1,3}\.[0-9]{1,3}([^0-9]|$)'
  find_kind 'MAC アドレス' '(^|[^[:xdigit:]:-])[[:xdigit:]]{2}([:-][[:xdigit:]]{2}){5}([^[:xdigit:]:-]|$)'
  find_kind 'GitHub のトークン' 'gh[pousr]_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{22,}'
  find_kind '秘密鍵' '-----BEGIN ([A-Z0-9]+ )*PRIVATE KEY'
  find_kind 'AWS のアクセスキー' '(AKIA|ASIA)[A-Z0-9]{16}'
  find_kind 'Slack のトークン' 'xox[abposr]-[A-Za-z0-9-]{10,}'

  total=$(awk 'END { print NR }' "$txt")
  found=$(cut -f1 "$dir/hits" | sort -u | awk 'END { print NR }')

  sort -n -k1,1 "$dir/hits" | awk -F'\t' -v locf="$loc" -v txtf="$txt" '
    BEGIN {
      while ((getline l < locf) > 0) L[++nl] = l
      while ((getline t < txtf) > 0) T[++nt] = t
    }
    {
      if ($1 != prev) { if (prev != "") out(); prev = $1; kinds = $2 }
      else if (index("," kinds ",", "," $2 ",") == 0) kinds = kinds "," $2
    }
    END { if (prev != "") out() }
    function out() { print "  [" kinds "] " L[prev] ": " T[prev] }
  '

  echo "$name: 調べた行の数 $total、見つかった行 $found 件"
  if [ "$found" -gt 0 ]; then
    echo "$name: 個人情報らしい行があるので、コミットを止めました"
    return 1
  fi
  return 0
}
