"""5-4 run_002: LLM に渡す材料を、定義ファイルと warehouse から機械的に作る。
- context_t2s.txt      : mart の列名と型（run_001 と同じ作り方）
- context_t2s_desc.txt : 上に、指標の説明の節を足したもの
- context_sl.txt       : 指標の説明の節 + 指標ごとのディメンション + mf query の書き方
指標の説明の節は _metrics.yml から作り、t2s_desc と sl で同じ文字列を使う。
mf query の書き方の節だけは人が書いたもの（run_001 の context_sl.txt から、そのまま取り出す）。
実行: dbt-core の uv tool の python で（PyYAML が要る）
"""
import pathlib, re, subprocess
import yaml

HERE = pathlib.Path(__file__).parent
REPO = HERE.parents[3]
DBT = REPO / "dbt_project"
MART = DBT / "models" / "mart"
MF = pathlib.Path.home() / ".local/bin/mf"
TABLES = ["dim_account", "fct_message_event", "fct_revenue", "fct_subscription"]


def schema_section():
    sql = ("select table_name, string_agg(column_name || ' ' || data_type, ', ' order by ordinal_position) "
           "from information_schema.columns where table_schema='main_mart' and table_name in ("
           + ",".join(f"'{t}'" for t in TABLES) + ") group by table_name order by table_name")
    out = subprocess.run(["duckdb", "-readonly", "-noheader", "-list", "warehouse.duckdb", sql],
                         cwd=DBT, capture_output=True, text=True, check=True).stdout
    lines = [re.sub(r"^([a-z_]+)\|", r"- main_mart.\1: ", l) for l in out.splitlines() if l]
    return "## スキーマ（DuckDB。スキーマ名 main_mart）\n" + "\n".join(lines) + "\n"


def metrics():
    return yaml.safe_load((MART / "_metrics.yml").read_text())["metrics"]


def metric_section():
    # 説明の改行は詰める（日本語の文なので空白を入れずにつなぐ）
    lines = ["- " + m["name"] + "：" + "".join(l.strip() for l in m["description"].strip().splitlines())
             for m in metrics()]
    return "## メトリクス（名前：説明）\n" + "\n".join(lines) + "\n"


def dimension_section():
    lines = []
    for m in metrics():
        out = subprocess.run([str(MF), "list", "dimensions", "--metrics", m["name"]],
                             cwd=DBT, capture_output=True, text=True, check=True).stdout
        dims = [l[2:].strip() for l in out.splitlines() if l.startswith("• ")]
        lines.append("- " + m["name"] + "：" + ", ".join(dims))
    return "## メトリクスごとに使えるディメンション\n" + "\n".join(lines) + "\n"


def syntax_section():
    text = (HERE.parent / "run_001" / "context_sl.txt").read_text()
    i = text.index("## mf query の書き方")
    return text[i:]


if __name__ == "__main__":
    schema, metric = schema_section(), metric_section()
    (HERE / "context_t2s.txt").write_text(schema)
    (HERE / "context_t2s_desc.txt").write_text(schema + "\n" + metric)
    (HERE / "context_sl.txt").write_text(metric + "\n" + dimension_section() + "\n" + syntax_section())
    print("wrote 3 files")
