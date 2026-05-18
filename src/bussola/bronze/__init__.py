"""Bronze layer.

This package is intentionally empty at the top level: each extractor module
(deputies, parties, propositions, votings) is imported directly by its own
runner script. This avoids coupling - adding or removing an endpoint does
not require changes to any shared registry.
"""
