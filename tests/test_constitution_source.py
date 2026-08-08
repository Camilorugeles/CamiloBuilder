import hashlib
import shutil
import tempfile
import unittest
from pathlib import Path

from capability_introspection.constitution import (
    ConstitutionSourceError,
    read_constitution_version,
)


ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    result = hashlib.sha256()
    for item in sorted(candidate for candidate in path.rglob("*") if candidate.is_file()):
        result.update(item.relative_to(path).as_posix().encode())
        result.update(item.read_bytes())
    return result.hexdigest()


class ConstitutionSourceTests(unittest.TestCase):
    def test_reads_the_single_canonical_semver_deterministically_without_writes(self):
        before = digest(ROOT / "governance")
        first = read_constitution_version(ROOT)
        second = read_constitution_version(ROOT)
        self.assertEqual(first, "2.0.0")
        self.assertEqual(first, second)
        self.assertEqual(before, digest(ROOT / "governance"))

    def test_rejects_missing_duplicate_invalid_utf8_and_invalid_semver(self):
        cases = {
            "missing": None,
            "duplicate": "**Versión constitucional:** 2.0.0  \n**Versión constitucional:** 2.0.0  \n",
            "semver": "**Versión constitucional:** 2.0  \n",
            "utf8": b"\xff\xfe",
        }
        for name, content in cases.items():
            with self.subTest(case=name), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                (root / "governance").mkdir()
                path = root / "governance/CONSTITUTION.md"
                if isinstance(content, bytes):
                    path.write_bytes(content)
                elif content is not None:
                    path.write_text(content, encoding="utf-8")
                with self.assertRaises(ConstitutionSourceError):
                    read_constitution_version(root)

    def test_rejects_symlinked_source_and_repository_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repository"
            shutil.copytree(ROOT / "governance", root / "governance")
            source = root / "governance/CONSTITUTION.md"
            external = Path(temporary) / "external.md"
            source.replace(external)
            source.symlink_to(external)
            with self.assertRaises(ConstitutionSourceError):
                read_constitution_version(root)
            alias = Path(temporary) / "alias"
            alias.symlink_to(root)
            with self.assertRaises(ConstitutionSourceError):
                read_constitution_version(alias)


if __name__ == "__main__":
    unittest.main()
