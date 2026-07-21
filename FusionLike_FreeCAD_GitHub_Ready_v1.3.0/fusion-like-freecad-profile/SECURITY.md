# Security policy

## Supported version

Only the latest public-test release is expected to receive security fixes.

## Macro execution risk

FreeCAD macros execute Python with the permissions of the FreeCAD process. Install only release files obtained from the project repository, verify published SHA-256 checksums, and review source before running untrusted forks.

## Reporting a vulnerability

Do not publish an exploit or malicious macro payload in a public issue. Contact the repository owner privately with:

- affected version
- attack prerequisites
- proof of concept or relevant source lines
- potential impact
- suggested mitigation if known

The repository owner should configure a private security advisory or contact address before public launch.

## Out of scope

General FreeCAD vulnerabilities, operating-system issues, and flaws in third-party add-ons should be reported to their respective projects unless this profile is required to trigger the problem.
