"""Shared value types for the tech stack scan.

Kept separate from :mod:`app.techstack.rules` because the generated rule table
and the rule index both need :class:`TechRule`, and a rule table that imported
the index that reads it would be circular.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = ["TechRule", "normalise_path"]


def normalise_path(path: str) -> str:
    """Drop a leading ``./`` and nothing else.

    ``str.lstrip("./")`` looks like it does this but strips a *set* of
    characters, so ``.github/workflows`` comes back as ``github/workflows`` and
    every rule keyed on a dotfile directory silently stops matching.
    """
    path = path.strip()
    if path.startswith("./"):
        return path[2:]
    return path


@dataclass(frozen=True)
class TechRule:
    """One technology, and the evidence that gives it away.

    ``key`` is a stable identity rather than a display string, because the
    service graph uses it to recognise that two folders refer to the same
    technology and should be merged into one component.

    A rule fires on any one of three kinds of evidence, which is stack-analyser's
    two-tier model extended to cover configuration files: a literal dependency
    name, a dependency-name pattern, or the presence of a file by a given name.
    """

    key: str
    name: str
    kind: str
    #: Package managers whose manifests can carry this tech.  Empty means the
    #: rule is evidence of a file existing rather than of a dependency, and the
    #: sentinel ``"*"`` means any manager.
    managers: tuple[str, ...] = ()
    #: Lower-cased literal dependency names.
    exact: tuple[str, ...] = ()
    #: Dependency-name patterns, carried over from stack-analyser's regex rules.
    patterns: tuple[str, ...] = ()
    #: Repository-relative paths whose presence implies the tech, e.g.
    #: ``.circleci`` or ``Jenkinsfile``.
    files: tuple[str, ...] = ()

    def matches_manager(self, manager: str) -> bool:
        return not self.managers or "*" in self.managers or manager in self.managers

    def matches_path(self, path: str) -> bool:
        """True when *path* is one of this rule's evidence files.

        A rule may name a directory (``.circleci``) or a file
        (``circle.yml``), and either may sit at any depth, so
        ``services/api/Jenkinsfile`` matches a rule naming ``Jenkinsfile`` and
        ``apps/web/.circleci/config.yml`` matches one naming ``.circleci``.
        """
        path = normalise_path(path)
        basename = path.rsplit("/", 1)[-1]
        padded = f"/{path}/"
        for candidate in self.files:
            candidate = normalise_path(candidate)
            if path == candidate or basename == candidate or path.endswith(f"/{candidate}"):
                return True
            # A rule naming a directory matches the files inside it.
            if path.startswith(f"{candidate}/") or f"/{candidate}/" in padded:
                return True
            if any(ch in candidate for ch in "*?["):
                expanded = candidate.replace("**", "\x00").replace("*", "[^/]*").replace("\x00", ".*")
                if re.fullmatch(expanded, path) or re.search(expanded, path):
                    return True
        return False
