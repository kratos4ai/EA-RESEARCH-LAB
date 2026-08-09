import unittest
from unittest.mock import patch

from tools import check


class CheckRunnerTests(unittest.TestCase):
    def test_main_propagates_a_failed_command_exit_code(self) -> None:
        with patch.object(check, "_run", return_value=7):
            self.assertEqual(check.main(), 7)


if __name__ == "__main__":
    unittest.main()
