# 🎮 Vimm's Lair Downloader

CLI downloader untuk ROM/ISO dari [Vimm's Lair](https://vimm.net/vault/) — 36 sistem klasik dari Atari 2600 hingga Nintendo 3DS.

## Stack

| Komponen | Library |
|----------|---------|
| HTTP scraping | `httpx` + `BeautifulSoup4` |
| Download | `aria2c` (primer) / `wget` (fallback) / `httpx` stream |
| Proxy (SOCKS) | `socksio` |
| CLI | `click` + `rich` |
| Config | `python-dotenv` |
| Dev env | `nix flake` + `direnv` |

## Setup (NixOS + direnv)

```bash
cd vimms-lair-downloader
direnv allow          # load flake dev shell otomatis

cp .env.example .env  # edit DOWNLOAD_DIR sesuai kebutuhan
```

Setelah `direnv allow` aktif, wrapper script `./vimms` siap digunakan langsung tanpa instalasi `pip` tambahan (Nix otomatis me-link Python interpreter dan seluruh dependensi C-extension).

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

# Lihat detail game (termasuk daftar format & versi)
vimms info 17874
# → New Super Mario Bros. Wii | Format: .wbfs, .rvz | Versi: 1.1, 1.2

# Download game dengan opsi format & versi
vimms download 17874 --version 1.2 --format wbfs
vimms download 834 -o /mnt/storage/roms
```

## Struktur Output

```
DOWNLOAD_DIR/
└── Wii/
    └── New Super Mario Bros. Wii/
        └── New Super Mario Bros. Wii (USA) (En,Fr,Es) (Rev 1).wbfs
```

## Konfigurasi `.env`

| Variable | Default | Keterangan |
|----------|---------|------------|
| `DOWNLOAD_DIR` | `~/roms` | Direktori output utama |
| `ARIA2_CONNECTIONS` | `1` | Koneksi paralel aria2c (Vimm membatasi 1 koneksi per IP) |
| `HTTP_TIMEOUT` | `30` | Timeout koneksi (detik) |
| `USE_WGET` | *(kosong)* | Set `1` untuk paksa pakai wget |

## Resume Download

- **aria2c**: otomatis via `--continue=true` (dengan auto-naming dari Content-Disposition)
- **wget**: otomatis via `-c` (dengan auto-naming via `--content-disposition`)
- **httpx fallback**: tidak mendukung resume

## Cara Kerja

```
vimms download <game_id> --version 1.2 --format wbfs
       │
       ├─ GET vimm.net/vault/<game_id>
       │  ├─ Ambil mediaId dari JS array `media` berdasarkan versi
       │  └─ Ambil domain cermin download (dl2.vimm.net, dl3.vimm.net, dll)
       │
       └─ GET dl<mirror>.vimm.net/?mediaId=x&alt=y (aria2c --continue)
              ↓ fallback
          wget -c --content-disposition
              ↓ fallback
          httpx streaming GET
```
