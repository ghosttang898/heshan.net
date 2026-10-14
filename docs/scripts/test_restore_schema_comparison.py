from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).parent
spec = importlib.util.spec_from_file_location("schema_restore", ROOT / "isolated-postgresql-restore.py")
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)


def snapshots():
    left = {"schema_fingerprint": "a" * 32, "schema_definitions": {}}
    right = {"schema_fingerprint": "b" * 32, "schema_definitions": {}}
    for key, enum in core.ENUM_CHECKS.items():
        left["schema_definitions"][key], right["schema_definitions"][key] = core.equivalent_check_forms(*enum)
        flag = key.replace("constraint:", "constraint_flags:", 1)
        left["schema_definitions"][flag] = right["schema_definitions"][flag] = "c|t|f|f|f| | | "
    for key, value in {"column:users:5": "role|character varying|16|NO|USER",
                       "index:users:uq_users_username": "UNIQUE username",
                       "constraint:posts:posts_author_id_fkey": "FOREIGN KEY author_id REFERENCES users(id)",
                       "sequence:users_id_seq": "1|1|9223372036854775807|1|f|1"}.items():
        left["schema_definitions"][key] = right["schema_definitions"][key] = value
    return left, right


class SchemaComparisonTest(unittest.TestCase):
    def test_literal_report_form_matches(self):
        source = "CHECK (((role)::text = ANY ((ARRAY['USER'::character varying, 'ADMIN'::character varying, 'SUPER_ADMIN'::character varying])::text[])))"
        restored = "CHECK (((role)::text = ANY (ARRAY[('USER'::character varying)::text, ('ADMIN'::character varying)::text, ('SUPER_ADMIN'::character varying)::text])))"
        self.assertEqual(core.equivalent_check_forms("role", ("USER", "ADMIN", "SUPER_ADMIN")), (source, restored))

    def test_all_seven_observed_equivalents(self):
        left, right = snapshots()
        verdict = core.compare_schema(left, right)
        self.assertFalse(verdict["raw_fingerprint_match"])
        self.assertEqual(set(verdict["normalized_checks"]), set(core.ENUM_CHECKS))
        self.assertEqual(len(verdict["normalized_checks"]), 7)
        self.assertEqual(core.compare_schema(right, left)["normalized_checks"], verdict["normalized_checks"])

    def test_real_check_differences_fail(self):
        for key in core.ENUM_CHECKS:
            column, values = core.ENUM_CHECKS[key]
            for changed in (core.equivalent_check_forms(column, (*values, "BYPASS"))[1],
                            core.equivalent_check_forms(column, values[:-1])[1],
                            core.equivalent_check_forms("other_column", values)[1],
                            core.equivalent_check_forms(column, values)[1].replace(" = ANY", " <> ALL"),
                            core.equivalent_check_forms(column, values)[1].replace("::character varying", "::character(8)"),
                            core.equivalent_check_forms(column, values)[1].replace("::text", "::citext"),
                            core.equivalent_check_forms(column, values)[1].replace("::character varying", "::character varying(2)"),
                            core.equivalent_check_forms(column, values)[1] + " OR role IS NULL",
                            core.equivalent_check_forms(column, values)[1].replace("'" + values[0] + "'::character varying", "NULL::character varying")):
                with self.subTest(key=key, changed=changed):
                    left, right = snapshots()
                    right["schema_definitions"][key] = changed
                    with self.assertRaises(ValueError):
                        core.compare_schema(left, right)

    def test_unknown_check_is_not_normalized(self):
        left, right = snapshots()
        source, restored = core.equivalent_check_forms("role", ("USER", "ADMIN", "SUPER_ADMIN"))
        left["schema_definitions"]["constraint:other:role_check"] = source
        right["schema_definitions"]["constraint:other:role_check"] = restored
        with self.assertRaises(ValueError):
            core.compare_schema(left, right)

    def test_flags_columns_indexes_foreign_keys_sequences_fail(self):
        left, right = snapshots()
        for key in left["schema_definitions"]:
            if key.startswith("constraint:") and key in core.ENUM_CHECKS:
                continue
            with self.subTest(key=key):
                modified = deepcopy(right)
                modified["schema_definitions"][key] += "CHANGED"
                with self.assertRaises(ValueError):
                    core.compare_schema(left, modified)

    def test_missing_or_extra_constraint_fails(self):
        for extra in (True, False):
            left, right = snapshots()
            if extra:
                right["schema_definitions"]["constraint:users:extra"] = "CHECK (false)"
            else:
                del right["schema_definitions"][next(iter(core.ENUM_CHECKS))]
            with self.assertRaises(ValueError):
                core.compare_schema(left, right)

    def test_matching_hash_cannot_hide_changed_definitions(self):
        left, right = snapshots()
        right["schema_fingerprint"] = left["schema_fingerprint"]
        right["schema_definitions"][next(iter(core.ENUM_CHECKS))] = "CHECK (true)"
        with self.assertRaises(ValueError):
            core.compare_schema(left, right)

    def test_legacy_mismatch_requires_details(self):
        with self.assertRaises(ValueError):
            core.compare_schema({"schema_fingerprint": "a" * 32}, {"schema_fingerprint": "b" * 32})

    def test_legacy_exact_match_preserved(self):
        self.assertEqual(core.compare_schema({"schema_fingerprint": "a" * 32},
                                             {"schema_fingerprint": "a" * 32})["normalized_checks"], [])

    def test_empty_or_both_missing_flags_fail(self):
        left, right = snapshots()
        for snapshot in (left, right):
            del snapshot["schema_definitions"]["constraint_flags:users:users_role_check"]
        with self.assertRaises(ValueError):
            core.compare_schema(left, right)
        with self.assertRaises(ValueError):
            core.compare_schema({"schema_fingerprint": "a" * 32, "schema_definitions": {}},
                                {"schema_fingerprint": "b" * 32, "schema_definitions": {}})

    def test_full_snapshot_preserves_data_and_role_checks(self):
        left, right = snapshots()
        common = {"tables": {"users": {"count": 5, "fingerprint": "fixed"}},
                  "sequences": [], "identities": [{"id": 1, "role": "USER"}],
                  "founders": [], "role_counts": {"USER": 5},
                  "migrations": [{"version": "1", "success": True}], "invalid_links": 0}
        left.update(deepcopy(common))
        right.update(deepcopy(common))
        core.compare_snapshot(left, right)
        for key in common:
            changed = deepcopy(right)
            changed[key] = "CHANGED"
            with self.subTest(key=key), self.assertRaises(ValueError):
                core.compare_snapshot(left, changed)

    def test_definition_output_has_constraint_flags(self):
        sql = (ROOT / "restore-reference.sql").read_text()
        for field in ("convalidated", "condeferrable", "condeferred", "connoinherit", "confdeltype", "schema_definitions"):
            self.assertIn(field, sql)


if __name__ == "__main__":
    unittest.main()
