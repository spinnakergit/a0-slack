---
status: published
repo: https://github.com/spinnakergit/a0-slack
index_pr: https://github.com/agent0ai/a0-plugins/pull/66
published_date: 2026-03-13
version: 1.1.0
---

# Release Status

## Publication
- **GitHub**: https://github.com/spinnakergit/a0-slack
- **Plugin Index PR**: [#66](https://github.com/agent0ai/a0-plugins/pull/66) (CI passed)
- **Published**: 2026-03-13

## v1.1.0 (2026-03-28)

### Changes
- Migrated config.html to Alpine.js framework pattern (outer Save button for settings, custom JS retained for auth key management)
- Added hooks.py for plugin lifecycle management
- Added thumbnail.png (256x256 indexed PNG, Slack aubergine)
- Improved install.sh with in-place detection for plugin manager installs

### Notes
- Chat Bridge tab retains custom JS for auth key regeneration and clipboard copy
- Credentials/Settings/Security tabs use Alpine.js x-model bindings saved by framework outer Save
- Array fields (workspaces, allowed users) use textarea-to-array conversion

## v1.0.0 (2026-03-13)

### Verification
- **Automated Tests**: 58/58 PASS
- **Human Verification**: 70/70 PASS
- **Security Assessment**: Completed
