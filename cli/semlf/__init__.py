"""semlf — the repository CLI layer (ADR-0004).

Owns subcommand routing; git snapshot selection arrives in v0.6b.
It never re-implements analysis:
every check delegates to the portable core,
and the version is the core's version.
In-process concurrent calls are not supported:
the core parses invocation state from process globals,
and semlf is a process-per-invocation command.
"""
