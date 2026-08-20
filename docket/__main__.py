"""`python -m docket`.

The detached interview server is spawned this way rather than by file path, so
it behaves identically whether Docket was installed or is being run from a
clone.
"""

from .cli import main

raise SystemExit(main())
