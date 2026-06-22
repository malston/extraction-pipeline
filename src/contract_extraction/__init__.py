"""Contract-extraction pipeline -- CCA Domain 4 build exercise.

A batch extraction pipeline that forces its output through a `tool_use` JSON
schema, classifies risk by categorical criteria (never confidence), retries
*format* failures with the exact violated constraint, and verifies each record
with an independent reviewer pass. Truthful absence -- a document silent on its
governing law -- survives end to end as `null`/`NOT_SPECIFIED`, never a guess.
"""
