"""Health Score & Hotspots — metrics, LRS and the scan.

The LRS formula and its band thresholds are a direct port, so these assert the
ported numbers exactly: a wrong weight or a wrong cap would silently mislabel
every severity band in the report, and the number looks plausible either way.
"""

from __future__ import annotations

import math

import pytest

from app.health.metrics import FunctionMetrics, iter_symbols, scope_statements
from app.health.risk import (
    CRITICAL_AT,
    HIGH_AT,
    MAX_LRS,
    MODERATE_AT,
    RISK_WEIGHTS,
    analyze,
    band_for,
    health_from_bands,
)
from app.health.service import HealthError, HealthService
from app.health.storage import HealthStore


def _one(source: str, kind: str = "function"):
    results = iter_symbols(source, "m.py")
    assert results, "expected at least one symbol"
    return results[0] if kind == "function" else results


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #


def test_trivial_function_has_baseline_metrics():
    (fn,) = iter_symbols("def f():\n    return 1\n", "m.py")
    assert fn.name == "f"
    assert fn.cc == 1  # no decisions
    assert fn.nd == 0
    assert fn.fo == 0
    # A single tail return is structured control flow, not an early exit.
    assert fn.ns == 0


def test_if_statement_raises_complexity_by_one():
    (fn,) = iter_symbols("def f(x):\n    if x:\n        return 1\n    return 0\n", "m.py")
    assert fn.cc == 2


def test_elif_counts_as_its_own_branch():
    # Python models `elif` as a nested If inside orelse.
    (fn,) = iter_symbols(
        "def f(x):\n    if x == 1:\n        return 1\n    elif x == 2:\n        return 2\n    return 0\n", "m.py"
    )
    assert fn.cc == 3


def test_boolean_chain_counts_each_short_circuit():
    (fn,) = iter_symbols("def f(a, b, c):\n    return a and b and c\n", "m.py")
    # `a and b and c` is two short-circuits on top of the base of 1.
    assert fn.cc == 3


def test_ternary_and_comprehension_filter_add_branches():
    (fn,) = iter_symbols("def f(xs):\n    return [x for x in xs if x]\n", "m.py")
    assert fn.cc == 2
    (fn2,) = iter_symbols("def g(x):\n    return 1 if x else 0\n", "m.py")
    assert fn2.cc == 2


def test_loop_and_except_handler_add_branches():
    (fn,) = iter_symbols(
        "def f(xs):\n    try:\n        for x in xs:\n            pass\n    except ValueError:\n        pass\n", "m.py"
    )
    assert fn.cc == 3  # for + except


def test_nesting_depth_counts_control_flow_blocks():
    (fn,) = iter_symbols(
        "def f(x):\n    if x:\n        for i in x:\n            if i:\n                pass\n    return 1\n",
        "m.py",
    )
    assert fn.nd == 3


def test_fan_out_counts_distinct_call_targets():
    source = "def f(a, b):\n    a.run()\n    a.run()\n    b.stop()\n    return helper(a)\n"
    (fn,) = iter_symbols(source, "m.py")
    # a.run twice counts once; three distinct targets.
    assert fn.fo == 3


def test_fan_out_separates_method_and_module_forms():
    (fn,) = iter_symbols("def f(a):\n    a.run()\n    run()\n    return 1\n", "m.py")
    assert fn.fo == 2


def test_non_structured_exits_exclude_a_final_return():
    (fn,) = iter_symbols("def f(x):\n    if not x:\n        return None\n    return 1\n", "m.py")
    # The early return counts; the tail return does not.
    assert fn.ns == 1


def test_raise_break_continue_all_count_as_exits():
    (fn,) = iter_symbols(
        "def f(x):\n    for i in x:\n        if i:\n            continue\n        break\n    raise ValueError\n",
        "m.py",
    )
    assert fn.ns == 3


def test_class_excludes_method_bodies_from_its_own_scope():
    source = "class C:\n    attr = 1\n    def m(self, x):\n        if x:\n            return 1\n        return 0\n"
    results = iter_symbols(source, "m.py")
    cls = next(r for r in results if r.kind == "class")
    method = next(r for r in results if r.kind == "method")
    assert cls.name == "C"
    # The class is measured over `attr = 1` only: a method's branching must not
    # be charged to the class as well, or every class looks like a hotspot.
    assert cls.cc == 1
    assert cls.fo == 0
    assert method.cc == 2


def test_methods_are_labelled_and_found():
    source = "class C:\n    def a(self):\n        pass\n    def b(self):\n        pass\n"
    kinds = sorted(r.kind for r in iter_symbols(source, "m.py"))
    assert kinds == ["class", "method", "method"]


def test_nested_function_is_its_own_symbol():
    results = iter_symbols("def outer():\n    def inner():\n        return 1\n    return inner\n", "m.py")
    assert sorted(r.name for r in results) == ["inner", "outer"]


def test_loc_spans_the_function():
    (fn,) = iter_symbols("def f():\n    a = 1\n    b = 2\n    return a + b\n", "m.py")
    assert fn.loc == 4


def test_unparseable_source_returns_none_rather_than_guesses():
    # A partially indexed file must be skipped, not measured with invented
    # numbers. `None` distinguishes "could not parse" from "parsed, no functions".
    assert iter_symbols("def broken(:\n    pass\n", "m.py") is None
    assert iter_symbols("    ) garbage ((", "m.py") is None
    # An empty string is valid Python — it parses, it just has no functions.
    assert iter_symbols("", "m.py") == []


def test_source_with_no_functions_is_parsed_but_empty():
    # A module of imports and one call is valid Python with nothing to measure;
    # that must not be reported as unparseable.
    assert iter_symbols("import os\n\nos.path.join('a', 'b')\n", "m.py") == []


def test_scope_statements_drops_methods_for_a_class():
    import ast

    cls = ast.parse("class C:\n    a = 1\n    def m(self):\n        pass\n").body[0]
    assert [type(s).__name__ for s in scope_statements(cls)] == ["Assign"]


# --------------------------------------------------------------------------- #
# LRS — ported exactly
# --------------------------------------------------------------------------- #


def test_weights_match_the_ported_defaults():
    assert RISK_WEIGHTS == {"cc": 1.0, "nd": 0.8, "fo": 0.6, "ns": 0.7}


def test_transforms_are_logarithmic_and_capped():
    metrics = FunctionMetrics("f", "function", "m.py", 10, cc=8, nd=3, fo=4, ns=2)
    components, _lrs, _band = analyze(metrics)
    # R_cc = min(log2(9), 6) = 3.17
    assert components.r_cc == pytest.approx(min(math.log2(9), 6.0))
    assert components.r_cc < 6
    # R_nd and R_ns are plain caps, not logs.
    assert components.r_nd == 3
    assert components.r_ns == 2


def test_transforms_saturate_at_their_caps():
    huge = FunctionMetrics("f", "function", "m.py", 10_000, cc=10_000, nd=10_000, fo=10_000, ns=10_000)
    components, lrs, band = analyze(huge)
    assert components.r_cc == 6.0
    assert components.r_nd == 8.0
    assert components.r_fo == 6.0
    assert components.r_ns == 6.0
    assert lrs == pytest.approx(MAX_LRS)
    assert band.name == "critical"


def test_lrs_uses_the_ported_weights():
    metrics = FunctionMetrics("f", "function", "m.py", 10, cc=7, nd=4, fo=3, ns=2)
    components, lrs, _ = analyze(metrics)
    expected = (
        RISK_WEIGHTS["cc"] * components.r_cc
        + RISK_WEIGHTS["nd"] * components.r_nd
        + RISK_WEIGHTS["fo"] * components.r_fo
        + RISK_WEIGHTS["ns"] * components.r_ns
    )
    assert lrs == pytest.approx(expected)


def test_growth_is_sublinear_so_one_function_cannot_dominate():
    """The transforms exist for this: a 10x more complex function must not
    score 10x the risk, or the ranking is really just a complexity ranking."""
    simple = FunctionMetrics("a", "function", "m.py", 10, cc=2, nd=0, fo=0, ns=0)
    complex_ = FunctionMetrics("b", "function", "m.py", 100, cc=64, nd=4, fo=8, ns=3)
    _, low, _ = analyze(simple)
    _, high, _ = analyze(complex_)
    assert high > low
    # 32x the complexity, well under 32x the score.
    assert high / low < 12


@pytest.mark.parametrize(
    ("lrs", "expected"),
    [
        (0.0, "low"),
        (MODERATE_AT - 0.01, "low"),
        (MODERATE_AT, "moderate"),
        (HIGH_AT - 0.01, "moderate"),
        (HIGH_AT, "high"),
        (CRITICAL_AT - 0.01, "high"),
        (CRITICAL_AT, "critical"),
        (20.0, "critical"),
    ],
)
def test_band_thresholds_match_the_ported_values(lrs, expected):
    assert band_for(lrs).name == expected


def test_health_is_100_for_an_all_low_codebase():
    assert health_from_bands({"low": 50}, 50) == 100


def test_health_drops_with_worse_bands_and_stays_in_range():
    # Weighted penalty per band: 0 / 0.35 / 0.7 / 1.0, scaled by the share of
    # symbols in that band.
    assert health_from_bands({"low": 100}, 100) == 100
    assert health_from_bands({"moderate": 100}, 100) == 65
    assert health_from_bands({"high": 100}, 100) == 30
    assert health_from_bands({"critical": 100}, 100) == 0
    # A tenth of symbols merely moderate costs a third of a percent of one band.
    assert health_from_bands({"low": 90, "moderate": 10}, 100) == 96


def test_health_of_nothing_is_100():
    assert health_from_bands({}, 0) == 100


# --------------------------------------------------------------------------- #
# Service
# --------------------------------------------------------------------------- #


class FakeChunk:
    def __init__(self, text, path, symbol=None, repo="acme/widgets"):
        self.text = text
        self.source_id = "repo:acme/widgets"
        meta = {"path": path, "repo": repo, "url": "https://github.com/acme/widgets", "source_type": "github"}
        if symbol is not None:
            meta["symbol"] = symbol
        self.metadata = meta


class FakeFaiss:
    def __init__(self, chunks):
        self._chunks = chunks

    async def get_chunks_by_source_id(self, source_id):
        return list(self._chunks)


def _service(tmp_path, chunks):
    return HealthService(store=HealthStore(tmp_path / "h.db"), faiss=FakeFaiss(chunks))


COMPLEX = (
    "def tangled(xs):\n"
    + "".join(
        f"    if x == {i}:\n        for y in xs:\n            try:\n                y.run()\n"
        f"            except ValueError:\n                continue\n            break\n        return {i}\n"
        for i, x in enumerate(["a", "b", "c", "d", "e", "f", "g", "h"], start=1)
    )
    + "    return None\n"
)

SIMPLE = "def add(a, b):\n    return a + b\n"


@pytest.fixture
def chunks():
    return [
        FakeChunk(COMPLEX, "app/core.py", "tangled"),
        FakeChunk(SIMPLE, "app/util.py", "add"),
        FakeChunk("body without a symbol", "app/mod.py"),
        FakeChunk("x", "node_modules/pkg/index.js", "whatever"),
    ]


@pytest.mark.asyncio
async def test_scan_ranks_the_complex_symbol_first(tmp_path, chunks):
    result = await _service(tmp_path, chunks).scan("p1", "repo:acme/widgets")
    assert result["repository"] == "acme/widgets"
    assert result["symbol_count"] == 2  # the symbol-less chunk is not measured
    assert result["hotspots"][0]["name"] == "tangled"
    assert result["hotspots"][0]["path"] == "app/core.py"
    assert result["hotspots"][0]["band"] in ("high", "critical")
    assert result["hotspots"][0]["lrs"] > result["hotspots"][1]["lrs"]
    # 0 <= health <= 100
    assert 0 <= result["health"] <= 100


@pytest.mark.asyncio
async def test_every_hotspot_carries_its_working(tmp_path, chunks):
    result = await _service(tmp_path, chunks).scan("p1", "repo:acme/widgets")
    for row in result["hotspots"]:
        for key in ("cc", "nd", "fo", "ns", "r_cc", "r_nd", "r_fo", "r_ns", "lrs"):
            assert key in row, key
        assert row["band"] in ("low", "moderate", "high", "critical")


@pytest.mark.asyncio
async def test_weights_are_published_with_the_result(tmp_path, chunks):
    result = await _service(tmp_path, chunks).scan("p1", "repo:acme/widgets")
    # The score must be reproducible by the reader, so the weights travel with it.
    assert result["weights"] == {"cc": 1.0, "nd": 0.8, "fo": 0.6, "ns": 0.7}


@pytest.mark.asyncio
async def test_vendored_directories_are_excluded(tmp_path, chunks):
    result = await _service(tmp_path, chunks).scan("p1", "repo:acme/widgets")
    assert all("node_modules" not in row["path"] for row in result["files"])


@pytest.mark.asyncio
async def test_largest_files_include_non_python(tmp_path, chunks):
    result = await _service(tmp_path, chunks).scan("p1", "repo:acme/widgets")
    paths = {row["path"] for row in result["largest_files"]}
    assert "node_modules/pkg/index.js" not in paths
    assert any(row["path"].endswith(".js") is False for row in result["largest_files"])


@pytest.mark.asyncio
async def test_coverage_limit_is_stated_not_hidden(tmp_path, chunks):
    result = await _service(tmp_path, chunks).scan("p1", "repo:acme/widgets")
    assert result["measured_languages"] == ["Python"]
    note = result["coverage_note"]
    # The defining insight of the tool is complexity AND churn; churn is not
    # measurable here, so the report has to say so rather than imply it.
    assert "Python" in note
    assert "Change frequency" in note


@pytest.mark.asyncio
async def test_test_files_are_excluded_from_hotspots(tmp_path):
    chunks = [
        FakeChunk(COMPLEX, "tests/test_core.py", "tangled"),
        FakeChunk(SIMPLE, "app/util.py", "add"),
    ]
    result = await _service(tmp_path, chunks).scan("p1", "repo:acme/widgets")
    # The risky function is in a test; it should not top the report.
    assert all("tests/" not in row["path"] for row in result["hotspots"])


@pytest.mark.asyncio
async def test_scan_is_cached_by_fingerprint(tmp_path, chunks):
    service = _service(tmp_path, chunks)
    first = await service.scan("p1", "repo:acme/widgets")
    second = await service.scan("p1", "repo:acme/widgets")
    assert second["cached"] is True
    assert second["elapsed_ms"] == 0
    assert second["fingerprint"] == first["fingerprint"]


@pytest.mark.asyncio
async def test_new_file_set_invalidates_the_cache(tmp_path, chunks):
    await _service(tmp_path, chunks).scan("p1", "repo:acme/widgets")
    grown = [*chunks, FakeChunk(SIMPLE, "app/extra.py", "add")]
    assert (await _service(tmp_path, grown).scan("p1", "repo:acme/widgets"))["cached"] is False


@pytest.mark.asyncio
async def test_rescan_bypasses_the_cache(tmp_path, chunks):
    service = _service(tmp_path, chunks)
    await service.scan("p1", "repo:acme/widgets")
    assert (await service.scan("p1", "repo:acme/widgets", refresh=True))["cached"] is False


@pytest.mark.asyncio
async def test_non_python_repo_reports_honestly_rather_than_faking(tmp_path):
    chunks = [FakeChunk("const a = 1\n" * 50, "src/app.js", "a")]
    result = await _service(tmp_path, chunks).scan("p1", "repo:acme/widgets")
    assert result["symbol_count"] == 0
    # Nothing measured is `None`, not 100: a repository that was never analysed
    # is not a healthy one, and a perfect score would read as a clean bill.
    assert result["health"] is None
    assert result["measured_languages"] == []
    assert "No per-function risk" in result["summary"]
    # It still reports the file, by size.
    assert result["largest_files"]


@pytest.mark.asyncio
async def test_empty_index_raises_a_clear_error(tmp_path):
    with pytest.raises(HealthError, match="no indexed files"):
        await _service(tmp_path, []).scan("p1", "repo:acme/widgets")


@pytest.mark.asyncio
async def test_get_returns_none_before_a_scan(tmp_path, chunks):
    assert await _service(tmp_path, chunks).get("unknown") is None


# --------------------------------------------------------------------------- #
# Both index chunking modes
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_measures_symbol_chunked_index(tmp_path):
    """A repository indexed with the code chunker stores one chunk per function."""
    chunks = [
        FakeChunk(COMPLEX, "app/core.py", "tangled"),
        FakeChunk(SIMPLE, "app/util.py", "add"),
    ]
    result = await _service(tmp_path, chunks).scan("p1", "repo:acme/widgets")
    assert result["symbol_count"] == 2
    assert result["measured_files"] == 2
    assert result["unparsed_files"] == 0
    assert result["hotspots"][0]["name"] == "tangled"


@pytest.mark.asyncio
async def test_measures_reassembled_text_chunked_index(tmp_path):
    """An older index holds whole files split on text-chunk boundaries.

    The splitter breaks on blank lines before anything finer, so a file split
    into a few pieces that land on those boundaries reassembles exactly. This is
    the path that makes the feature work on a repository indexed before the
    code chunker was used for GitHub sources.
    """
    # A blank line between the two defs, as real source has and as the
    # splitter's first separator uses.
    whole = SIMPLE + "\n" + COMPLEX
    head, _, tail = whole.partition("\n\ndef tangled")
    assert head and tail, "expected to split on the blank line before the second def"
    chunks = [
        FakeChunk(head, "app/core.py"),
        FakeChunk("def tangled" + tail, "app/core.py"),
    ]
    result = await _service(tmp_path, chunks).scan("p1", "repo:acme/widgets")
    assert result["symbol_count"] == 2
    assert result["measured_files"] == 1
    assert result["unparsed_files"] == 0
    assert {row["name"] for row in result["hotspots"]} == {"add", "tangled"}


@pytest.mark.asyncio
async def test_unparseable_file_is_skipped_and_counted_not_guessed(tmp_path):
    """A file that will not parse is reported as skipped, never measured."""
    chunks = [
        FakeChunk("    return 1\n    ) garbage ((", "app/broken.py"),
        FakeChunk(SIMPLE, "app/util.py", "add"),
    ]
    result = await _service(tmp_path, chunks).scan("p1", "repo:acme/widgets")
    assert result["unparsed_files"] == 1
    # Only the parseable function is reported.
    assert result["symbol_count"] == 1
    assert all(row["path"] != "app/broken.py" for row in result["hotspots"])
    assert "re-ingesting" in result["coverage_note"]


@pytest.mark.asyncio
async def test_skipped_files_do_not_count_as_low_risk(tmp_path):
    """A file that could not be measured must not dilute the health score.

    Counting unparsed files as zero-risk would make a broken index look healthy,
    which is the opposite of what the number is for.
    """
    broken_only = [FakeChunk("   (( garbage", "app/broken.py")]
    result = await _service(tmp_path, broken_only).scan("p1", "repo:acme/widgets")
    assert result["symbol_count"] == 0
    assert result["unparsed_files"] == 1
    # A file that could not be read must not be silently scored as healthy.
    assert result["health"] is None
    assert "No per-function risk" in result["summary"]
