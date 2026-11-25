"""Inspect generated SQL with PostgreSQL's parser before it can reach a reader."""

from __future__ import annotations

import re

from pglast import ast, parse_sql
from pglast.parser import ParseError
from pglast.visitors import Visitor

from .db import READ_TABLES


class QueryError(ValueError):
    pass


FUNCTIONS = frozenset(
    """
abs avg cast coalesce count dense_rank date_part extract first_value lag last_value lead length
lower ltrim max min nullif rank replace round row_number rtrim similarity string_agg strpos substr
substring sum trim upper
""".split()
)
TYPES = frozenset(
    "bool boolean date decimal float4 float8 int2 int4 int8 numeric text timestamp timestamptz varchar".split()
)
OPERATORS = frozenset("= <> != < > <= >= + - * / % || ~~ !~~ ~~* !~~*".split()) | {
    "BETWEEN",
    "NOT BETWEEN",
    "BETWEEN SYMMETRIC",
    "NOT BETWEEN SYMMETRIC",
}


class Inspect(Visitor):
    def __init__(self, relation_names: set[str]):
        super().__init__()
        self.relation_names = relation_names

    def visit_SelectStmt(self, ancestors, node):
        if node.intoClause or node.lockingClause:
            raise QueryError("Use a read-only SELECT without locking or INTO.")

    def visit_CommonTableExpr(self, ancestors, node):
        if not isinstance(node.ctequery, ast.SelectStmt):
            raise QueryError("Every CTE must be a SELECT.")

    def visit_RangeVar(self, ancestors, node):
        if node.catalogname or node.schemaname or node.relname not in self.relation_names:
            raise QueryError(
                "Unknown relation. Use an unqualified table from the ScholarQL schema or a CTE."
            )

    def visit_FuncCall(self, ancestors, node):
        if len(node.funcname) != 1 or node.funcname[0].sval.casefold() not in FUNCTIONS:
            raise QueryError("Use only supported SQL functions.")

    def visit_SQLValueFunction(self, ancestors, node):
        raise QueryError("Use corpus fields and explicit literals for reproducible results.")

    def visit_RangeFunction(self, ancestors, node):
        raise QueryError("Select rows from a ScholarQL table or a CTE.")

    def visit_RangeTableSample(self, ancestors, node):
        raise QueryError("Use the complete ScholarQL relation for sampling-free answers.")

    def visit_TypeName(self, ancestors, node):
        names = tuple(x.sval for x in node.names)
        if names[-1].casefold() not in TYPES or (len(names) > 1 and names[:-1] != ("pg_catalog",)):
            raise QueryError("Use standard numeric, string, date, or Boolean casts.")

    def visit_CollateClause(self, ancestors, node):
        raise QueryError("Use the database's default collation.")

    def visit_A_Expr(self, ancestors, node):
        names = tuple(x.sval for x in node.name or ())
        if names and (len(names) != 1 or names[0] not in OPERATORS):
            raise QueryError("Use a standard SQL comparison or arithmetic operator.")

    def visit_ParamRef(self, ancestors, node):
        raise QueryError("Use literal values for generated SQL.")


class CTEs(Visitor):
    def __init__(self):
        super().__init__()
        self.names: set[str] = set()

    def visit_CommonTableExpr(self, ancestors, node):
        self.names.add(node.ctename)


def validate_sql(sql: str) -> str:
    clean = re.sub(r"^\s*```(?:sql|postgresql)?\s*|\s*```\s*$", "", sql.strip(), flags=re.I).strip()
    if len(clean) > 12_000:
        raise QueryError("SQL exceeds the 12,000-character limit.")
    try:
        statements = parse_sql(clean)
    except (ParseError, ValueError) as error:
        message = getattr(error, "args", ("Invalid SQL",))[0]
        raise QueryError(f"SQL parser: {message}") from error
    if len(statements) != 1 or not isinstance(statements[0].stmt, ast.SelectStmt):
        raise QueryError("Use exactly one SELECT or WITH ... SELECT.")
    stmt = statements[0].stmt
    ctes = CTEs()
    ctes(stmt)
    Inspect(set(READ_TABLES) | ctes.names)(stmt)
    return clean
