import re
from pathlib import Path


VERSION_PATTERN = re.compile(
    r"^\*\*Versión constitucional:\*\* "
    r"((?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?)[ \t]*$",
    re.MULTILINE,
)


class ConstitutionSourceError(RuntimeError):
    """Raised when the canonical constitutional source cannot be trusted."""


def read_constitution_version(repository_root: Path) -> str:
    root = Path(repository_root)
    if root.is_symlink() or not root.is_dir():
        raise ConstitutionSourceError("Invalid repository root")
    path = root / "governance" / "CONSTITUTION.md"
    current = path
    while current != root:
        if current.is_symlink():
            raise ConstitutionSourceError("Symlink constitutional source")
        current = current.parent
    try:
        path.resolve().relative_to(root.resolve())
        text = path.read_text(encoding="utf-8")
    except (ValueError, OSError, UnicodeDecodeError) as error:
        raise ConstitutionSourceError("Invalid constitutional source") from error
    matches = VERSION_PATTERN.findall(text)
    if len(matches) != 1:
        raise ConstitutionSourceError("Constitution must declare exactly one SemVer version")
    return matches[0]
