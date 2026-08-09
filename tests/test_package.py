import unittest

import ea_research_lab


class PackageImportTests(unittest.TestCase):
    def test_package_is_importable(self) -> None:
        self.assertEqual(ea_research_lab.__name__, "ea_research_lab")


if __name__ == "__main__":
    unittest.main()
