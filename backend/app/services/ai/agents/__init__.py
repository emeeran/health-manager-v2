"""Record agents: deterministic history assembly + claim-level audit.

Two roles, no agent framework:

``history``  — builds the member's whole-record evidence index in code.
``auditor``  — extracts claims from a narrative, verifies them against that
               index, and (only when consent allows) checks external facts
               with the household's SearXNG instance.

Both run behind the existing ``verifications`` row so the UI can poll the
audit without changing the report stream.
"""
