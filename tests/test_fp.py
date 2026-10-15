"""Unit tests for superswim.fp - the FMA-faithful PPC 750CL single-precision ops.

Locks two properties: (1) the fused ops differ from separate-rounding where they must
(the whole reason fp.py exists vs sim.f32), and (2) the f64-intermediate fmadds equals the
struct-emulated correctly-rounded single FMA bit-for-bit over random + edge inputs. Pure offline.
"""
import struct
import random

import pytest

from tww_sim.core import fp


def _to_f32(x):
    return struct.unpack('f', struct.pack('f', x))[0]


def _ref_fma(a, b, c):
    """Reference correctly-rounded single FMA via struct round of the f64 product-sum.
    Same theorem fp.fmadds relies on; independent implementation for cross-check."""
    return _to_f32(a * b + c)


class TestFused:
    def test_all_outputs_are_f32(self):
        a, b, c = 1.1, 2.2, 3.3
        for v in (fp.fmuls(a, b), fp.fadds(a, b), fp.fsubs(a, b), fp.fdivs(a, b),
                  fp.fmadds(a, b, c), fp.fmsubs(a, b, c),
                  fp.fnmadds(a, b, c), fp.fnmsubs(a, b, c)):
            assert v == _to_f32(v)

    def test_fma_differs_from_separate_rounding(self):
        # The whole point of fp.py: the fused op keeps the product's low mantissa bits that a
        # separate f32(f32(a*b)+c) drops. Such triples are common; find one and assert it exists.
        random.seed(0xBEEF)
        found = False
        for _ in range(100000):
            a = _to_f32(random.uniform(-10, 10))
            b = _to_f32(random.uniform(-10, 10))
            c = _to_f32(random.uniform(-10, 10))
            if fp.fmadds(a, b, c) != fp.f32(fp.fmuls(a, b) + c):
                found = True
                break
        assert found, "expected some triple where fused FMA != separate rounding"

    def test_fnmsub_is_negated_fmsub(self):
        for _ in range(1000):
            a = _to_f32(random.uniform(-100, 100))
            b = _to_f32(random.uniform(-100, 100))
            c = _to_f32(random.uniform(-100, 100))
            assert fp.fnmsubs(a, b, c) == -fp.fmsubs(a, b, c)
            assert fp.fnmadds(a, b, c) == -fp.fmadds(a, b, c)

    def test_fmadds_matches_reference_fma(self):
        random.seed(0xC0FFEE)
        for _ in range(50000):
            a = _to_f32(random.uniform(-1e3, 1e3))
            b = _to_f32(random.uniform(-1e3, 1e3))
            c = _to_f32(random.uniform(-1e3, 1e3))
            assert fp.fmadds(a, b, c) == _ref_fma(a, b, c)
            assert fp.fmsubs(a, b, c) == _ref_fma(a, b, -c)

    def test_edge_values(self):
        # zero, negatives, tiny; fused ops stay finite/correct
        assert fp.fmadds(0.0, 5.0, 3.0) == 3.0
        assert fp.fmadds(2.0, 3.0, 0.0) == 6.0
        assert fp.fmsubs(2.0, 3.0, 6.0) == 0.0
        assert fp.fnmsubs(2.0, 3.0, 6.0) == 0.0  # -(6-6) == 0
