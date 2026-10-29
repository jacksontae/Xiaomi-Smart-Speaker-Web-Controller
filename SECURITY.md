# Security Policy

## Supported versions

Only the latest commit on `main` receives security fixes until versioned releases begin.

## Reporting a vulnerability

Please **do not open a public issue**. Use GitHub's private reporting instead:
**Security** tab → **Report a vulnerability** on this repository.

Include what is affected, steps to reproduce, and the impact you expect.
You should get a first response within 7 days.

## Deployment notes

- Control endpoints require a Bearer token (`./speakerctl token`). Media links fetched by the speaker are
  HMAC-signed with that token and expire after 6 hours. Rotate with `./speakerctl token --rotate`.
- The service speaks plain HTTP, so the token crosses the LAN unencrypted. For remote access use an encrypted
  path (Tailscale, an HTTPS tunnel) and never forward port 8090 to the internet directly.
- The speaker is controlled with the Cast protocol, which is unauthenticated on the LAN by design;
  anyone on the same network can control the speaker regardless of this project.
