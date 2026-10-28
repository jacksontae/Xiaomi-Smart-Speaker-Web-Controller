# Contributing

Thanks for helping! This project controls Google Cast speakers (such as the Xiaomi Mi Smart Speaker)
over the local network, without Google Assistant. ภาษาไทยหรือภาษาอังกฤษก็ได้ทั้ง issue และ PR

## Branches

| Branch | Purpose |
|---|---|
| `main` | Production. Changes arrive only from `dev`, merged by the maintainer. |
| `dev` | Integration branch. **Open pull requests against `dev`.** |
| `feat/…` `fix/…` `docs/…` `refactor/…` `test/…` `ci/…` `chore/…` | Short-lived work branches, created from `dev` and deleted after merge. |

Releases and version tags are made by the maintainer.

## Development setup

Python 3.11+ and Node.js (used by yt-dlp for YouTube) are required.

```bash
python3 -m venv .venv
./.venv/bin/pip install -r requirements-dev.txt
cp config.example.json config.json     # set speaker_ip
./.venv/bin/python app.py              # http://localhost:8090
```

## Before opening a pull request

```bash
./.venv/bin/ruff check .
./.venv/bin/python -m pytest
```

Both must pass; CI runs the same checks on Python 3.11–3.14.

- Add or update tests for behaviour changes. Tests use a fake speaker (`tests/conftest.py`), so no hardware is needed.
- If you tested against a real speaker, say which model in the PR.
- Never commit `config.json`, tokens or other secrets.
- Use [Conventional Commits](https://www.conventionalcommits.org/): `feat: …`, `fix: …`, `docs: …`.
- Add a line under **Unreleased** in `CHANGELOG.md` for user-visible changes.

## Reporting bugs and security issues

Use the issue templates for bugs and feature ideas.
Report security problems privately as described in [SECURITY.md](SECURITY.md), not in public issues.

By contributing you agree that your contributions are licensed under the [MIT License](LICENSE)
and that you will follow the [Code of Conduct](CODE_OF_CONDUCT.md).
