"""Performance-test data preparation for the homomorphic e-voting backend.

This package prepares *staging* data for a later load test. It only ever talks to
the public HTTP API — it never opens a database connection, and it has no delete,
cleanup, reset or truncate mode. See README.md for the safety boundaries.
"""
