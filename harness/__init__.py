"""Live-Dolphin research + validation harness for the tww_sim player-physics sim.

Everything here drives a running Dolphin instance via ``dolphin_mem`` (which lives in the parent
``../tools/`` and is reached through the ``# locate tools/`` sys.path bootstrap). This layer is
optional and is NOT imported by the pure-offline :mod:`tww_sim` core — keeping the core
shareable without an emulator. Subpackages: ``capture`` (read live game state), ``validate``
(sim-vs-live checks), ``dtm`` (movie authoring/playback), ``search`` (live-grounded planning).

Dolphin command reference: ../tools/DOLPHIN_CONTROL.md (dolphin_mem.py -- the single source of truth).
"""
