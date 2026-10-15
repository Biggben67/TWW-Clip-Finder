"""THE PER-SESSION GATE IS A 2-MINUTE BUDGET AND A 1-SECOND TEST, ENFORCED HERE (session 132).

Dereck's rule, and the reasoning behind it: a functionality test does not take a second. The cases
that did were not functionality tests at all -- they re-ran the planner, the fan or the camera pool at
test time and asserted the measurement that came back, so the default gate had drifted to 29 minutes
of re-derived research. That gets marked `@pytest.mark.slow` and still runs under `pytest -m slow`;
what stays is what a gate is for.

The conventions in this repo hold only when they are machine-checked, so both halves are:

  * ANY unmarked test costing more than `PER_TEST_BUDGET_S` fails the run, and is named. This is the
    one that catches drift on the day it is introduced rather than when the total finally crosses.
  * The DEFAULT selection as a whole must finish inside `TOTAL_BUDGET_S`.

A test's cost here is setup + call + teardown, deliberately: a module fixture is paid by whichever
test asks for it first, so charging only the call would let an expensive fixture hide behind a cheap
assertion -- and marking that test would merely hand the bill to the next one in the file.

Both checks run on the DEFAULT selection only. A subset run (`pytest tests/test_x.py`) is exempt on
purpose: its first test absorbs the process's whole cold start -- import, native module load, the
first fixture -- which reads as ~0.5 s of fiction and would fail honest tests. The full run amortises
that once. A `-m slow` run is exempt too; it IS the heavy selection. A slower machine can raise either
budget with `TWW_TEST_BUDGET_S` / `TWW_TEST_PER_BUDGET_S`.
"""
import os
import time

#: The RULE is one second. The gate trips at 1.5 because it must not flap: a band of tests sits at
#: 0.9-1.1 s and at a hard 1.0 a different two cross it every run, which is noise, not drift.
TOTAL_BUDGET_S = float(os.environ.get("TWW_TEST_BUDGET_S", "120"))
PER_TEST_BUDGET_S = float(os.environ.get("TWW_TEST_PER_BUDGET_S", "1.5"))

_cost = {}
_marked = set()
_t0 = [None]


def _running_slow(config):
    return "slow" in config.getoption("markexpr", "") and "not slow" != config.getoption("markexpr")


def _is_default_gate(config):
    if config.getoption("collectonly", False):
        return False
    root = str(config.rootpath)
    want = sorted(os.path.normcase(os.path.abspath(os.path.join(root, p)))
                  for p in config.getini("testpaths"))
    have = sorted(os.path.normcase(os.path.abspath(a)) for a in config.args)
    return bool(want) and want == have


def pytest_configure(config):
    _t0[0] = time.time()
    config._tww_slow_run = _running_slow(config)
    config._tww_default_gate = _is_default_gate(config)


def pytest_runtest_logreport(report):
    _cost[report.nodeid] = _cost.get(report.nodeid, 0.0) + report.duration
    if "slow" in getattr(report, "keywords", {}):
        _marked.add(report.nodeid)


def _verdict(config):
    """(over-budget tests, ran-late) for this run, or (None, False) when the budget does not apply.

    Recomputed by each hook rather than cached by one for the other: pytest does not order
    `pytest_sessionfinish` against the terminal reporter's own, so a flag set while printing is not
    reliably visible when the exit status is decided -- which is exactly how the first version printed
    the violation and still exited 0."""
    if config._tww_slow_run or not config._tww_default_gate:
        return None, False
    over = sorted(((c, n) for n, c in _cost.items()
                   if c > PER_TEST_BUDGET_S and n not in _marked), reverse=True)
    return over, (time.time() - _t0[0]) > TOTAL_BUDGET_S


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    over, late = _verdict(config)
    if not over and not late:
        return
    elapsed = time.time() - _t0[0]
    terminalreporter.section("TEST-BUDGET GATE", red=True)
    if late:
        terminalreporter.line("the default suite took %.0f s against a %.0f s hard budget"
                              % (elapsed, TOTAL_BUDGET_S))
    if over:
        terminalreporter.line("%d test(s) over the %.1f s per-test budget -- a functionality test does"
                              " not take a second. Mark them @pytest.mark.slow (they still run under"
                              " `pytest -m slow`), or assert against a banked artefact instead of"
                              " re-running the search:" % (len(over), PER_TEST_BUDGET_S))
        for cost, nodeid in over[:20]:
            terminalreporter.line("  %6.1f s  %s" % (cost, nodeid))
        if len(over) > 20:
            terminalreporter.line("  ... and %d more" % (len(over) - 20))


def pytest_sessionfinish(session, exitstatus):
    over, late = _verdict(session.config)
    if (over or late) and exitstatus == 0:
        session.exitstatus = 1
