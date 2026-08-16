# 🎮 Vimm's Lair Downloader

CLI downloader for ROMs/ISOs from [Vimm's Lair](https://vimm.net/vault/) — supports 36 classic systems from Atari 2600 to Nintendo 3DS.

---

## 🚀 Key Features

- **Native Nix Package & Cross-Platform**: Ready to run via `nix run`, `nix build`, or `pip`/`pipx`/`uv` on Linux, macOS, and Windows.
- **Downloader Strategy Pattern**: Automatic fallback order `aria2c` (multi-connection & resume) → `wget` → `httpx` streaming (pure Python).
- **Centralized Configuration**: Flexible `.env` settings (`DOWNLOAD_DIR`, `HTTP_TIMEOUT`, `ARIA2_CONNECTIONS`).
- **Rich CLI Interface**: Interactive tables and download progress indicators.

---

## 🛠️ Installation & Usage

### A. Nix Users (NixOS / Home Manager / Flakes)

#### 1. Run Directly (No Installation)
```bash
nix run github:XiaoXioe/vimms-lair-downloader -- list-systems
nix run github:XiaoXioe/vimms-lair-downloader -- search "mario" -s NES
```

#### 2. Build Locally (`nix build`)
```bash
nix build
./result/bin/vimms --help
```

#### 3. Integrate into a NixOS / Home Manager Flake
Add the project as an input in your `flake.nix`:
```nix
inputs.vimms-downloader.url = "github:XiaoXioe/vimms-lair-downloader";
```
Then add it to your system packages:
```nix
environment.systemPackages = [
  inputs.vimms-downloader.packages.${pkgs.stdenv.hostPlatform.system}.default
];
```

#### 4. Development Environment (`nix develop` / `direnv`)
```bash
direnv allow   # Automatically load the dev shell
vimms --help   # Uses the vimms binary from the devShell / environment
```

---

### B. Non-Nix Users (Linux / macOS / Windows with Python 3.11+)

#### 1. Via `pipx` (Recommended)
```bash
pipx install git+https://github.com/XiaoXioe/vimms-lair-downloader.git
```

#### 2. Via `uv`
```bash
uv tool install git+https://github.com/XiaoXioe/vimms-lair-downloader.git
```

#### 3. Via `pip` (Virtual Environment)
```bash
git clone https://github.com/XiaoXioe/vimms-lair-downloader.git
cd vimms-lair-downloader

python -m venv .venv
source .venv/bin/activate  # Linux/macOS (.venv\Scripts\activate on Windows)
pip install .
```

#### 4. Uninstalling (Non-Nix)
- **Via `uv`**:
  ```bash
  uv tool uninstall vimms-lair-downloader
  ```
- **Via `pipx`**:
  ```bash
  pipx uninstall vimms-lair-downloader
  ```
- **Via `pip`**:
  ```bash
  pip uninstall vimms-lair-downloader
  ```

> 💡 **Non-Nix System Dependency Note**:
> `vimms` works out of the box without any extra tools (falls back to Python `httpx`). To get the fastest multi-connection download support, you can install `aria2` on your OS:
> - **Ubuntu/Debian**: `sudo apt install aria2`
> - **Arch Linux**: `sudo pacman -S aria2`
> - **macOS**: `brew install aria2`
> - **Windows**: `choco install aria2` or `scoop install aria2`

---

## 📖 CLI Usage

```bash
# List all available systems
vimms list-systems

# Search for a game in the vault
vimms search "mario" --system NES
vimms search "zelda" -s N64 -l 10

# Browse by system / starting letter
vimms browse SNES
vimms browse NES -l M

# View game details (formats & version options)
vimms info 17874

# Download a game to the default location (~/roms/<SYSTEM>/<TITLE>/)
vimms download 17874 --version 1.2 --format wbfs

# Download to a custom location
vimms download 834 -o /mnt/storage/roms

# Queue multiple downloads (Vimm only allows 1 connection at a time), always
# grabbing the newest version of each, with a 5s pause between downloads
vimms download 17874 8342 12345 --latest --format wbfs --wait 5
```

---

## ⚙️ `.env` Configuration

| Variable | Default | Description |
| :--- | :--- | :--- |
| `DOWNLOAD_DIR` | `~/roms` | Main output directory |
| `ARIA2_CONNECTIONS` | `1` | Parallel `aria2c` connections (Vimm limits to 1 connection per IP) |
| `HTTP_TIMEOUT` | `30` | HTTP connection timeout (seconds) |
| `USE_WGET` | *(empty)* | Set to `1` to force the use of `wget` |

---

## 🐳 Docker (Synology NAS)

Run `vimms` via Docker/Container Manager on a Synology NAS (e.g. DS920+), with `aria2c` built in and the download folder mounted to a DSM shared folder.

#### 1. Prepare
- Copy this project (via `git clone` or File Station) onto the NAS, e.g. to `/volume1/docker/vimms-lair-downloader`.
- Create a shared folder for the downloads (e.g. `downloads`) via **Control Panel > Shared Folder** or File Station.
- Find your DSM user's uid/gid over SSH: `id <username>` — used in the `user:` field so downloaded files aren't owned by `root`.

#### 2. Edit `docker-compose.yml`
- Set `user: "<uid>:<gid>"` to match the `id <username>` output above (applies to both the main process and `docker exec`).
- Change the `volumes:` line to point at your DSM shared folder, e.g.:
  ```yaml
  volumes:
    - /volume1/downloads/roms:/roms
  ```

#### 3. Build and run
`docker-compose.yml` only runs the `vimm:latest` image — it does not build it. Build it once first:
```bash
docker build -t vimm:latest .
```
Then, over SSH:
```bash
docker compose up -d
```
Or import `docker-compose.yml` as a **Project** in **Container Manager** (DSM 7+), after building the image via the Container Manager **Image** tab.

Whenever you update the source, rebuild the image (`docker build -t vimm:latest .`) and recreate the container (`docker compose up -d`).

The container stays idle (`sleep infinity`); run `vimms` commands via `docker exec`:
```bash
docker exec -it vimms-lair-downloader vimms list-systems
docker exec -it vimms-lair-downloader vimms search "mario" -s NES
docker exec -it vimms-lair-downloader vimms download 17874 -f wbfs -v 1.2
```

Downloaded files will appear in the mounted DSM shared folder, owned by whatever `user:` you configured.

---

## 🏗️ Downloader Strategy Architecture

```
vimms download <game_id> --version 1.2 --format wbfs
       │
       ├─ GET vimm.net/vault/<game_id> (VimmScraper)
       │  ├─ Extract mediaId from the JS `media` array
       │  └─ Extract the download mirror domain (dl2.vimm.net, dl3.vimm.net)
       │
       └─ Download Strategy Fallback (download_game)
              ├─ 1. Aria2Downloader (aria2c --continue=true)
              ├─ 2. WgetDownloader  (wget -c --content-disposition)
              └─ 3. HttpxDownloader (httpx GET streaming fallback)
```
