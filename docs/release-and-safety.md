# Release and safety

Use `--dry-run` to inspect release, rename, and repair plans. Non-dry-run ZIP repairs require a configured backup directory; the default is the repository-local, gitignored `.repair-backups/` directory, which is outside the shared folder. Users may choose another local directory for stronger failure isolation. Configuration and `oksg doctor` verify the directory with an exclusive create, write, flush, `fsync`, and delete probe because cloud-backed filesystems can misreport writability through Unix permission checks. Each backup is created with exclusive creation, flushed, and SHA-256 verified before any ZIP rewrite or sibling MP4 publication; no destructive no-backup mode exists.

Shared MP4 publication requires same-directory hard links for atomic no-replace publication. Unsupported filesystems fail loudly and leave the source ZIP unchanged. Do not repair a creator's only copy of a release.
