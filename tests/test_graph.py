"""Tests for graph module: frontmatter, wikilinks, backlinks."""

from pathlib import Path

from claw_librarian.graph.frontmatter import parse, parse_file, serialize


class TestFrontmatter:
    def test_parse_with_frontmatter(self):
        text = "---\ntitle: Hello\nstatus: active\n---\n\n# Body\n"
        meta, body = parse(text)
        assert meta["title"] == "Hello"
        assert "# Body" in body

    def test_parse_without_frontmatter(self):
        text = "# Just a heading\n\nSome text.\n"
        meta, body = parse(text)
        assert meta is None
        assert body == text

    def test_parse_yaml_list(self):
        text = "---\nkeywords: [a, b, c]\n---\n\nBody\n"
        meta, body = parse(text)
        assert meta["keywords"] == ["a", "b", "c"]

    def test_parse_quoted_strings(self):
        text = '---\ntitle: "Quoted Title"\n---\n\nBody\n'
        meta, body = parse(text)
        assert meta["title"] == "Quoted Title"

    def test_serialize_roundtrip(self):
        meta = {"title": "Test", "keywords": ["a", "b"], "status": "active"}
        body = "# Content\n"
        output = serialize(meta, body)
        meta2, body2 = parse(output)
        assert meta2["title"] == "Test"
        assert meta2["keywords"] == ["a", "b"]
        assert "# Content" in body2

    def test_parse_file(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("---\ntitle: File\n---\n\nContent\n")
        meta, body = parse_file(f)
        assert meta["title"] == "File"


from claw_librarian.graph.wikilinks import (
    extract_wikilinks,
    resolve_ref,
    find_all_vault_files,
)


class TestWikilinks:
    def test_extract_simple(self):
        links = extract_wikilinks("See [[target]] for details.")
        assert links == ["target"]

    def test_extract_with_display(self):
        links = extract_wikilinks("See [[target|display text]].")
        assert links == ["target"]

    def test_extract_with_section(self):
        links = extract_wikilinks("See [[target#section]].")
        assert links == ["target"]

    def test_extract_multiple(self):
        links = extract_wikilinks("[[a]] and [[b]] and [[c]]")
        assert links == ["a", "b", "c"]

    def test_extract_none(self):
        links = extract_wikilinks("No links here.")
        assert links == []

    def test_resolve_ref_literal_path(self, vault_with_files):
        result = resolve_ref("projects/test-project/api-spec", vault_with_files)
        assert result is not None
        assert result.name == "api-spec.md"

    def test_resolve_ref_stem_fallback(self, vault_with_files):
        result = resolve_ref("api-spec", vault_with_files)
        assert result is not None
        assert result.name == "api-spec.md"

    def test_resolve_ref_not_found(self, vault_with_files):
        result = resolve_ref("nonexistent", vault_with_files)
        assert result is None

    def test_find_all_vault_files(self, vault_with_files):
        files = find_all_vault_files(vault_with_files)
        names = {f.name for f in files}
        assert "api-spec.md" in names
        assert "tests.md" in names

    def test_find_excludes_internal_dirs(self, vault_with_files):
        internal = vault_with_files / "_inbox"
        internal.mkdir()
        (internal / "temp.md").write_text("temp")
        files = find_all_vault_files(vault_with_files)
        names = {f.name for f in files}
        assert "temp.md" not in names


from claw_librarian.graph.backlinks import build_backlink_index, incoming_links


class TestBacklinks:
    def test_build_index(self, vault_with_files):
        index = build_backlink_index(vault_with_files)
        # api-spec links to tests and lessons
        # tests links to api-spec
        assert len(index) > 0

    def test_incoming_links(self, vault_with_files):
        target = vault_with_files / "projects" / "test-project" / "api-spec.md"
        sources = incoming_links(target, vault_with_files)
        source_names = {s.name for s in sources}
        assert "tests.md" in source_names  # tests.md links to [[api-spec]]

    def test_no_self_links(self, vault_with_files):
        target = vault_with_files / "projects" / "test-project" / "api-spec.md"
        sources = incoming_links(target, vault_with_files)
        assert target not in sources

    def test_incoming_links_nonexistent(self, vault_with_files):
        target = vault_with_files / "nope.md"
        sources = incoming_links(target, vault_with_files)
        assert sources == []
