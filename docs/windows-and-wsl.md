# Windows and WSL

Native Windows uses `setup.ps1` and an `oksg.cmd` shim. Review any `winget`, Scoop, or PATH change yourself; setup does not silently install packages or call `setx`.

WSL is a Linux installation: run `setup.sh` inside the distribution and use paths such as `/mnt/c/Users/Alice/Music/Karaoke`. If a Windows path is pasted, translate it with `wslpath` and confirm it. Keep all configured paths in the same environment; cloud-synced `/mnt/c` workspaces may be slower.
