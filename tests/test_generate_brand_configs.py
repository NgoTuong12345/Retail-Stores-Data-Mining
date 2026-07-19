"""Tests for generalized brand config generator."""
import re
from pathlib import Path

import pytest
import yaml

from generate_brand_configs import (
    slugify,
    build_brand_regex,
    build_spelling_variants,
    write_brand_config,
    should_skip_brand,
)


class TestSlugify:
    def test_simple(self):
        assert slugify("Starbucks") == "starbucks"

    def test_spaces(self):
        assert slugify("King BBQ") == "king-bbq"

    def test_special_chars(self):
        assert slugify("Pizza 4P's") == "pizza-4p-s"

    def test_ampersand(self):
        assert slugify("Wrap & Roll") == "wrap-roll"

    def test_dot(self):
        assert slugify("Co.op food") == "co-op-food"

    def test_parenthetical(self):
        assert slugify("AEON (Supermarket)") == "aeon-supermarket"

    def test_vietnamese_diacritics(self):
        assert slugify("Café Ông Bầu") == "cafe-ong-bau"

    def test_trailing_hyphens(self):
        assert slugify("Go!") == "go"

    def test_consecutive_hyphens(self):
        assert slugify("IT Cream & Bakery") == "it-cream-bakery"


class TestBuildBrandRegex:
    def test_simple_brand(self):
        regex = build_brand_regex("Starbucks")
        pattern = re.compile(regex, re.IGNORECASE)
        assert pattern.search("STARBUCKS COFFEE")
        assert pattern.search("starbucks")

    def test_special_chars_escaped(self):
        regex = build_brand_regex("Pizza 4P's")
        pattern = re.compile(regex, re.IGNORECASE)
        assert pattern.search("PIZZA 4P'S HA NOI")

    def test_ampersand_brand(self):
        regex = build_brand_regex("R&B Tea")
        pattern = re.compile(regex, re.IGNORECASE)
        assert pattern.search("R&B TEA VIETNAM")

    def test_vietnamese_both_forms(self):
        """Regex should match both diacriticked and ASCII-folded forms."""
        regex = build_brand_regex("Phúc Long")
        pattern = re.compile(regex, re.IGNORECASE)
        assert pattern.search("PHÚC LONG")
        assert pattern.search("PHUC LONG")


class TestBuildSpellingVariants:
    def test_basic_variants(self):
        variants = build_spelling_variants("Starbucks")
        assert "Starbucks" in variants
        assert "STARBUCKS" in variants
        assert "starbucks" in variants

    def test_vietnamese_includes_ascii(self):
        variants = build_spelling_variants("Phúc Long")
        assert "Phúc Long" in variants
        assert "PHÚC LONG" in variants
        assert "PHUC LONG" in variants
        assert "phuc long" in variants

    def test_no_duplicates(self):
        variants = build_spelling_variants("KFC")
        assert len(variants) == len(set(variants))


class TestShouldSkipBrand:
    def test_skip_existing(self, tmp_path):
        brand_dir = tmp_path / "brands" / "starbucks"
        brand_dir.mkdir(parents=True)
        (brand_dir / "config.yaml").write_text("slug: starbucks\n")
        assert should_skip_brand("starbucks", tmp_path / "brands") is True

    def test_no_skip_new(self, tmp_path):
        brands_dir = tmp_path / "brands"
        brands_dir.mkdir(parents=True)
        assert should_skip_brand("new-brand", brands_dir) is False


class TestWriteBrandConfig:
    def test_creates_config_yaml(self, tmp_path):
        brands_dir = tmp_path / "brands"
        brands_dir.mkdir()

        brand_entry = {
            "brand_name": "Starbucks",
            "parent_company": "Starbucks Corp (US)",
            "country_of_origin": "United States",
        }
        result = write_brand_config(brand_entry, "F&B", "coffee_chains", brands_dir)

        assert result["status"] == "created"
        config_path = brands_dir / "F&B" / "coffee_chains" / "starbucks" / "config.yaml"
        assert config_path.exists()

        loaded = yaml.safe_load(config_path.read_text(encoding='utf-8'))
        assert loaded["slug"] == "starbucks"
        assert loaded["name"] == "Starbucks"
        assert "STARBUCKS" in loaded["spelling_variants"]
        assert loaded["default_store_type"] == "Starbucks"

    def test_skips_existing(self, tmp_path):
        brands_dir = tmp_path / "brands"
        existing = brands_dir / "F&B" / "coffee_chains" / "starbucks"
        existing.mkdir(parents=True)
        (existing / "config.yaml").write_text("slug: starbucks\n")

        brand_entry = {
            "brand_name": "Starbucks",
            "parent_company": None,
            "country_of_origin": None,
        }
        result = write_brand_config(brand_entry, "F&B", "coffee_chains", brands_dir)
        assert result["status"] == "skipped"
