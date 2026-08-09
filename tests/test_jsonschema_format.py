import unittest

from jsonschema import Draft202012Validator, FormatChecker


class JsonSchemaFormatTests(unittest.TestCase):
    def test_format_validation_is_explicitly_enabled(self) -> None:
        schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "string",
            "format": "date-time",
        }
        invalid_value = "not-a-date-time"

        without_checker = Draft202012Validator(schema)
        with_checker = Draft202012Validator(
            schema,
            format_checker=FormatChecker(),
        )

        self.assertEqual(list(without_checker.iter_errors(invalid_value)), [])
        self.assertNotEqual(list(with_checker.iter_errors(invalid_value)), [])


if __name__ == "__main__":
    unittest.main()
