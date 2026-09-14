# Changelog

## 0.1.4

- Retry failed reads once using a new WebSocket connection.
- Detect empty replies, invalid JSON and incomplete values before updating state.
- Keep the previous value for a failed command while refreshing the other values.
- Report the integration as unavailable only when every command fails; recover automatically.
- Show values that have never been read as unknown.
- Bound connection timeouts and keep writes single-attempt.
- Publish a versioned GitHub release so HACS can download the tag archive instead of treating a commit hash as a branch.
- Verify the HACS archive and run 44 regression tests against both minimum and current WebSocket environments.

After downloading version 0.1.4 in HACS, restart Home Assistant. Existing configuration is preserved.
