"""Deterministic renderers.

Every renderer is a pure function of approved content. No renderer calls
a language model, a network service, or a clock-dependent source: two
builds of the same approved bytes produce the same output, and both
carry that source hash so a printed handout and an app screen can be
checked against each other.
"""
