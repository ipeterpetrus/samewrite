"""The typed evidence kernel: validated internal objects and the pure algorithms over them.

Nothing in this package may accept a raw mapping as a trusted evidence value. Raw wire data is
decoded exactly once, in the `wire` package, and what comes out is what the algorithms consume.
"""
