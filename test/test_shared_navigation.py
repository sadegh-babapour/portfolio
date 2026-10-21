import json
import re
import unittest
from pathlib import Path

from app.components import navbar


ROOT = Path(__file__).resolve().parents[1]
NAVIGATION = json.loads((ROOT / "content" / "navigation.json").read_text(encoding="utf-8"))


class SharedNavigationTests(unittest.TestCase):
    """The NiceGUI header and the transit map header share content/navigation.json."""

    def test_navbar_links_come_from_the_shared_file(self):
        self.assertEqual(navbar.NAV_LINKS, [tuple(link) for link in NAVIGATION["links"]])
        self.assertEqual(navbar.ACCOUNT_LINK, tuple(NAVIGATION["account_link"]))
        self.assertEqual(json.loads(navbar.THEME_JSON), NAVIGATION["theme"])

    def test_links_are_well_formed_and_unique(self):
        paths = [path for _, path in NAVIGATION["links"]]
        self.assertEqual(len(paths), len(set(paths)))
        for label, path in [*NAVIGATION["links"], NAVIGATION["account_link"]]:
            self.assertTrue(label.strip())
            self.assertTrue(path.startswith("/"), path)
        self.assertNotIn(NAVIGATION["account_link"][1], paths)

    def test_theme_rules_are_valid(self):
        theme = NAVIGATION["theme"]
        self.assertEqual(theme["time_zone"], "America/Edmonton")
        self.assertTrue(0 <= theme["light_from_hour"] < theme["dark_from_hour"] <= 24)
        self.assertNotEqual(theme["mode_storage_key"], theme["resolved_storage_key"])

    def test_no_second_copy_of_links_or_theme_rules(self):
        python_source = (ROOT / "app" / "components" / "navbar.py").read_text(encoding="utf-8")
        react_source = (ROOT / "frontend" / "src" / "PortfolioNav.jsx").read_text(encoding="utf-8")
        theme_source = (ROOT / "frontend" / "src" / "mountainTime.js").read_text(encoding="utf-8")

        for label, _ in [*NAVIGATION["links"], NAVIGATION["account_link"]]:
            for source in (python_source, react_source):
                self.assertFalse(f"'{label}'" in source or f'"{label}"' in source, label)
        for source in (python_source, theme_source):
            for constant in ("America/Edmonton", "portfolio-theme-mode"):
                self.assertFalse(constant in source, constant)
            self.assertIsNone(re.search(r"hour >= 7 && hour < 19", source))
        self.assertEqual(python_source.count("__PORTFOLIO_THEME__"), 5)


if __name__ == "__main__":
    unittest.main()


class SharedHeaderStyleTests(unittest.TestCase):
    """Both headers use static/portfolio-nav.css and the same class names."""

    STYLESHEET = (ROOT / "static" / "portfolio-nav.css").read_text(encoding="utf-8")
    CLASSES = (
        "portfolio-nav", "portfolio-brand", "portfolio-nav-desktop", "portfolio-nav-actions",
        "portfolio-mountain-clock", "portfolio-theme-toggle", "portfolio-nav-mobile",
        "portfolio-nav-mobile-links", "portfolio-account-link",
    )

    def test_navbar_links_the_versioned_stylesheet(self):
        self.assertRegex(navbar.NAV_STYLESHEET_URL, r"^/static/portfolio-nav\.css\?v=[0-9a-f]{12}$")
        source = (ROOT / "app" / "components" / "navbar.py").read_text(encoding="utf-8")
        self.assertIn('<link rel="stylesheet" href="__NAV_STYLESHEET_URL__">', source)

    def test_both_headers_use_the_shared_class_names(self):
        python_source = (ROOT / "app" / "components" / "navbar.py").read_text(encoding="utf-8")
        react_source = (ROOT / "frontend" / "src" / "PortfolioNav.jsx").read_text(encoding="utf-8")
        self.assertIn('import "../../static/portfolio-nav.css";', react_source)
        for name in self.CLASSES:
            self.assertIn(f".{name}", self.STYLESHEET, name)
            self.assertIn(name, python_source, name)
            self.assertIn(name, react_source, name)

    def test_no_second_copy_of_the_header_styles(self):
        python_source = (ROOT / "app" / "components" / "navbar.py").read_text(encoding="utf-8")
        app_css = (ROOT / "frontend" / "src" / "App.css").read_text(encoding="utf-8")
        self.assertNotIn("nicegui-portfolio", python_source)
        self.assertNotIn("nicegui-mobile", python_source)
        for name in self.CLASSES:
            self.assertNotIn(f".{name} {{{{", python_source, name)
            self.assertNotIn(f".{name}", app_css, name)
