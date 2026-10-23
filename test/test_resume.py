"""Résumé timeline: validation, ordering and the read-only public page."""
import unittest
import uuid
from unittest.mock import MagicMock, patch

from app.resume import service
from app.resume.models import ResumeEntry
from app.resume.service import ResumeValidationError, validate_entry


def fields(**overrides):
    value = {
        "period": "2022 – present", "title": "Data Engineer", "organization": "Acme, Calgary",
        "kind": "work", "summary": "", "highlights": [], "skills": [], "visible": True,
    }
    value.update(overrides)
    return value


class ValidationTests(unittest.TestCase):
    def test_text_is_trimmed_and_blank_list_items_dropped(self):
        clean = validate_entry(**fields(
            title="  Data   Engineer ", highlights=["Built the load", "  ", ""], skills=[" SQL ", ""],
        ))
        self.assertEqual(clean["title"], "Data Engineer")
        self.assertEqual(clean["highlights"], ["Built the load"])
        self.assertEqual(clean["skills"], ["SQL"])

    def test_summary_is_optional(self):
        self.assertEqual(validate_entry(**fields(summary="   "))["summary"], "")

    def test_unknown_type_is_rejected(self):
        with self.assertRaisesRegex(ResumeValidationError, "Type"):
            validate_entry(**fields(kind="hobby"))

    def test_missing_title_and_overlong_items_are_rejected(self):
        with self.assertRaisesRegex(ResumeValidationError, "Title"):
            validate_entry(**fields(title=" "))
        with self.assertRaisesRegex(ResumeValidationError, "Highlights"):
            validate_entry(**fields(highlights=["x"] * (service.MAX_HIGHLIGHTS + 1)))
        with self.assertRaisesRegex(ResumeValidationError, "Skills"):
            validate_entry(**fields(skills=["x" * 41]))


class OrderingTests(unittest.TestCase):
    def _database(self, entries):
        database = MagicMock()
        database.scalars.return_value.all.return_value = entries
        scope = MagicMock()
        scope.__enter__.return_value = database
        return scope, database

    def test_moving_up_swaps_with_the_entry_above_and_renumbers(self):
        a, b, c = (ResumeEntry(id=uuid.uuid4(), position=p) for p in (5, 9, 12))
        scope, database = self._database([a, b, c])
        with patch.object(service, "session_scope", return_value=scope):
            service.move_entry(c.id, -1)
        self.assertEqual([a.position, c.position, b.position], [0, 1, 2])
        database.commit.assert_called_once()

    def test_the_top_entry_cannot_move_up(self):
        a, b = (ResumeEntry(id=uuid.uuid4(), position=p) for p in (0, 1))
        scope, database = self._database([a, b])
        with patch.object(service, "session_scope", return_value=scope):
            service.move_entry(a.id, -1)
        self.assertEqual([a.position, b.position], [0, 1])
        database.commit.assert_not_called()


class ModelTests(unittest.TestCase):
    def test_entries_live_in_the_portfolio_schema(self):
        self.assertEqual(ResumeEntry.__table__.schema, "portfolio")


if __name__ == "__main__":
    unittest.main()
