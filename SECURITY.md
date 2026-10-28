# Security Policy

## Supported versions

Only the latest commit on `main` receives security fixes until versioned releases begin.

## Reporting a vulnerability

Please **do not open a public issue**. Use GitHub's private reporting instead:
**Security** tab → **Report a vulnerability** on this repository.

Include what is affected, steps to reproduce, and the impact you expect.
You should get a first response within 7 days.

## Deployment notes

- The HTTP service has **no authentication yet**. Run it only on a trusted LAN and do not expose port 8090
  to the internet (port forwarding, public tunnels) until token auth lands.
- The speaker is controlled with the Cast protocol, which is unauthenticated on the LAN by design;
  anyone on the same network can control the speaker regardless of this project.
