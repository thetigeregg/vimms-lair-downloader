# 🎮 Vimm's Lair Downloader

CLI downloader for ROMs/ISOs from [Vimm's Lair](https://vimm.net/vault/) — supports 36 classic systems from Atari 2600 to Nintendo 3DS.

---

## 🚀 Key Features

- **Native Nix Package & Cross-Platform**: Ready to run via `nix run`, `nix build`, or `pip`/`pipx`/`uv` on Linux, macOS, and Windows.
- **aria2c-powered downloads**: Resume support plus automatic retry with increasing backoff on any failed attempt — connection errors, timeouts, or HTTP error responses (e.g. Vimm's Lair's single-connection-per-IP rate limit).
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
> `vimms` requires `aria2` to be installed for the `download` command to work — install it on your OS:
> - **Ubuntu/Debian**: `sudo apt install aria2`
> - **Arch Linux**: `sudo pacman -S aria2`
> - **macOS**: `brew install aria2`
> - **Windows**: `choco install aria2` or `scoop install aria2`
>
> Vimm's Lair always serves downloads as `.7z` archives. To use `--extract`, also install `7z` (`p7zip-full` on Debian/Ubuntu, `p7zip` on Arch/macOS Homebrew/Windows).
>
> `--extract-xiso` (for Xbox/Xbox 360 games) needs the [`extract-xiso`](https://github.com/XboxDev/extract-xiso) binary on `PATH`. It isn't packaged for apt/Homebrew, so non-Nix/non-Docker users need to build it themselves (`cmake -S . -B build && cmake --build build`) and install the resulting binary. Docker and Nix builds already include it.
>
> `--zar` needs the [`zarchive`](https://github.com/Exzap/ZArchive) binary on `PATH` (also not packaged for apt/Homebrew — build it the same way, plus `libzstd` dev headers: `sudo apt install libzstd-dev` / `brew install zstd`). Docker and Nix builds already include it too.

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

# Download and extract the .7z archive in place (kept alongside the extracted files)
vimms download 17874 --latest --extract

# Download, extract, and delete the .7z archive once extraction succeeds
vimms download 17874 --latest --extract --delete-archive

# Xbox 360: unzip the .7z, then run extract-xiso on the resulting .iso to get
# a folder (with default.xex etc.) ready for Xenia Canary/Edge
vimms download 15323 --latest --format xiso.iso --extract --extract-xiso

# Same, but also clean up the intermediate .7z and .iso, keeping only the
# extracted folder
vimms download 15323 --latest --format xiso.iso --extract --delete-archive --extract-xiso --delete-iso

# Xbox 360, full pipeline: unzip, extract the xiso, then pack the result into
# a .zar for Xenia Canary/Edge (smaller than the raw .iso, e.g. ~7.3GB -> ~4.8GB)
vimms download 15323 --latest --format xiso.iso --extract --extract-xiso --zar

# Same, but clean up every intermediate (.7z, .iso, extracted folder), keeping
# only the final .zar
vimms download 15323 --latest --format xiso.iso \
  --extract --delete-archive --extract-xiso --delete-iso --zar --delete-xex-folder

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

## 🏗️ Download Architecture

```
vimms download <game_id> --version 1.2 --format wbfs
       │
       ├─ GET vimm.net/vault/<game_id> (VimmScraper)
       │  ├─ Extract mediaId from the JS `media` array
       │  └─ Extract the download mirror domain (dl2.vimm.net, dl3.vimm.net)
       │
       └─ download_game(): aria2c --continue=true
              │  On any failure (connection error, timeout, HTTP error, ...):
              │  retry with increasing delay (5s, 10s, 20s, ...), up to
              │  5 attempts, resuming via -c each time
              │
              ├─ --extract: 7z x  → the game's .7z archive
              │
              └─ --extract-xiso: extract-xiso -x → the extracted .iso
                     (Xbox/Xbox 360 only — exposes default.xex etc. for Xenia)
                     │
                     └─ --zar: zarchive → the extracted folder
                            (zstd-compressed .zar, smaller than the raw .iso)
```

### Pipelined downloads + post-processing

When queuing more than one game ID with any post-processing flag (`--extract`, `--extract-xiso`, `--zar`), downloads and post-processing run in two independently-paced lanes instead of one item's full pipeline blocking the next:

- **Downloads** stay strictly sequential — one at a time, respecting `--wait` and Vimm's Lair's single-connection-per-IP limit.
- **Post-processing** (7z/extract-xiso/zarchive) also stays strictly sequential — one item at a time, in the order downloads complete — but runs concurrently with the download lane.

So item 2's download starts the moment item 1's download finishes, even if item 1 is still being extracted/converted/packed; if item 2 finishes downloading before item 1's post-processing is done, it just waits its turn. This kicks in automatically whenever it applies — no flag needed. A single ID, or a queue with no post-processing flags, is unaffected and behaves exactly as before.
