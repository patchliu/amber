"""Small, explicit Amber Spec subset used by the local registry MVP."""

from .core import SpecError, canonical_json, digest, match_spec, validate_spec

__all__ = ["SpecError", "canonical_json", "digest", "match_spec", "validate_spec"]
