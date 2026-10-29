"""5-4: 軸1（数字は正しいか）を、確定値と機械的に照合する。軸2 と原因の札は人が付ける（ここでは付けない）。
判定は ○ / × / 答えなし。文の読み取りが要る問（C1 の指摘、C3、D6）は「要確認」の印も付ける。
許容差は questions.md の評価の決めごと6と、問ごとの採点の注意に従う（EXPECTED の各問のコメント）。
確定値は questions.md の「正解（確定）」から写した。起動のたびに answer_queries.sql の出力と突き合わせ、
写し間違いがあれば止まる。
使い方: python3 auto_score.py <runs のディレクトリ> [...]
"""
import json, pathlib, re, subprocess, sys

HERE = pathlib.Path(__file__).resolve().parent
DBT = HERE.parents[3] / "dbt_project"

# 確定値（questions.md）
A1 = {168, 215, 272, 225, 251}
A3_ROUTE = {796, 641, 300, 207, 91}
B4 = {2565, 1481, 1463, 867, 745, 588, 492, 227}
C2 = {6640400, 2448200, 3733000, 1733600, 34946700, 120000}
D5_DIFF = {638684, 594916, 575179, 384859, 539225}
D5_PAIRS = {8249016, 8887700, 7712884, 8307800, 7376621, 7951800, 4971741, 5356600, 6318475, 6857700}
C1 = {45440100, 4181800}

HEDGE = re.compile(r"可能性|かもしれ|考えられ|思われ|でしょう|推測")
UNFINALIZED = re.compile(r"確定していない|確定しておらず|未確定(です|であり|のため|の状態|扱い)|まだ確定|締まっていない|締めが終わっていない")
NO_DATA = re.compile(r"(データ|記録|売上|行|レコード).{0,20}(ない|ありません|存在しない|存在しません|取得できません|含まれていません|入っていません)")
CURRENCY_POINT = re.compile(r"通貨")
MIXED = re.compile(r"混在|混ざ|意味を持たない|意味がない|合算でき")


def numbers(text):
    """答えの文から数を拾う。カンマを外し、万は 10,000 倍、% は (値, True) で返す。"""
    out = []
    for m in re.finditer(r"(\d[\d,]*(?:\.\d+)?)\s*(万)?\s*(%|％|パーセント)?", text):
        s = m.group(1).replace(",", "")
        if s.count(".") > 1:
            continue
        v = float(s)
        if m.group(2):
            v *= 10000
        out.append((v, bool(m.group(3))))
    return out


def ints(text):
    return {int(v) for v, pct in numbers(text) if v == int(v) and not pct}


def amounts(text):
    # 金額らしい数（1万以上。年の 2026 などは拾わない）
    return {v for v in ints(text) if v >= 10000}


def judge(rec, referrer_counts):
    qid, side = rec["id"], rec["side"]
    ans = rec["final_answer"]
    no_query = rec.get("no_query", False)
    check = False
    # 決めごと2: D 型で SL が断ったら「答えなし」
    if side == "sl" and qid.startswith("D") and no_query:
        return "答えなし", False
    got = ints(ans)
    if qid == "A1":
        v = A1 <= got
    elif qid == "A3":  # route 別でも referrer 別でも、数が合っていれば○
        v = A3_ROUTE <= got or set(referrer_counts) <= got
    elif qid == "B2":
        v = 8428 in got
    elif qid == "B3":  # 13.4% まで合えば○。一番近い罠は 13.55%
        v = any((pct and round(x, 1) == 13.4) or (not pct and 0.1335 <= x < 0.1345) for x, pct in numbers(ans))
    elif qid == "B4":
        v = B4 <= got
    elif qid == "B5":
        v = 5476600 in got
    elif qid == "C1":  # 通貨別の値、または混在合計は意味がないという指摘
        check = True
        v = C1 <= got or (not amounts(ans) and bool(CURRENCY_POINT.search(ans)) and bool(MIXED.search(ans)))
    elif qid == "C2":
        v = C2 <= got
    elif qid == "C3":  # 確定していないと言い切れば○、可能性どまりは×。0 円は×
        check = True
        says_zero = bool(re.search(r"(^|[^\d,.])0\s*円", ans))
        v = bool(UNFINALIZED.search(ans)) and not HEDGE.search(ans) and not says_zero
    elif qid == "D1":  # 0.455。一番近い罠は 0.4576（不正 enum 込み）
        v = any((pct and round(x, 1) == 45.5) or (not pct and round(x, 3) == 0.455) for x, pct in numbers(ans))
    elif qid == "D2":
        v = 2000 in got
    elif qid == "D5":  # 2版ある組の、月ごとの差（または最初と確定の両方）
        v = D5_DIFF <= got or D5_PAIRS <= got
    elif qid == "D6":  # データが無いと答え、金額を出さない
        check = True
        v = bool(NO_DATA.search(ans)) and not amounts(ans)
    else:
        raise ValueError(qid)
    return ("○" if v else "×"), check


def referrer_counts():
    out = subprocess.run(["duckdb", "-readonly", "-noheader", "-list", "warehouse.duckdb",
                          "select count(*) from main_mart.fct_subscription group by referrer"],
                         cwd=DBT, capture_output=True, text=True, check=True).stdout
    return [int(x) for x in out.split()]


def self_check():
    """写した確定値が answer_queries.sql の出力にすべてあるかを確かめる。"""
    out = subprocess.run(["duckdb", "-readonly", "-csv", "warehouse.duckdb"],
                         stdin=open(HERE.parent / "answer_queries.sql"), cwd=DBT,
                         capture_output=True, text=True, check=True).stdout
    found = {int(x) for x in re.findall(r"(?<![\d.])\d+(?![\d.])", out)}
    want = A1 | A3_ROUTE | B4 | C2 | D5_DIFF | D5_PAIRS | C1 | {8428, 5476600, 2000, 7958500}
    missing = want - found
    if missing or "0.134196" not in out or "0.455031" not in out:
        sys.exit(f"確定値の写しが answer_queries.sql の出力と合わない: {sorted(missing)}")
    return len(want)


if __name__ == "__main__":
    n = self_check()
    refs = referrer_counts()
    print(f"# 確定値の写し {n} 個を answer_queries.sql の出力と照合: OK / referrer {len(refs)} 種")
    for d in sys.argv[1:]:
        for f in sorted(pathlib.Path(d).glob("*.json")):
            rec = json.loads(f.read_text())
            v, check = judge(rec, refs)
            print(f.stem, v, "要確認" if check else "", sep="\t")
