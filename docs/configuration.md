# Configuration

Each clone uses an ignored `.config.toml`; copy `.config.example.toml` as a starting point or run `oksg configure`.

`karaoke_root` and `shared_folder` must be absolute existing directories. By default, `oksg configure` places `repair_backup_dir` in the repository's gitignored `.repair-backups/` directory. The configured value must be an absolute path to an existing directory outside the shared folder. It may instead point to another local backup directory when stronger failure isolation is desired. Before accepting it, setup and `oksg doctor` perform an exclusive create, write, flush, `fsync`, and delete probe; this catches filesystem restrictions that Unix permission checks can miss. Repairs copy and SHA-256 verify an exclusive, timestamped backup before changing a ZIP.

`creator_code` is three to eight uppercase letters/digits, beginning with a letter. New releases use four digits (`CODE-0001 - Artist - Title`); three-digit legacy names are accepted only when parsing existing releases. `--config PATH` selects another configuration.

Logos are never copied into the repository. `font_dirs` points to creator-managed `.ttf`, `.otf`, or `.ttc` directories. Direct `--font`, `--font.release`, `--font.band`, `--font.song`, and `--font.banner` values take precedence. If no font is found, Pillow's default is used.
