import subprocess
from pathlib import Path


class HistoricalEvidenceUnavailable(RuntimeError):
    """Raised when an explicitly historical Git assertion cannot be completed."""


def _git(repository_root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=repository_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise HistoricalEvidenceUnavailable(
            f"Historical Git evidence unavailable: {' '.join(arguments)}"
        )
    return completed.stdout.strip()


def require_commit(repository_root: Path, commit: str) -> None:
    if _git(repository_root, "cat-file", "-t", commit) != "commit":
        raise HistoricalEvidenceUnavailable(f"Historical object is not a commit: {commit}")


def require_ancestor(repository_root: Path, commit: str, reference: str) -> None:
    require_commit(repository_root, commit)
    _git(repository_root, "merge-base", "--is-ancestor", commit, reference)


def commit_timestamp(repository_root: Path, commit: str) -> int:
    require_commit(repository_root, commit)
    return int(_git(repository_root, "show", "-s", "--format=%ct", commit))


def commit_timestamp_rfc3339(repository_root: Path, commit: str) -> str:
    require_commit(repository_root, commit)
    return _git(repository_root, "show", "-s", "--format=%cI", commit)


def require_chronological_commits(repository_root: Path, commits: list[str]) -> None:
    timestamps = [commit_timestamp(repository_root, commit) for commit in commits]
    if timestamps != sorted(timestamps):
        raise HistoricalEvidenceUnavailable("Historical commits are not chronological")
