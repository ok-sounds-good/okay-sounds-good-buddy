# Changelog

## 0.1.0 - 2026-07-11

Initial public release of the `oksg` karaoke workflow helper:

- Create song workspaces, thumbnails, source audio, release ZIPs, MP4s, and upload notes.
- Audit and normalize creator-coded shared releases on macOS, Linux, WSL, and Windows.
- Keep creator configuration, branding, assets, and working media outside the package.
- Require explicit configuration before writes and support dry-run previews.
- Validate CD+G ZIPs strictly and create exclusive, checksum-verified backups before mutation.
- Stage and verify MP4 output, publish without replacement through hard links, and preserve atomic transaction order and failure cleanup.
