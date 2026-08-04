import fnmatch

from folderscribe.domain.models import ExclusionRule


class ExclusionMatcher:
    def __init__(self, rules: tuple[ExclusionRule, ...]) -> None:
        self._rules = rules

    def is_excluded(self, relative_path: str) -> tuple[bool, ExclusionRule | None]:
        for rule in self._rules:
            if "/" not in rule.pattern:
                basename = relative_path.rsplit("/", 1)[-1]
                if fnmatch.fnmatch(basename, rule.pattern):
                    return True, rule
            else:
                if fnmatch.fnmatch(relative_path, rule.pattern):
                    return True, rule
        return False, None
