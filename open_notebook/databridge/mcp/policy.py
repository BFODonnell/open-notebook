"""A deliberately small SQL language, shared by app and DuckDB broker.

Parsing is not authorization: callers must also enforce scope, database grants,
transport isolation and server-side resource limits. No joins/CTEs/subqueries yet.
"""

import math
import re

POLICY_VERSION = "databridge-select-v1"
IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")
NODES = {
    "Select",
    "From",
    "Table",
    "Identifier",
    "Column",
    "Alias",
    "TableAlias",
    "Where",
    "Group",
    "Having",
    "Order",
    "Ordered",
    "Limit",
    "Literal",
    "Null",
    "Boolean",
    "Paren",
    "And",
    "Or",
    "Not",
    "EQ",
    "NEQ",
    "GT",
    "GTE",
    "LT",
    "LTE",
    "Is",
    "In",
    "Between",
    "Add",
    "Sub",
    "Mul",
    "Div",
    "Neg",
    "Distinct",
    "Sum",
    "Avg",
    "Count",
    "Min",
    "Max",
    "Abs",
    "Round",
    "Coalesce",
    "Lower",
    "Upper",
}


def readonly_sql(
    sql: str,
    dialect: str,
    tables: dict[str, list[str]],
    limit: int,
    parameters: dict | None = None,
) -> str:
    from sqlglot import exp, parse

    if dialect not in {"postgres", "duckdb", "sqlite"} or not 1 <= limit <= 1000:
        raise ValueError("Unsupported dialect or row limit")
    if not sql.strip() or len(sql.encode()) > 8192:
        raise ValueError("SQL is empty or exceeds 8192 bytes")
    try:
        statements = parse(sql, read=dialect)
    except Exception:
        raise ValueError("SQL could not be parsed") from None
    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        raise ValueError("Only one SELECT is allowed")
    tree = statements[0]
    if any(n.comments for n in tree.walk()):
        raise ValueError("SQL comments are not supported")
    params = parameters or {}
    used = set()
    for placeholder in list(tree.find_all(exp.Placeholder)):
        name = placeholder.name
        if name not in params:
            raise ValueError("Missing named SQL parameter")
        value = params[name]
        if (
            not isinstance(value, (str, int, float, bool, type(None)))
            or (isinstance(value, float) and not math.isfinite(value))
            or len(str(value)) > 1024
        ):
            raise ValueError("Invalid scalar SQL parameter")
        # Some MCP SQL tools have no bind interface. Generate an escaped AST
        # literal, never format untrusted values into SQL text.
        placeholder.replace(exp.convert(value))
        used.add(name)
    if used != set(params):
        raise ValueError("Unexpected SQL parameters")
    relations = list(tree.find_all(exp.Table))
    if len(relations) != 1 or not isinstance(relations[0].this, exp.Identifier):
        raise ValueError("Exactly one approved base table is required")
    table = relations[0]
    if table.catalog or table.db or table.name not in tables:
        raise ValueError("Catalog/schema switching or unapproved table")
    columns = tables[table.name]
    qualifiers = {table.name, table.alias} - {""}
    aliases = {a.alias for a in tree.find_all(exp.Alias)}
    for column in tree.find_all(exp.Column):
        if (
            column.db
            or column.catalog
            or (column.table and column.table not in qualifiers)
        ):
            raise ValueError("Unapproved column qualifier")
        if column.name not in columns:
            # Output aliases are allowed only as direct ORDER BY names.
            if not (column.name in aliases and isinstance(column.parent, exp.Ordered)):
                raise ValueError("Unapproved column (SELECT * is not supported)")
    for node in tree.walk():
        if isinstance(node, exp.Star) and isinstance(node.parent, exp.Count):
            continue
        if type(node).__name__ not in NODES:
            raise ValueError("SQL construct is not in the read-only allowlist")
        if isinstance(node, exp.Identifier) and not IDENTIFIER.fullmatch(node.name):
            raise ValueError("Unsupported identifier")
        if isinstance(node, exp.Literal) and len(node.this) > 1024:
            raise ValueError("SQL literal too large")
    if sum(1 for _ in tree.walk()) > 256:
        raise ValueError("SQL complexity limit exceeded")
    requested = tree.args.get("limit")
    if requested:
        value = requested.expression
        if (
            not isinstance(value, exp.Literal)
            or not value.is_int
            or int(value.this) < 1
        ):
            raise ValueError("LIMIT must be a positive integer")
        limit = min(limit, int(value.this))
    tree = tree.limit(limit)
    return tree.sql(dialect=dialect, identify=True)
