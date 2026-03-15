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
