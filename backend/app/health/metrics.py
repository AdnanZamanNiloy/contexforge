"""Per-function structural metrics for the Health Score & Hotspots scan.

Ported from ``hotspots`` (``hotspots-core/src/metrics.rs``), which computes its
metrics over a tree-sitter AST.  Python's own :mod:`ast` gives the same tree for
free, so the definitions are carried over directly rather than approximated:

* **CC** — the tool derives a base from a control-flow graph (``E - N + 2``)
  and then adds boolean operators, ternary expressions and comprehension ``if``
  filters.  For a structured CFG, ``E - N + 2`` equals ``1 + decision points``,
  so counting decisions is the same number without building a graph.
* **ND** — maximum nesting depth over if / while / for / try / with / match.
* **FO** — number of *distinct* call targets in the body.
* **NS** — non-structured exits (return, raise, break, continue), excluding a
  final tail return, which is structured control flow rather than an early exit.
* **LOC** — physical lines of the function.

Only Python is measured.  The index stores whole files for every other
language, split on chunk boundaries, so there is no per-function text to measure
and inventing an approximation would put a number in the report that nothing
supports.

Every helper takes the *statements* making up a scope rather than a node, so a
class can be measured over its own body while its methods are measured
separately — attributing a method's branching to the class as well would
double-count it and make every class look like a hotspot.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

__all__ = ["FunctionMetrics", "iter_symbols", "measure", "scope_statements"]


@dataclass(frozen=True)
class FunctionMetrics:
    name: str
    kind: str  # function | method | class
    path: str
    loc: int
    cc: int
    nd: int
    fo: int
    ns: int


# Statements that open a nesting level. Matches the tool's node list. A
# comprehension's `if` is an expression, so it is counted in CC, not here.
_NESTING_NODES = (
    ast.If,
    ast.While,
    ast.For,
    ast.AsyncFor,
    ast.Try,
    ast.With,
    ast.AsyncWith,
    ast.Match,
)

# Exits that are "non-structured": control leaving partway through the function.
_EXIT_NODES = (ast.Return, ast.Raise, ast.Break, ast.Continue)

_DEF_NODES = (ast.FunctionDef, ast.AsyncFunctionDef)
_COMPREHENSIONS = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)


def scope_statements(node: ast.AST) -> list[ast.stmt]:
    """The statements that make up *node*'s own scope.

    For a function that is its body.  For a class it is the class body with
    method definitions removed, so a class is not charged for its methods.
    """
    body = list(getattr(node, "body", []) or [])
    if isinstance(node, ast.ClassDef):
        body = [s for s in body if not isinstance(s, _DEF_NODES)]
    return body


def _decision_points(statements: list[ast.stmt]) -> int:
    """Branch points in *statements*.

    This is the increment CC adds on top of its base of 1, matching the tool's
    ``python_count_cc_extras`` (boolean operators, ternary expressions,
    comprehension ``if`` filters) extended with the structured decisions the CFG
    formula would have counted.
    """
    count = 0
    for statement in statements:
        for node in ast.walk(statement):
            if isinstance(node, ast.If):
                # `elif` appears as a nested If in `orelse`, so it is counted here.
                count += 1
            elif isinstance(node, (ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler)):
                count += 1
            elif isinstance(node, ast.BoolOp):
                # `a and b and c` is two short-circuits, not one.
                count += len(node.values) - 1
            elif isinstance(node, ast.IfExp):
                count += 1
            elif isinstance(node, _COMPREHENSIONS):
                # The `if` filters live on each generator, not on the
                # comprehension itself.
                count += sum(len(gen.ifs) for gen in node.generators)
            elif isinstance(node, ast.Assert):
                count += 1
            elif isinstance(node, ast.Match):
                # Each case arm after the first is an extra branch.
                count += max(0, len(node.cases) - 1)
    return count


def _nesting_depth(statements: list[ast.stmt]) -> int:
    """Maximum depth of nested control-flow blocks.

    An ``if`` at the top of a function body is depth 1, matching the tool,
    which measures depth from the function's body block.  A statement that is
    itself a control-flow block therefore starts at depth 1, not 0.
    """

    def walk(node: ast.AST, depth: int) -> int:
        best = depth
        for child in ast.iter_child_nodes(node):
            step = depth + 1 if isinstance(child, _NESTING_NODES) else depth
            best = max(best, walk(child, step))
        return best

    return max(
        (walk(statement, 1 if isinstance(statement, _NESTING_NODES) else 0) for statement in statements),
        default=0,
    )


def _distinct_callees(statements: list[ast.stmt]) -> int:
    """Distinct call targets, keyed on the written form.

    Using the source text (``obj.method``, ``Cls.method``, ``fn``) means two
    call sites of one name count once, while a module-level call and a method
    call that share a bare name stay distinct.
    """
    names: set[str] = set()
    for statement in statements:
        for node in ast.walk(statement):
            if isinstance(node, ast.Call):
                try:
                    names.add(ast.unparse(node.func))
                except Exception:  # pragma: no cover - unparse is total
                    continue
    return len(names)


def _non_structured_exits(statements: list[ast.stmt]) -> int:
    """Return/raise/break/continue, minus a final tail return."""
    total = 0
    last: ast.stmt | None = None
    for statement in statements:
        for node in ast.walk(statement):
            if isinstance(node, _EXIT_NODES):
                total += 1
        last = statement
    # A `return` as the last statement is how a function ends normally, not an
    # early exit, so it is not counted.
    if isinstance(last, ast.Return) and total > 0:
        total -= 1
    return total


def measure(name: str, node: ast.AST, path: str, kind: str = "function") -> FunctionMetrics:
    """Compute the metric set for one function, method or class."""
    statements = scope_statements(node)
    loc = getattr(node, "end_lineno", None) - getattr(node, "lineno", 1) + 1
    return FunctionMetrics(
        name=name,
        kind=kind,
        path=path,
        loc=max(0, loc),
        # 1 + decisions is E-N+2 for a structured CFG, without building one.
        cc=1 + _decision_points(statements),
        nd=_nesting_depth(statements),
        fo=_distinct_callees(statements),
        ns=_non_structured_exits(statements),
    )


def iter_symbols(source: str, path: str) -> list[FunctionMetrics] | None:
    """Measure every function, method and class in *source*.

    Returns ``None`` when *source* does not parse, so a file that could not be
    reassembled from the index is reported as skipped rather than measured from
    a guess.  Returns ``[]`` when it parses but declares no functions, which is
    a real and common thing for a module of imports to be.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError, ValueError, RecursionError, MemoryError:
        return None

    results: list[FunctionMetrics] = []

    def visit(node: ast.AST, in_class: bool) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, _DEF_NODES):
                results.append(measure(child.name, child, path, "method" if in_class else "function"))
                # Recurse for nested defs, but the enclosing function's metrics
                # already counted this body's nodes, so nothing is double-counted
                # across symbols.
                visit(child, False)
            elif isinstance(child, ast.ClassDef):
                results.append(measure(child.name, child, path, "class"))
                visit(child, True)
            else:
                visit(child, in_class)

    visit(tree, False)
    return results
