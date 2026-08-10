# 🎮 Vimm's Lair Downloader

CLI downloader untuk ROM/ISO dari [Vimm's Lair](https://vimm.net/vault/) — mendukung 36 sistem klasik dari Atari 2600 hingga Nintendo 3DS.

---

## 🚀 Fitur Utama

- **Native Nix Package & Cross-Platform**: Siap dijalankan via `nix run`, `nix build`, maupun `pip`/`pipx`/`uv` di Linux, macOS, dan Windows.
- **Downloader Strategy Pattern**: Urutan otomatis `aria2c` (multi-koneksi & resume) → `wget` → `httpx` streaming fallback (pure Python).
- **Konfigurasi Terpusat**: Pengaturan `.env` fleksibel (`DOWNLOAD_DIR`, `HTTP_TIMEOUT`, `ARIA2_CONNECTIONS`).
- **Antarmuka CLI Rich**: Tampilan tabel interaktif dan indikator progress download.

---

## 🛠️ Instalasi & Pemakaian

### A. Pengguna Nix (NixOS / Home Manager / Flakes)

#### 1. Jalankan Langsung (Tanpa Instalasi)
```bash
nix run github:XiaoXioe/vimms-lair-downloader -- list-systems
nix run github:XiaoXioe/vimms-lair-downloader -- search "mario" -s NES
```

#### 2. Kompilasi Lokal (`nix build`)
```bash
nix build
./result/bin/vimms --help
```

#### 3. Integrasi ke Flake NixOS / Home Manager
Tambahkan input proyek di `flake.nix` Anda:
```nix
inputs.vimms-downloader.url = "github:XiaoXioe/vimms-lair-downloader";
```
Lalu tambahkan ke paket sistem:
```nix
environment.systemPackages = [
  inputs.vimms-downloader.packages.${pkgs.stdenv.hostPlatform.system}.default
];
```

#### 4. Development Environment (`nix develop` / `direnv`)
```bash
direnv allow   # Memuat dev shell otomatis
vimms --help   # Menggunakan biner vimms dari devShell / environment
```

---

### B. Pengguna Non-Nix (Linux / macOS / Windows dengan Python 3.11+)

#### 1. Via `pipx` (Direkomendasikan)
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
source .venv/bin/activate  # Linux/macOS (.venv\Scripts\activate di Windows)
pip install .
```

#### 4. Cara Uninstal (Non-Nix)
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

> 💡 **Catatan Dependensi Sistem Non-Nix**:
> `vimms` secara otomatis bekerja tanpa butuh alat tambahan (*fallback* ke Python `httpx`). Untuk mendapatkan fitur download multi-koneksi tercepat, Anda dapat menginstal `aria2` di OS Anda:
> - **Ubuntu/Debian**: `sudo apt install aria2`
> - **Arch Linux**: `sudo pacman -S aria2`
> - **macOS**: `brew install aria2`
> - **Windows**: `choco install aria2` atau `scoop install aria2`

---

## 📖 Penggunaan CLI

```bash
# Lihat semua sistem tersedia
vimms list-systems

# Cari game di vault
vimms search "mario" --system NES
vimms search "zelda" -s N64 -l 10

# Browse per sistem / huruf awal
vimms browse SNES
vimms browse NES -l M

# Lihat detail game (format & opsi versi)
vimms info 17874

# Download game ke lokasi default (~/roms/<SYSTEM>/<JUDUL>/)
vimms download 17874 --version 1.2 --format wbfs

# Download ke lokasi kustom
vimms download 834 -o /mnt/storage/roms
```

---

## ⚙️ Konfigurasi `.env`

| Variable | Default | Keterangan |
| :--- | :--- | :--- |
| `DOWNLOAD_DIR` | `~/roms` | Direktori output utama |
| `ARIA2_CONNECTIONS` | `1` | Koneksi paralel `aria2c` (Vimm membatasi 1 koneksi per IP) |
| `HTTP_TIMEOUT` | `30` | Timeout koneksi HTTP (detik) |
| `USE_WGET` | *(kosong)* | Set `1` untuk memaksa penggunaan `wget` |

---

## 🏗️ Arsitektur Downloader Strategy

```
vimms download <game_id> --version 1.2 --format wbfs
       │
       ├─ GET vimm.net/vault/<game_id> (VimmScraper)
       │  ├─ Ambil mediaId dari JS array `media`
       │  └─ Ambil domain cermin download (dl2.vimm.net, dl3.vimm.net)
       │
       └─ Download Strategy Fallback (download_game)
              ├─ 1. Aria2Downloader (aria2c --continue=true)
              ├─ 2. WgetDownloader  (wget -c --content-disposition)
              └─ 3. HttpxDownloader (httpx GET streaming fallback)
```
