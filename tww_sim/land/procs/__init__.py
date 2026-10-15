"""land/procs - the LandState proc bodies, one mixin per proc group.

Each module defines a ``_*Mixin`` carrying the methods for its proc family; ``state.LandState``
multi-inherits them all (``_MoveMixin`` first, as the MRO base). Cross-proc calls (e.g. the
arbiter ``_check_next_mode`` -> the turn procs) bind to the single composed ``self`` at class
definition, so there is no import cycle between proc modules. See ../land.py for the public shim.
"""
