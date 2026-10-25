# Security and privacy reports

For a vulnerability or accidental data exposure, use this repository's **Security → Report a vulnerability** feature. If private reporting is unavailable, open a minimal issue requesting a private contact without posting the sensitive material.

Include the affected version, module, a reproducer using fictional data, and the impact. Do not paste a token, private key, raw SSH command, remote address or unredacted screenshot. Revoke an exposed credential through its issuer rather than waiting for a code change.

This project has no telemetry endpoint. Credentials remain handled by OpenSSH, but the program does execute a read-only metrics collector over SSH when the remote module is enabled. Optional preload hooks run inside the user's file-manager process. The trust boundaries and retained local data are described in [docs/privacy.md](docs/privacy.md).

The initial supported development series is 0.1.x. No response-time SLA is offered.
