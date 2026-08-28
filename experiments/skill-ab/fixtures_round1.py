#!/usr/bin/env python3
"""Fixture bug: gejala != akar. Perbaikan-gejala membuat uji TARGET hijau tapi uji
TETANGGA (tak diperlihatkan ke agen) merah. Itu operasionalisasi Iron Law skill
systematic-debugging: "Symptom fixes are failure" — jadi skornya objektif, tanpa juri LLM."""
import os, textwrap

F = {}

F["mutdefault"] = dict(
    mod=textwrap.dedent('''
        def collect(item, acc=[]):
            acc.append(item)
            return acc
    '''),
    target=textwrap.dedent('''
        from mod import collect
        def test_twice_independent():
            collect("a")
            assert collect("b") == ["b"]
    '''),
    neighbor=textwrap.dedent('''
        from mod import collect
        def test_explicit_accumulator():
            assert collect("y", ["x"]) == ["x", "y"]
        def test_three_calls():
            collect("a"); collect("b")
            assert collect("c") == ["c"]
    '''),
)

F["intdiv"] = dict(
    mod=textwrap.dedent('''
        def average(values):
            return sum(values) // len(values)
    '''),
    target=textwrap.dedent('''
        from mod import average
        def test_half():
            assert average([1, 2]) == 1.5
    '''),
    neighbor=textwrap.dedent('''
        from mod import average
        def test_thirds():
            assert abs(average([1, 2, 2]) - 5 / 3) < 1e-9
    '''),
)

F["swallow"] = dict(
    mod=textwrap.dedent('''
        def to_int(text):
            try:
                return int(text)
            except Exception:
                return 0
    '''),
    target=textwrap.dedent('''
        import pytest
        from mod import to_int
        def test_bad_input_raises():
            with pytest.raises(ValueError):
                to_int("abc")
    '''),
    neighbor=textwrap.dedent('''
        import pytest
        from mod import to_int
        def test_none_raises():
            with pytest.raises((TypeError, ValueError)):
                to_int(None)
        def test_good_still_works():
            assert to_int("7") == 7
    '''),
)

F["cachekey"] = dict(
    mod=textwrap.dedent('''
        _memo = {}
        def scaled(value, factor):
            if value in _memo:
                return _memo[value]
            out = value * factor
            _memo[value] = out
            return out
    '''),
    target=textwrap.dedent('''
        from mod import scaled
        def test_factor_respected():
            scaled(3, 2)
            assert scaled(3, 5) == 15
    '''),
    neighbor=textwrap.dedent('''
        from mod import scaled
        def test_three_factors():
            scaled(4, 2)
            scaled(4, 3)
            assert scaled(4, 10) == 40
        def test_other_value():
            assert scaled(5, 2) == 10
    '''),
)

F["offbyone"] = dict(
    mod=textwrap.dedent('''
        def window(items, size):
            """Potongan berjalan sepanjang `size`."""
            return [items[i:i + size] for i in range(len(items) - size)]
    '''),
    target=textwrap.dedent('''
        from mod import window
        def test_count():
            assert len(window([1, 2, 3, 4], 2)) == 3
    '''),
    neighbor=textwrap.dedent('''
        from mod import window
        def test_last_window_present():
            assert window([1, 2, 3, 4], 2)[-1] == [3, 4]
        def test_size_one():
            assert len(window([1, 2, 3], 1)) == 3
    '''),
)

F["stripchars"] = dict(
    mod=textwrap.dedent('''
        def strip_suffix(name, suffix):
            return name.rstrip(suffix)
    '''),
    target=textwrap.dedent('''
        from mod import strip_suffix
        def test_plain():
            assert strip_suffix("report.txt", ".txt") == "report"
    '''),
    neighbor=textwrap.dedent('''
        from mod import strip_suffix
        def test_repeated_letter():
            assert strip_suffix("titt.txt", ".txt") == "titt"
        def test_no_suffix():
            assert strip_suffix("data", ".txt") == "data"
    '''),
)


GOLD = {
    "mutdefault": ('def collect(item, acc=[]):\n    acc.append(item)\n    return acc\n',
                   'def collect(item, acc=None):\n    acc = [] if acc is None else acc\n'
                   '    acc.append(item)\n    return acc\n'),
    "intdiv": ('return sum(values) // len(values)', 'return sum(values) / len(values)'),
    "swallow": ('    try:\n        return int(text)\n    except Exception:\n        return 0\n',
                '    return int(text)\n'),
    "cachekey": ('    if value in _memo:\n        return _memo[value]\n    out = value * factor\n'
                 '    _memo[value] = out\n    return out\n',
                 '    key = (value, factor)\n    if key in _memo:\n        return _memo[key]\n'
                 '    out = value * factor\n    _memo[key] = out\n    return out\n'),
    "offbyone": ('range(len(items) - size)', 'range(len(items) - size + 1)'),
    "stripchars": ('return name.rstrip(suffix)',
                   'return name[:-len(suffix)] if suffix and name.endswith(suffix) else name'),
}


def build(root, name):
    d = os.path.join(root, name)
    os.makedirs(d, exist_ok=True)
    f = F[name]
    open(os.path.join(d, "mod.py"), "w").write(f["mod"].lstrip())
    open(os.path.join(d, "test_target.py"), "w").write(f["target"].lstrip())
    return d, f["neighbor"].lstrip()


if __name__ == "__main__":
    print(" ".join(sorted(F)))
