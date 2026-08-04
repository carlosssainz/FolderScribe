from folderscribe.domain.exclusion import ExclusionMatcher
from folderscribe.domain.models import ExclusionRule, RuleSource


def _rule(pattern: str) -> ExclusionRule:
    return ExclusionRule(pattern=pattern, source=RuleSource.USER)


class TestExclusionMatcher:
    def test_exact_name_match(self) -> None:
        matcher = ExclusionMatcher((_rule("secreto.txt"),))
        matched, rule = matcher.is_excluded("secreto.txt")
        assert matched
        assert rule is not None
        assert rule.pattern == "secreto.txt"

    def test_exact_name_at_depth(self) -> None:
        matcher = ExclusionMatcher((_rule("secreto.txt"),))
        matched, _ = matcher.is_excluded("subdir/secreto.txt")
        assert matched

    def test_wildcard_at_any_depth(self) -> None:
        matcher = ExclusionMatcher((_rule("*.tmp"),))
        assert matcher.is_excluded("file.tmp")[0]
        assert matcher.is_excluded("sub/file.tmp")[0]
        assert matcher.is_excluded("a/b/c/file.tmp")[0]
        assert not matcher.is_excluded("file.txt")[0]

    def test_wildcard_no_match(self) -> None:
        matcher = ExclusionMatcher((_rule("*.tmp"),))
        assert not matcher.is_excluded("notes.txt")[0]
        assert not matcher.is_excluded("tmp")[0]

    def test_relative_path_pattern(self) -> None:
        matcher = ExclusionMatcher((_rule("privado/*.pdf"),))
        assert matcher.is_excluded("privado/doc.pdf")[0]
        assert not matcher.is_excluded("publico/doc.pdf")[0]
        assert not matcher.is_excluded("privado/leeme.txt")[0]

    def test_directory_whole_name(self) -> None:
        matcher = ExclusionMatcher((_rule("node_modules"),))
        assert matcher.is_excluded("node_modules")[0]
        assert matcher.is_excluded("sub/node_modules")[0]
        assert not matcher.is_excluded("node")[0]

    def test_directory_with_trailing_star(self) -> None:
        matcher = ExclusionMatcher((_rule("privado/**"),))
        assert matcher.is_excluded("privado/file.pdf")[0]
        assert matcher.is_excluded("privado/sub/file.txt")[0]

    def test_case_sensitivity(self) -> None:
        matcher = ExclusionMatcher((_rule("*.TMP"),))
        assert matcher.is_excluded("file.TMP")[0]
        assert not matcher.is_excluded("file.tmp")[0]

    def test_paths_with_spaces(self) -> None:
        matcher = ExclusionMatcher((_rule("my file.txt"),))
        assert matcher.is_excluded("my file.txt")[0]
        assert matcher.is_excluded("sub/my file.txt")[0]

    def test_unicode_patterns(self) -> None:
        matcher = ExclusionMatcher((_rule("café/*.pdf"),))
        assert matcher.is_excluded("café/doc.pdf")[0]
        assert not matcher.is_excluded("cafe/doc.pdf")[0]

    def test_unicode_filename(self) -> None:
        matcher = ExclusionMatcher((_rule("*.pdf"),))
        assert matcher.is_excluded("café.pdf")[0]
        assert matcher.is_excluded("中文.pdf")[0]

    def test_multiple_rules(self) -> None:
        matcher = ExclusionMatcher((_rule("*.tmp"), _rule("privado/**"), _rule(".git")))
        assert matcher.is_excluded("notes.tmp")[0]
        assert matcher.is_excluded("privado/secret.pdf")[0]
        assert matcher.is_excluded(".git")[0]
        assert not matcher.is_excluded("readme.md")[0]

    def test_no_rules(self) -> None:
        matcher = ExclusionMatcher(())
        assert not matcher.is_excluded("anything.txt")[0]
        assert not matcher.is_excluded("sub/file.tmp")[0]

    def test_identifies_which_rule_matched(self) -> None:
        matcher = ExclusionMatcher((_rule("*.tmp"), _rule("*.txt")))
        matched, rule = matcher.is_excluded("notes.tmp")
        assert matched
        assert rule is not None
        assert rule.pattern == "*.tmp"

        matched, rule = matcher.is_excluded("notes.txt")
        assert matched
        assert rule is not None
        assert rule.pattern == "*.txt"

    def test_first_rule_wins(self) -> None:
        matcher = ExclusionMatcher((_rule("*.tmp"), _rule("a.tmp")))
        matched, rule = matcher.is_excluded("a.tmp")
        assert matched
        assert rule is not None
        assert rule.pattern == "*.tmp"

    def test_normalized_separators(self) -> None:
        matcher = ExclusionMatcher((_rule("sub/*.txt"),))
        assert matcher.is_excluded("sub/notes.txt")[0]
        assert not matcher.is_excluded("sub\\notes.txt")[0]
