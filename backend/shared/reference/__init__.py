"""
shared/reference - statutory data that belongs to no domain.

The distinction from shared/config.py: that file holds *this application's* choices
(benchmark mappings, category colours, peer universes). This package holds facts about
Indian tax law, which are true regardless of which domain is asking.

The test for whether something belongs here: if two domains would otherwise each need
their own copy, and neither is the natural owner, it goes here.
"""
