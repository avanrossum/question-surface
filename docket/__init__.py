"""Docket — batch question collection.

Serialized question-and-answer in chat is the wrong shape for architecture work:
a fork with eight dependent questions becomes eight round trips, each one losing
the context of the last. This package renders a questionnaire spec as a local
web form, collects every answer in one pass, and writes the result back to disk
in a form an agent reads directly.

Entry point is `docket.cli:main`, exposed as the `docket` command.
"""

__version__ = "2.2.0"
