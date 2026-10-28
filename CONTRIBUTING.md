# Contributing

Thank you for helping improve Network Camera Console.

Participation in this project is governed by [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## Before you start

- Search existing issues before opening a new one.
- Do not post camera passwords, private network details, recordings, or snapshots.
- Keep changes focused and explain any user-visible behavior change.
- For larger changes, open an issue first so the approach can be discussed.

## Development setup

Install the system dependencies listed in `README.md`, then optionally create a local environment:

```bash
python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install -r requirements.txt
```

Copy `.env.example` to `.env` only for local testing. Never commit `.env`.

## Checks

Run these commands before submitting a pull request:

```bash
python3 -m compileall -q src
python3 -m unittest discover -s tests -v
bash -n scripts/run_desktop.sh
```

Hardware-dependent changes should also be tested with an ONVIF/RTSP camera when possible. Describe the tested camera capabilities without publishing credentials or private addresses.

## Pull requests

- Use a clear title and description.
- Link related issues.
- Include screenshots for interface changes.
- Update English and Chinese documentation together when user-facing behavior changes.
- Confirm that generated recordings, snapshots, caches, and local configuration are not included.
