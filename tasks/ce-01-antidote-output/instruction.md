A git wrapper on PATH writes progress to stdout even for `git --quiet`, and antidote is leaking that text into generated plugin scripts. Keep generated scripts valid: plugin-loading commands must remain on stdout, wrapper progress and diagnostics must go to stderr, and git failures must still propagate.

Investigate the repository, add focused regression coverage, and commit the finished change. You may use `ask_user` if consequential scope is genuinely unclear.
