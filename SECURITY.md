# Security Policy

## Supported versions

Security fixes are applied to the latest code on the default branch. Older commits and unpublished development branches are not supported.

## Reporting a vulnerability

Do not disclose vulnerabilities, credentials, private camera addresses, recordings, or snapshots in a public issue.

Use the repository's private security-reporting channel to contact the maintainers. Include:

- a concise description of the issue and its impact;
- reproducible steps or a minimal proof of concept;
- affected versions or commits;
- any suggested mitigation;
- sanitized logs with secrets and private addresses removed.

Allow the maintainers time to investigate and coordinate a fix before public disclosure.

## Deployment guidance

- Use a dedicated, least-privilege camera account.
- Keep cameras on a trusted network segment and restrict ONVIF, RTSP, and WS-Discovery access.
- Store credentials only in the ignored local `.env` file or enter them at runtime.
- Do not commit captured media or diagnostic output containing private network information.
