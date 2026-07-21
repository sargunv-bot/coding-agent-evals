A git wrapper on PATH writes progress to stdout even for `git --quiet`, and antidote is leaking that text into generated plugin scripts. Fix it without hiding useful diagnostics.

Investigate the repository, add focused regression coverage, and commit the finished change.
