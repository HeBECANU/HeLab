"""App updates (``roadmaps/app-updates.md``): the version status, the check for a newer release or a newer
green commit on HeLab's branch (stage 1), and the updater that moves a source checkout to it and starts
HeLab again (stage 2, source only).

- ``versions`` and ``github`` are pure (no Qt): the status, the channels, GitHub's replies, the CI rule
  and the check's requests, as a generator any transport drives.
- ``settings``, ``check``, ``launch`` and ``dialog`` are HeLab's side (Qt).
- ``updater`` is a standard-library script, copied out of the checkout and run by the base Python: it
  imports nothing from HeLab.
"""
