"""modurn — a declarative mod manager for OpenMW.

The public surface is intentionally small for the MVP. The one seam that
matters for future re-architecting is `modurn.sources`: everything else in
the package is backend-agnostic and talks to mod backends only through the
`ModSource` protocol.
"""

__version__ = "0.1.0"
