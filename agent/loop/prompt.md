docs/agent/loop.md に従って、NEXT.md の <ID> を1件だけ進める。

- <ID> は、起動の台本（agent/loop/run.py と pick.py）が NEXT.md の表と GitHub の PR から選んだ。選び直さない
- 起動の台本は、作業場所に消えていない変更が無いことを確かめ、origin/main に戻してある（detached HEAD）。作業ブランチは `git switch -c auto/<ID>` で作る
- この起動は承認の画面が出ない（dontAsk）。断られた操作は、別の書き方で通そうとせず、報告の6に書く
