# 🎮 Vimm's Lair Downloader

CLI downloader untuk ROM/ISO dari [Vimm's Lair](https://vimm.net/vault/) — 36 sistem klasik dari Atari 2600 hingga Nintendo 3DS.

## Stack

| Komponen | Library |
|----------|---------|
| HTTP scraping | `httpx` + `BeautifulSoup4` |
| Download | `aria2c` (primer) / `wget` (fallback) / `httpx` stream |
| CLI | `click` + `rich` |
| Config | `python-dotenv` |
| Dev env | `nix flake` + `direnv` |

## Setup (NixOS + direnv)

```bash
cd vimms-lair-downloader
direnv allow          # load flake dev shell otomatis

cp .env.example .env  # edit DOWNLOAD_DIR sesuai kebutuhan
pip install -e .      # install CLI dalam mode editable
```

## Penggunaan

```bash
# Lihat semua sistem tersedia
vimms list-systems

# Cari game
vimms search "mario" --system NES
vimms search "zelda" -s N64 -l 10

# Browse per sistem / huruf
vimms browse SNES
vimms browse NES -l M

# Lihat detail game (tanpa download)
vimms info 834
# → Super Mario Bros. | Media ID: 818 | 31 KB

# Download game
vimms download 834
vimms download 834 -o /mnt/storage/roms
```

## Struktur Output

```
DOWNLOAD_DIR/
└── Nintendo/
    └── Super Mario Bros./
        └── Super Mario Bros. (World).nes
```

## Konfigurasi `.env`

| Variable | Default | Keterangan |
|----------|---------|------------|
| `DOWNLOAD_DIR` | `~/roms` | Direktori output utama |
| `ARIA2_CONNECTIONS` | `4` | Koneksi paralel aria2c |
| `HTTP_TIMEOUT` | `30` | Timeout koneksi (detik) |
| `USE_WGET` | *(kosong)* | Set `1` untuk paksa pakai wget |

## Resume Download

- **aria2c**: otomatis via `--continue=true`
- **wget**: otomatis via `-c`
- **httpx fallback**: tidak mendukung resume

## Cara Kerja

```
vimms download <game_id>
       │
       ├─ GET vimm.net/vault/<game_id>   ← ambil mediaId dari hidden input
       │
       ├─ POST dl3.vimm.net (mediaId=x) ← tangkap redirect URL
       │
       └─ aria2c --continue <URL>        ← download dengan resume
              ↓ fallback
          wget -c <URL>
              ↓ fallback
          httpx streaming POST
```
