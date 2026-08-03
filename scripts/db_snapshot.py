import os
import json
from pathlib import Path
from decimal import Decimal
from datetime import date, datetime

import psycopg
from psycopg.rows import dict_row

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


BASE_DIR = Path(__file__).resolve().parents[1]
ENV_PATH = BASE_DIR / ".env"

if load_dotenv:
    load_dotenv(ENV_PATH)
else:
    # Fallback: proceed without python-dotenv, relying on shell env
    pass


OUTPUT_DIR = BASE_DIR / "db_snapshot"
OUTPUT_DIR.mkdir(exist_ok=True)


def to_jsonable(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, list):
        return [to_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {k: to_jsonable(v) for k, v in value.items()}
    return value


def fetch_all(cur, query, params=None):
    cur.execute(query, params or ())
    return cur.fetchall()


def fetch_one(cur, query, params=None):
    cur.execute(query, params or ())
    return cur.fetchone()


def get_tables(cur):
    return fetch_all(
        cur,
        """
        SELECT table_schema, table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_type = 'BASE TABLE'
        ORDER BY table_name
        """
    )


def get_columns(cur, table_name):
    return fetch_all(
        cur,
        """
        SELECT
            column_name,
            data_type,
            udt_name,
            is_nullable,
            column_default,
            ordinal_position
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = %s
        ORDER BY ordinal_position
        """,
        (table_name,),
    )


def get_primary_key(cur, table_name):
    rows = fetch_all(
        cur,
        """
        SELECT kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.table_schema = kcu.table_schema
        WHERE tc.table_schema = 'public'
          AND tc.table_name = %s
          AND tc.constraint_type = 'PRIMARY KEY'
        ORDER BY kcu.ordinal_position
        """,
        (table_name,),
    )
    return [r["column_name"] for r in rows]


def get_indexes(cur, table_name):
    return fetch_all(
        cur,
        """
        SELECT indexname, indexdef
        FROM pg_indexes
        WHERE schemaname = 'public'
          AND tablename = %s
        ORDER BY indexname
        """,
        (table_name,),
    )


def get_row_count(cur, table_name):
    q = f'SELECT COUNT(*) AS n FROM "{table_name}"'
    row = fetch_one(cur, q)
    return row["n"]


def get_table_size(cur, table_name):
    ident = f'public."{table_name}"'
    row = fetch_one(
        cur,
        """
        SELECT
            pg_size_pretty(pg_total_relation_size(%s::regclass)) AS total_size,
            pg_total_relation_size(%s::regclass) AS total_bytes
        """,
        (ident, ident),
    )
    return row


def get_sample_rows(cur, table_name, limit=5):
    q = f'SELECT * FROM "{table_name}" LIMIT {int(limit)}'
    rows = fetch_all(cur, q)
    return [{k: to_jsonable(v) for k, v in row.items()} for row in rows]


def main():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise RuntimeError(
            f"DATABASE_URL is not set. Checked shell env and {ENV_PATH}"
        )

    report = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "env_file_checked": str(ENV_PATH),
        "tables": [],
    }

    with psycopg.connect(db_url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            tables = get_tables(cur)

            for t in tables:
                table_name = t["table_name"]
                print(f"Inspecting {table_name}...")

                table_info = {
                    "table_name": table_name,
                    "row_count": get_row_count(cur, table_name),
                    "size": get_table_size(cur, table_name),
                    "primary_key": get_primary_key(cur, table_name),
                    "columns": [
                        {
                            "column_name": c["column_name"],
                            "data_type": c["data_type"],
                            "udt_name": c["udt_name"],
                            "is_nullable": c["is_nullable"],
                            "column_default": c["column_default"],
                            "ordinal_position": c["ordinal_position"],
                        }
                        for c in get_columns(cur, table_name)
                    ],
                    "indexes": [
                        {
                            "indexname": i["indexname"],
                            "indexdef": i["indexdef"],
                        }
                        for i in get_indexes(cur, table_name)
                    ],
                    "sample_rows": get_sample_rows(cur, table_name, limit=5),
                }

                report["tables"].append(table_info)

    json_path = OUTPUT_DIR / "db_snapshot.json"
    md_path = OUTPUT_DIR / "db_snapshot.md"

    json_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    md_lines = []
    md_lines.append("# DB Snapshot")
    md_lines.append("")
    md_lines.append(f"Generated at: `{report['generated_at']}`")
    md_lines.append(f"Env file checked: `{report['env_file_checked']}`")
    md_lines.append("")

    for table in report["tables"]:
        md_lines.append(f"## {table['table_name']}")
        md_lines.append("")
        md_lines.append(f"- Rows: **{table['row_count']}**")
        md_lines.append(
            f"- Size: **{table['size']['total_size']}** ({table['size']['total_bytes']} bytes)"
        )
        md_lines.append(f"- Primary key: `{table['primary_key']}`")
        md_lines.append("")

        md_lines.append("### Columns")
        md_lines.append("")
        md_lines.append("| # | Name | Type | Nullable | Default |")
        md_lines.append("|---|------|------|----------|---------|")
        for c in table["columns"]:
            default = (
                str(c["column_default"]).replace("\n", " ")
                if c["column_default"] is not None
                else ""
            )
            md_lines.append(
                f"| {c['ordinal_position']} | {c['column_name']} | {c['data_type']} ({c['udt_name']}) | {c['is_nullable']} | {default} |"
            )
        md_lines.append("")

        md_lines.append("### Indexes")
        md_lines.append("")
        if table["indexes"]:
            for idx in table["indexes"]:
                md_lines.append(f"- **{idx['indexname']}**: `{idx['indexdef']}`")
        else:
            md_lines.append("- None")
        md_lines.append("")

        md_lines.append("### Sample rows")
        md_lines.append("")
        md_lines.append("```json")
        md_lines.append(json.dumps(table["sample_rows"], indent=2, ensure_ascii=False))
        md_lines.append("```")
        md_lines.append("")

    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    print(f"\nWrote:\n- {json_path}\n- {md_path}")


if __name__ == "__main__":
    main()