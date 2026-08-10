"""semlf — the repository CLI layer.

Owns git snapshot selection and subcommand routing.
Config discovery lives in the portable core, per roadmap section 8.2, and is reused from here.
It never re-implements analysis: every check delegates to the portable core.
"""

__version__ = "0.0.0-poc"
