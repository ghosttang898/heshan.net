import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).parent
spec = importlib.util.spec_from_file_location("diagnosis", ROOT / "diagnose-restored-schema.py")
diagnosis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnosis)


class DiagnosisTest(unittest.TestCase):
    def test_pinned_files(self):
        for name, expected in diagnosis.PINS.items():
            self.assertEqual(diagnosis.hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), expected)

    def test_schema_sql_is_read_only_and_contains_no_rows(self):
        sql = diagnosis.structural_sql((ROOT / "restore-reference.sql").read_text())
        self.assertTrue(sql.startswith("BEGIN READ ONLY;"))
        self.assertIn("pg_get_constraintdef", sql)
        self.assertIn("information_schema.columns", sql)
        self.assertNotIn("row_to_json", sql)
        self.assertNotIn("identities", sql)
        self.assertNotIn("database_size_bytes", sql)
        self.assertTrue(sql.endswith("COMMIT;\n"))

    def test_sql_format_change_fails_closed(self):
        with self.assertRaises(ValueError):
            diagnosis.structural_sql("SELECT 1;")

    def test_differences_missing_and_changed(self):
        self.assertEqual(diagnosis.differences({"b": "same", "a": "old", "c": "lost"},
                                              {"b": "same", "a": "new", "d": "added"}), [
            {"key": "a", "source": "old", "restored": "new"},
            {"key": "c", "source": "lost", "restored": None},
            {"key": "d", "source": None, "restored": "added"}])

    def test_unapproved_targets_and_transactions_never_execute(self):
        commands, core = Mock(), Mock()
        for container, database, sql in [
            ("other", "restore_test", "BEGIN READ ONLY; COMMIT;"),
            (diagnosis.SOURCE, "restore_test", "BEGIN READ ONLY; COMMIT;"),
            (diagnosis.TARGET, "production", "BEGIN READ ONLY; COMMIT;"),
            (diagnosis.TARGET, "restore_test", "SELECT 1;")]:
            with self.assertRaises(ValueError):
                diagnosis.read_only_query(commands, core, container, database, sql)
        commands.run.assert_not_called()

    def test_psql_has_explicit_readonly_target(self):
        commands, core = Mock(), Mock()
        diagnosis.read_only_query(commands, core, diagnosis.TARGET, "restore_test", diagnosis.METADATA_SQL)
        args, data = commands.run.call_args.args
        self.assertEqual(args[:3], ["exec", "-i", diagnosis.TARGET])
        self.assertIn("ON_ERROR_STOP=1", args)
        self.assertEqual(data, diagnosis.METADATA_SQL.encode())


if __name__ == "__main__":
    unittest.main()
