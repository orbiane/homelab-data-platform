"""5-4 run_002: 3つの組 × 13問 × 3回。
指示文・流れ・実行・安全策は run_001/harness.py の solve をそのまま呼ぶ（写さない）。渡す材料だけを差し替える。
変えたのは、組（t2s / t2s_desc / sl）、回数、朝3時の dbt build を避ける待ち、各本の時刻の記録。
回す順は「1回目を全組 → 2回目を全組 → 3回目を全組」。途中で止まっても、既にある記録は飛ばして続きから回る。
"""
import datetime, json, pathlib, sys, time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "run_001"))  # 同じ名前の harness.py なので、run_001 を先に探させる
import harness as h1  # noqa: E402

OUT = HERE / "runs"
OUT.mkdir(exist_ok=True)
REPEATS = 3
JST = datetime.timezone(datetime.timedelta(hours=9))

# 組 -> (指示文と実行の種類, 渡す材料)
GROUPS = {
    "t2s": ("t2s", (HERE / "context_t2s.txt").read_text()),
    "t2s_desc": ("t2s", (HERE / "context_t2s_desc.txt").read_text()),
    "sl": ("sl", (HERE / "context_sl.txt").read_text()),
}


def wait_for_dbt_build():
    # 毎日 JST 03:00 の dbt build（warehouse を作り直す）と重ならないよう、02:50〜03:15 は新しい問を始めない
    while True:
        now = datetime.datetime.now(JST)
        if not (now.hour == 2 and now.minute >= 50 or now.hour == 3 and now.minute < 15):
            return
        time.sleep(60)


def solve(group, qid, q):
    # run_001 の solve をそのまま使い、渡す材料だけを差し替える
    kind, context = GROUPS[group]
    h1.CONTEXT[kind] = context
    rec = h1.solve(kind, qid, q)
    rec["group"] = group
    return rec


if __name__ == "__main__":
    for rep in range(1, REPEATS + 1):
        for group in GROUPS:
            for qid, q in h1.QUESTIONS:
                path = OUT / f"{group}_{qid}_r{rep}.json"
                if path.exists():
                    continue
                wait_for_dbt_build()
                started = datetime.datetime.now(JST).isoformat(timespec="seconds")
                rec = solve(group, qid, q)
                rec["rep"] = rep
                rec["started_at"] = started
                rec["ended_at"] = datetime.datetime.now(JST).isoformat(timespec="seconds")
                path.write_text(json.dumps(rec, ensure_ascii=False, indent=2))
                print(group, qid, rep, "done", flush=True)
