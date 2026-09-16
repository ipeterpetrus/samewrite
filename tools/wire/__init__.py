"""The decoding boundary.

This is the ONLY package allowed to touch raw JSON values. Everything it returns is validated: a
caller that holds a typed evidence object holds something this package established completely.
Nothing here is an evidence algorithm, and nothing in `evidence` imports a raw value from here.
"""
