# Working on EtherDrop

## User instructions

Follow the existing code style and patterns in the repository. Keep solutions simple and consistent, and avoid adding unnecessary complexity, edge-case handling, compatibility workarounds, or speculative checks unless explicitly requested.

Do not waste tokens and time thinking on things you can just ask the user about. If asking a couple of questions can clarify the task and save time, ask those questions.

The user must always be the final decision maker. Do not make decisions on their behalf; ask specific questions to clarify the task or let them decide meaningful choices.

Never commit or push changes before the user has personally looked at the app and explicitly approved those changes for committing and pushing. This is mandatory for every change; do not wait for the user to request manual testing.

## Project

EtherDrop is a Windows application for sharing large files and folders between friends over a direct Ethernet connection. Read `README.md` for usage and networking requirements.

- `etherdrop.py`: application, Tkinter UI, transfer services, and updater. The runtime uses the Python standard library.
- `build.bat` and `EtherDrop.spec`: PyInstaller build configuration.
- `EtherDrop.manifest`: Windows manifest, including the application version.
- `RELEASE_NOTES.md`: notes for the next release, bundled inside the EXE and published on GitHub.
- `scripts/prepare_release.py`: automatic version selection and release preparation.
- `.github/workflows/release.yml`: Windows build and publication workflow.
- `tests/`: updater and versioning tests.

The distributed application must remain one standalone `EtherDrop.exe`. Do not require Python, an installer, or a permanent updater executable on users' computers.

## Making changes

- Inspect the working tree before editing and preserve unrelated user changes.
- Follow the existing Tkinter theme and UI patterns. Network and file work runs in background threads; UI updates use the existing event queue and Tk callbacks.
- The **Check for updates** button belongs only on the opening role-selection screen. It must not appear on Sender, Receiver, or other screens.
- Preserve direct Ethernet transfer behavior: physical wired adapters, no default gateway, IPv6 link-local discovery and transfer. Internet access for GitHub updates is separate and may use Wi-Fi.
- Preserve receiver approval and destination selection, transfer cancellation, and the existing diagnostics flow.
- Update downloads require user approval. Keep EXE replacement, temporary updater cleanup, restart, and release notes working.
- The release-notes dialog appears once per newly installed version, works offline using bundled notes, and opens when a manual check finds no newer version.
- For an app change, replace `RELEASE_NOTES.md` with concise notes describing the upcoming release. If it is unchanged, the workflow generates notes from commit titles.

## Branches and releases

- Work on `main` first. `main` must always contain every commit on `release`; it may be equal to or ahead of `release`, never behind it.
- Do not commit application changes directly to `release`. If using a feature branch, integrate it into `main` before promoting it to `release`.
- A push to `main` does not publish an app update. A push to `release` starts a build and publishes a new patch release, including for documentation or workflow changes.
- After the user has looked at the app and explicitly approved committing, pushing, and publication, push `main` first, then fast-forward `release` from `main` and push `release`. Return the working checkout to `main`.
- The workflow commits the release version on `release`, merges that commit into `main`, and pushes both branches and the tag atomically. Preserve newer work on `main`; resolve conflicts instead of force-pushing or rewriting history.
- Pull the workflow's version commit after a release completes before starting the next change.
- Normal releases increment the patch automatically. Do not manually bump `APP_VERSION` for a patch or create release tags yourself during the normal workflow.
- Minor and major versions require the user to explicitly choose the next version. Set `APP_VERSION` to that version only with their instruction; release preparation updates the manifest to match.
- Keep the full version in the source, tag, manifest, and released EXE consistent. Application versioning is separate from `PROTOCOL_VERSION` and `MAGIC`.
- If asked to publish, verify the workflow finishes successfully and the GitHub release contains `EtherDrop.exe` and the expected notes. A successful push alone is not a completed release.

## Validation and approval

Use the project's Python environment when available. Run checks appropriate to the change; avoid adding tests for trivial reversible edits or repeating unrelated checks.

```powershell
# Run from source.
python etherdrop.py

# Updater and release-versioning checks.
python -m unittest discover -s tests -v

# Build the standalone EXE with PyInstaller installed in the active environment.
.\build.bat
```

- Check the affected behavior, build and launch a visible local test copy, and let the user personally inspect the app before committing or pushing any changes.
- Never commit, push, or promote changes to `release` until the user has inspected the app and explicitly approved those specific changes. Automated tests or an earlier approval for different changes do not replace this approval. Wait for the user even if all checks pass.
- Do not overwrite an existing installed EXE just to test a change. Use the local `dist\EtherDrop.exe` test copy.
- Keep `build/`, `dist/`, `.venv/`, and Python caches out of commits.
- Adding or editing this file does not by itself authorize committing, pushing, or publishing a release.
