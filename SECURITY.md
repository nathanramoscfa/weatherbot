# Security policy

Weatherbot is a personal hurricane-threat monitor in a public repository. Its
maintainer, Nathan Ramos ([@nathanramoscfa](https://github.com/nathanramoscfa)),
owns its security: triage, fixes, and advisories.

## Reporting a vulnerability

**Do not open a public issue for a vulnerability.** Report it privately
through GitHub's private vulnerability reporting:

1. Open
   <https://github.com/nathanramoscfa/weatherbot/security/advisories/new>
   (or the repository's **Security** tab, then **Report a vulnerability**).
2. Describe the issue, the affected surface (the command line, the web app,
   a source client, CI, or the repository settings), how to reproduce it, and
   the impact you expect. Include a proof of concept if you have one.

Never include a real location, an API key, or any other personal value in a
report. Use synthetic values or the public landmarks in
[`scripts/public_landmarks.toml`](scripts/public_landmarks.toml).

You will get an acknowledgement within 7 days. Critical and High findings are
fixed on a `hotfix/` or `fix/` branch before other work continues; Medium and
Low findings are tracked as issues with a due date
([the roadmap](docs/roadmap/ROADMAP.md), "Vulnerability handling"). You are
credited in the advisory unless you ask otherwise.

## Supported versions

| Version                                  | Supported                        |
| ---------------------------------------- | -------------------------------- |
| 2.x pre-releases on `main`               | Yes: fixes land on `main`        |
| 1.0.0 (PyPI, the `v1.0.0` tag)           | No: retired, and never patched   |

## What counts as a vulnerability here

Beyond the usual classes (injection, unsafe deserialization, a vulnerable
dependency, a weakness in the CI pipeline), Weatherbot treats these as
vulnerabilities:

- **A path that leaks personal data or a secret**: the operator's
  coordinates or another personal value, an API key, or a token reaching the
  repository, a fixture, a log, an export, a bug report, or the web app's
  client bundle.
- **Model output reaching a level or a fact**: anything the Claude
  integration says being stored or shown as an alert level, a storm
  position, a watch or warning, or a time. Official NHC and NWS products
  decide; the model only narrates.
- **A non-loopback bind without the LAN token**: the web app listening on
  anything other than 127.0.0.1 without the LAN setting and its token.

## Out of scope

The NOAA services Weatherbot reads (report problems with those to NOAA), and
findings that require an already-compromised maintainer account or machine.
