import os
import re
import subprocess
from pathlib import Path


def parse_version(value: str) -> tuple[int, int, int]:
    if not re.fullmatch(r"v?\d+\.\d+\.\d+", value):
        raise ValueError(f"Invalid release version: {value}")
    return tuple(int(part) for part in value.removeprefix("v").split("."))


def next_version(current: str, previous: str | None) -> str:
    current_parts = parse_version(current)
    if previous is None or current_parts > parse_version(previous):
        return current
    major, minor, patch = parse_version(previous)
    return f"{major}.{minor}.{patch + 1}"


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True, encoding="utf-8").strip()


def prepare_release(root: Path) -> str:
    source_path = root / "etherdrop.py"
    source = source_path.read_text(encoding="utf-8")
    current = re.search(r'^APP_VERSION = "([^"]+)"$', source, re.MULTILINE).group(1)
    tags = [tag for tag in git("tag", "--list").splitlines() if re.fullmatch(r"v\d+\.\d+\.\d+", tag)]
    previous_tag = max(tags, key=parse_version) if tags else None
    version = next_version(current, previous_tag)
    source_path.write_text(re.sub(r'^APP_VERSION = "[^"]+"$', f'APP_VERSION = "{version}"', source, flags=re.MULTILINE), encoding="utf-8")

    manifest_path = root / "EtherDrop.manifest"
    manifest = manifest_path.read_text(encoding="utf-8")
    manifest_path.write_text(re.sub(r'version="\d+\.\d+\.\d+\.\d+"', f'version="{version}.0"', manifest), encoding="utf-8")

    notes_path = root / "RELEASE_NOTES.md"
    if previous_tag and notes_path.read_text(encoding="utf-8").strip() == git("show", f"{previous_tag}:RELEASE_NOTES.md"):
        subjects = git("log", f"{previous_tag}..HEAD", "--format=%s", "--no-merges").splitlines()
        subjects = [subject for subject in subjects if not subject.startswith("chore: release v")]
        notes = f"What's new in EtherDrop v{version}\n\n" + "\n".join(f"- {subject}" for subject in subjects)
        notes_path.write_text(notes + "\n", encoding="utf-8")

    return version


if __name__ == "__main__":
    version = prepare_release(Path.cwd())
    print(f"Preparing EtherDrop v{version}")
    with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
        output.write(f"version={version}\n")
