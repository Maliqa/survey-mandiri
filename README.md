# Survey Mandiri — Backend & Deploy (Fase 1)

Marketplace survei lapangan: **Client** (leasing / caleg / produk) memesan survei, membayar ke **escrow**, lalu job di-broadcast ke **Surveyor terverifikasi** yang cocok lokasinya. Surveyor mengambil unit, mengirim laporan (foto + GPS), dan client me-review. Setelah itu escrow dicairkan ke surveyor setelah dipotong komisi platform.

Fase 1 berisi: backend Django + Docker stack untuk VPS + CI/CD GitHub Actions.
Fase 2: app Android (Kotlin/Compose) + workflow build APK.

---

## 1. Ringkasan solusi & asumsi

| Keputusan | Pilihan | Alasan |
|---|---|---|
| Model bisnis | Komisi per job + escrow | Disepakati. Default komisi 20% (`COMMISSION_PERCENT`). |
| Penentuan harga | **Platform** pasang tarif per unit per kategori | Menyelesaikan kontradiksi step 5/6 di infografis. Harga di-snapshot saat quote, jadi perubahan tarif tidak mengubah deal yang sudah jalan. |
| Satuan kerja | **Unit** = 1 kunjungan / 1 responden | Satu model untuk semua kategori: leasing qty=1, caleg qty=1.000. |
| Pembayaran | Demo: tombol bayar instan (`DEMO_PAYMENTS=1`). Produksi: transfer manual, admin konfirmasi | Payment gateway (Midtrans/Xendit) masuk fase berikutnya. |
| Framework | Django + DRF | Django Admin langsung jadi panel verifikasi, keuangan, dan fraud review. |
| Auth | JWT (SimpleJWT): access 15 menit, refresh 14 hari, rotasi + blacklist | Cocok untuk mobile, logout benar-benar mencabut token. |
| Anti-fraud | GPS wajib, deteksi mock GPS, jarak ke titik target, foto duplikat (SHA-256), batas umur foto | Risiko terbesar bisnis ini adalah survei fiktif. |
| Offline | Laporan punya `client_uuid` dari device, retry idempotent | Surveyor di area sinyal jelek, Android menyimpan lokal lalu sync via WorkManager. |

Default tarif (bisa diubah di Admin → Pricing rates):

| Kategori | Unit | Harga/unit | Min unit |
|---|---|---|---|
| Leasing | kunjungan | Rp150.000 | 1 |
| Caleg | responden | Rp50.000 | 50 |
| Produk | responden | Rp40.000 | 20 |

## 2. Arsitektur

```
 Android (Client / Surveyor)                         Admin (browser)
          │  HTTPS + JWT                                   │ session
          ▼                                                ▼
 ┌──────────────────────── VPS (Docker Compose) ───────────────────────┐
 │ Caddy (TLS otomatis Let's Encrypt) ──► web: Django + Gunicorn        │
 │                                         │        │                   │
 │                       PostgreSQL ◄──────┘        └──► Redis ◄── worker (Celery)
 │                       volume: media (privat, tidak disajikan langsung)  beat (jadwal)
 └──────────────────────────────────────────────────────────────────────┘
          ▲
 GitHub Actions: test ► build image ► push GHCR ► SSH ke VPS ► migrate ► restart ► health check
```

**Siklus hidup request** (dijaga `select_for_update`, jadi dua surveyor yang menerima bersamaan tidak bisa over-claim):

```
quoted ─approve─► awaiting_payment ─pay─► open ⇄ assigned ─semua laporan masuk─► in_review ─complete─► completed
   └──────────────────┴────────────────────┴─► cancelled (hanya jika belum ada unit diambil; escrow di-refund)
```

- Laporan ditolak saat `in_review` membuat status kembali ke `assigned`, dan surveyor mengulang unit tersebut.
- Client tidak me-review dalam `REVIEW_WINDOW_DAYS` (default 3 hari) → auto-complete oleh Celery beat. Request yang punya laporan ber-flag fraud **dilewati** dan harus dicek manusia.

**Lapisan backend:** `views` (HTTP & permission) → `services` (aturan bisnis & transaksi) → `models`. Logika bisnis tidak ada di view, jadi bisa dites dan dipanggil dari Admin maupun Celery.

## 3. Kontrak API

Base URL: `https://<DOMAIN>/api/v1`. Dokumentasi interaktif (OpenAPI/Swagger) ada di `/api/docs`, schema di `/api/schema`.

Semua error memakai format yang sama:

```json
{"error": {"code": "quota_full", "message": "Only 1 units left.", "details": {}}}
```

| HTTP | `code` | Arti |
|---|---|---|
| 400 | `validation_error` | Input salah. `details` berisi per-field. |
| 401 | `unauthenticated` | Token tidak ada atau kedaluwarsa. Refresh dulu. |
| 403 | `forbidden`, `not_offered`, `payments_manual_only` | Role tidak sesuai atau job tidak ditawarkan ke surveyor ini. |
| 404 | `not_found` | Tidak ada atau bukan milik user (sengaja tidak membedakan). |
| 409 | `invalid_state`, `quota_full`, `already_assigned`, `already_claimed`, `units_complete`, `has_reports` | Pelanggaran aturan bisnis. |
| 422 | `quantity_out_of_range`, `invalid_timestamp`, `report_expired`, `too_many_units`, `pricing_unavailable` | Input valid tapi ditolak aturan. |
| 429 | `rate_limited` | Throttle: auth 10/menit, upload 120/menit. |

### Auth

| Method | Path | Body | Response |
|---|---|---|---|
| POST | `/auth/register/client` | `email, password, phone, client_type (leasing\|caleg\|product\|other), organization` | 201 `User` |
| POST | `/auth/register/surveyor` | **multipart**: `email, password, phone, full_name, nik (16 digit), city, service_cities[], latitude, longitude, service_radius_km, id_document (img), selfie (img)` | 201 `User` (status `pending`) |
| POST | `/auth/login` | `email, password` | `{access, refresh, user}`. JWT berisi claim `role`. |
| POST | `/auth/refresh` | `refresh` | `{access, refresh}` (refresh dirotasi) |
| POST | `/auth/logout` | `refresh` | 204 |
| GET | `/me` | – | `User` + `surveyor_profile` |

### Client

| Method | Path | Keterangan |
|---|---|---|
| GET | `/pricing` | Tarif aktif. |
| POST | `/quote` | `{category, quantity}` → `{unit_price, total_price, unit_label}` (preview, tidak disimpan). |
| POST | `/requests` | Buat request → `quoted`. Lihat body di bawah. |
| GET | `/requests?status=` | Daftar request milik client (paginated). |
| GET | `/requests/{id}` | Detail + `escrow_status` + progres per surveyor. |
| POST | `/requests/{id}/approve-quote` | `quoted` → `awaiting_payment`. |
| POST | `/requests/{id}/pay` | (Demo) Danai escrow → `open` + broadcast. |
| POST | `/requests/{id}/cancel` | Refund escrow jika belum ada unit diambil. |
| GET | `/requests/{id}/reports?flagged=true` | Laporan (paginated). `photo_url` butuh token. |
| POST | `/reports/{id}/reject` | `{reason}`. Unit dibuka lagi untuk diulang. |
| POST | `/requests/{id}/complete` | Setujui semua → escrow cair → payout. |

Body `POST /requests` (field `details` divalidasi per kategori):

```json
{
  "category": "caleg",
  "title": "Survey elektabilitas Dapil 1",
  "description": "Door-to-door, usia 17+",
  "details": {"electoral_district": "Jabar 4", "target_demographic": "17-45", "questions": ["Pilihan Anda?"]},
  "quantity": 1000,
  "target_cities": ["Sukabumi", "Kabupaten Sukabumi"],
  "address": "", "latitude": null, "longitude": null,
  "deadline": "2026-11-30"
}
```

- `leasing.details` = `{purpose: credit_worthiness|business_location|customer_verification, applicant_ref}`. Wajib `address` + `latitude` + `longitude`.
- `product.details` = `{product_name, condition: new|used, research_type: market_research|feedback, questions[]}`.

### Surveyor (hanya yang sudah terverifikasi)

| Method | Path | Keterangan |
|---|---|---|
| GET | `/jobs/available` | Job yang di-broadcast ke saya. Diurutkan dari yang terdekat. Menampilkan `unit_earning` (net setelah komisi), tanpa identitas client. |
| GET | `/jobs/{id}` | Detail job. |
| POST | `/jobs/{id}/accept` | `{units}` → 201 `Assignment`. |
| GET | `/assignments?status=` | Tugas saya. |
| POST | `/assignments/{id}/withdraw` | Mundur (hanya sebelum kirim laporan). |
| POST | `/assignments/{id}/reports` | **multipart**: `client_uuid, photo, latitude, longitude, gps_accuracy_m, captured_at, city, is_mock_location, respondent_label, answers (JSON string), notes` → 201 baru / **200 jika retry** dengan `client_uuid` sama. Response berisi `flags[]`. |
| GET | `/payouts` | Riwayat pendapatan + `totals` per status. |

### File privat

`GET /reports/{id}/photo` hanya bisa diakses pemilik request, surveyor pembuat, atau admin. `GET /admin/surveyors/{id}/id-document|selfie` hanya untuk admin. Caddy tidak pernah menyajikan media langsung.

## 4. Struktur folder

```
survey-mandiri/
├── backend/
│   ├── config/            settings (env-based), urls, celery, settings_test
│   ├── apps/core/         error envelope, JSON logging + request id, geo, upload aman, health, seed_demo
│   ├── apps/accounts/     User (login email, role), SurveyorProfile (KYC, area layanan), JWT
│   ├── apps/surveys/      PricingRate, SurveyRequest, JobOffer, Assignment, Report, services (state machine), tasks
│   ├── apps/payments/     Escrow, Payout, services (fund/refund/release)
│   ├── tests/             23 test (auth, alur penuh, fraud, idempotensi, akses file)
│   ├── Dockerfile         multi-stage, non-root, healthcheck
│   └── requirements*.txt  versi di-pin
├── deploy/                docker-compose.yml, Caddyfile, deploy.sh, .env.example
├── .github/workflows/     backend-ci.yml, backend-deploy.yml
└── android/               (fase 2)
```

## 5. Model database

| Tabel | Isi penting |
|---|---|
| `accounts_user` | `email` (unik, login), `role` (client/surveyor/admin), `client_type`, `organization`, `phone` |
| `accounts_surveyorprofile` | `status` (pending/verified/rejected/suspended), `nik_last4` (NIK penuh **tidak disimpan**), foto KTP & selfie (privat), `city_normalized`, `service_cities`, lat/lon, `service_radius_km` |
| `surveys_pricingrate` | tarif per kategori, min/max unit |
| `surveys_surveyrequest` | snapshot `unit_price`, `total_price`, `commission_percent`; `quantity`, `claimed_units` (CHECK ≤ quantity), `status`, `target_cities`, lat/lon opsional |
| `surveys_joboffer` | hasil broadcast (unik request+surveyor), `distance_km` |
| `surveys_assignment` | surveyor ↔ request, `units`, unik per surveyor aktif |
| `surveys_report` | `client_uuid` (unik, untuk idempotensi), foto + `photo_sha256`, GPS + akurasi, `captured_at`, `flags[]`, status |
| `payments_escrow` | 1:1 request, `amount`, `method`, status funded/released/refunded, `platform_fee` |
| `payments_payout` | per surveyor per escrow: `gross`, `fee`, `net`, status pending/paid |

Migration ada di `apps/*/migrations`. `surveys/0002_seed_pricing` mengisi tarif default.

Uang disimpan sebagai **integer rupiah**, bukan float, jadi tidak ada error pembulatan.

## 6. Testing

```bash
cd backend
pip install -r requirements-dev.txt
python -m pytest                                    # SQLite lokal
DATABASE_URL=postgres://... python -m pytest        # seperti di CI
```

Cakupan test: register/login/logout + blacklist, validasi upload gambar palsu, matching broadcast per kota/radius, over-claim kuota, alur penuh 2 surveyor dengan perhitungan escrow & payout, retry laporan idempotent, flag fraud (jauh, mock GPS, foto duplikat), aturan timestamp, reject → ulang, cancel/refund, withdraw, isolasi data antar client, auto-complete melewati laporan ber-flag, dan mode pembayaran manual.

## 7. Menjalankan

### Lokal (tanpa Docker)

```bash
cd backend
pip install -r requirements-dev.txt
export DJANGO_DEBUG=1
python manage.py migrate
python manage.py seed_demo --password 'DemoPass#2026'
python manage.py runserver 0.0.0.0:8000      # Celery otomatis eager (tanpa Redis)
# Swagger: http://localhost:8000/api/docs   Admin: http://localhost:8000/admin/
```

### Deploy demo ke VPS (sekali setup)

1. **VPS:** install Docker (`curl -fsSL https://get.docker.com | sh`) dan buka port 22/80/443 di firewall.
2. **Kunci deploy** (jalankan di VPS):
   ```bash
   ssh-keygen -t ed25519 -f ~/.ssh/gh_deploy -N "" -C github-actions
   cat ~/.ssh/gh_deploy.pub >> ~/.ssh/authorized_keys
   cat ~/.ssh/gh_deploy                 # isi untuk secret VPS_SSH_KEY
   ssh-keyscan -t ed25519 <IP-VPS>      # isi untuk secret VPS_KNOWN_HOSTS
   ```
3. **GitHub → Settings → Secrets and variables → Actions**, isi:

   | Secret | Isi |
   |---|---|
   | `VPS_HOST` | IP VPS |
   | `VPS_USER` | user SSH (misalnya `root`) |
   | `VPS_PORT` | opsional, default 22 |
   | `VPS_SSH_KEY` | private key dari langkah 2 |
   | `VPS_KNOWN_HOSTS` | output `ssh-keyscan` |

   Variable opsional `DEMO_DOMAIN`: kalau tidak diisi, dipakai `<ip-dengan-minus>.sslip.io` (HTTPS gratis tanpa beli domain).
4. **Actions → Backend Deploy → Run workflow.** Deploy pertama otomatis membuat `.env` (secret acak, password DB, path admin acak) dan akun demo.
5. Lihat URL dan password demo di VPS:
   ```bash
   cat ~/sm-demo/demo-credentials.txt
   ```

Setelah itu, setiap push ke `main` otomatis ter-deploy.

Rollback: `./deploy.sh sha-<commit-lama>` di VPS.

### Environment variables

Lihat `deploy/.env.example`. Yang paling penting:

| Variabel | Default | Fungsi |
|---|---|---|
| `DJANGO_SECRET_KEY` | – (wajib) | Kunci tanda tangan JWT/session. |
| `DOMAIN` | – | Domain untuk Caddy/TLS. |
| `DATABASE_URL`, `REDIS_URL`, `CELERY_BROKER_URL` | – | Koneksi infrastruktur. |
| `DJANGO_ADMIN_URL` | `admin/` | Ganti ke path acak di produksi. |
| `COMMISSION_PERCENT` | 20 | Komisi platform. |
| `MAX_UNITS_PER_SURVEYOR` | 50 | Batas unit per surveyor per request. |
| `REPORT_MAX_DISTANCE_KM` | 2 | Jarak maksimal dari titik target sebelum di-flag. |
| `REPORT_MAX_AGE_HOURS` | 72 | Umur foto maksimal saat dikirim (cukup untuk sync offline). |
| `REVIEW_WINDOW_DAYS` | 3 | Batas waktu review client sebelum auto-complete. |
| `DEMO_PAYMENTS` | 1 | `0` = hanya transfer manual yang dikonfirmasi admin. |

## 8. Risiko, trade-off & rekomendasi

**Trade-off yang diambil**
- **Matching broadcast dihitung di Python** (iterasi surveyor terverifikasi). Cukup untuk ratusan sampai beberapa ribu surveyor. Lebih dari itu, pindah ke PostGIS + query `ST_DWithin`.
- **Notifikasi:** Android melakukan polling `/jobs/available`. Hook FCM sudah disiapkan di `services.broadcast`.
- **Foto di volume lokal VPS.** Cukup untuk demo. Untuk produksi, pakai object storage (S3-compatible) + backup.
- **Deteksi mock GPS bergantung pada kejujuran device** (`Location.isMock()`), karena di HP yang di-root bisa diakali. Itu sebabnya ada lapisan kedua: jarak, foto duplikat, dan umur foto.

**Risiko yang perlu ditangani sebelum produksi nyata**
1. **UU PDP:** foto KTP, selfie, dan data responden adalah data pribadi. Perlu kebijakan privasi, persetujuan responden, masa retensi, dan enkripsi backup. Desain saat ini sudah meminimalkan data: NIK hanya disimpan 4 digit terakhir, file privat, dan akses admin ke KTP tercatat di log.
2. **Survei caleg:** jika hasilnya dipublikasikan, cek aturan KPU tentang lembaga survei.
3. **Escrow sungguhan:** memegang dana pihak ketiga punya implikasi regulasi. Pakai fitur escrow/split payment dari payment gateway berizin, jangan menahan dana di rekening sendiri.
4. **Backup Postgres:** tambahkan `pg_dump` terjadwal ke luar VPS. Ini belum ada di stack demo.

**Rekomendasi lanjutan (urut prioritas)**
1. Fase 2: app Android + workflow build APK (GitHub Releases).
2. FCM push untuk broadcast job.
3. Rating surveyor oleh client (kolom `rating_avg` sudah ada).
4. Kuesioner dinamis untuk caleg/produk (`answers` sudah berupa JSON).
5. Payment gateway (Midtrans/Xendit) + webhook.
6. Monitoring: Sentry + uptime check ke `/api/health`.

---

## Laporan survei (web + PDF)

Setiap order punya halaman laporan yang rapi di `/laporan/<token>/`. Isinya ringkasan, peta lokasi (OpenStreetMap), foto, GPS, jarak ke titik target, jawaban, dan tanda fraud. Laporan juga bisa diunduh sebagai PDF di `/laporan/<token>/pdf`.

- **Client (app):** buka detail order, lalu tap **Laporan Lengkap** atau **Unduh PDF**. App mengambil link dari `GET /api/v1/requests/{id}/report-link`.
- **Admin:** buka *Survey requests*, lalu kolom **Laporan** (Lihat / PDF).
- **Keamanan:** token ditandatangani (`django.core.signing`) dan kedaluwarsa setelah `REPORT_LINK_HOURS` (default 72 jam). Siapa pun yang memegang link bisa membuka laporan, jadi link boleh diteruskan ke komite kredit, tapi jangan disebar luas. Halaman memakai `noindex` dan `no-referrer`.
- **Panel admin → Reports:** thumbnail foto, badge fraud merah, filter *Mencurigakan/Bersih*, link Google Maps, dan jarak ke titik target.

# Fase 2 — App Android

Satu aplikasi untuk dua role. Setelah login, app otomatis membuka mode **Client** atau **Surveyor** sesuai akun. Akun admin tetap memakai panel web.

**Distribusi ke customer:** buka `https://103-54-170-83.sslip.io/download/` di HP, unduh APK, lalu instal. Setiap push ke `android/**` memicu workflow `Android APK` yang menjalankan unit test, build APK, membuat GitHub Release `android-v0.1.N`, dan meng-upload APK ke VPS.

| Layar | Fungsi |
|---|---|
| Login / Daftar Client / Daftar Surveyor | Daftar surveyor: KTP + selfie lewat kamera, GPS domisili, radius layanan. |
| Client: daftar permintaan → buat → detail | Form per kategori (leasing: alamat + titik GPS; caleg/produk: daftar pertanyaan). Alur: setujui harga → bayar (demo, ke escrow) → pantau progres → review laporan (foto + flag fraud) → tolak / selesaikan. |
| Surveyor: Job / Tugas / Dompet | Job di area sekitar (diurutkan dari yang terdekat), ambil unit, isi laporan (foto kamera + GPS + jawaban), riwayat pendapatan. |

**Offline-first:** laporan disimpan dulu di HP (`filesDir/pending_reports`: JSON + JPEG), lalu dikirim oleh WorkManager saat ada sinyal. Pengiriman memakai `client_uuid` dari HP, jadi retry tidak pernah membuat laporan ganda. Error yang bersifat permanen (misalnya ditolak server) ditampilkan di layar tugas dengan opsi kirim ulang atau hapus.

**Keamanan & anti-fraud di sisi app:** JWT disimpan di storage privat app. Saat access token kedaluwarsa (401), token di-refresh otomatis sekali; kalau refresh token ditolak, user kembali ke login. Foto hanya dari kamera (bukan galeri), dikompres maksimal 1600 px dengan rotasi EXIF diperbaiki. Flag `isMock` dari GPS ikut dikirim. Foto laporan diambil lewat endpoint privat dengan token.

**Struktur:**
```
android/app/src/main/java/id/surveymandiri/app/
├── SurveyApp.kt, MainActivity.kt
├── data/   ApiModels, ApiService (Retrofit), Network (token, refresh, error), AppContainer (DI manual), PendingReports (outbox + UploadWorker)
├── util/   DeviceUtils (kompres foto, GPS + deteksi mock)
└── ui/     Common, Capture (kamera/lokasi), AuthScreens, ClientScreens, SurveyorScreens, AppNav
```

**Trade-off yang disengaja:**
- **DI manual, bukan Hilt.** Build hanya berjalan di CI, jadi lebih sedikit annotation processing berarti lebih sedikit titik gagal. Mudah dimigrasi ke Hilt nanti.
- **Outbox berbasis file, bukan Room.** Alasannya sama. Strukturnya sudah siap dipindah ke Room.
- **APK ditandatangani `android/app/demo.keystore`** (di-commit, khusus demo) supaya update APK bisa langsung menimpa versi lama. Sebelum rilis ke Play Store, ganti dengan keystore rahasia di GitHub Secrets.
- **Teks UI di-hardcode dalam Bahasa Indonesia.** Pindahkan ke `strings.xml` kalau butuh multi-bahasa.

**Build lokal** (Android Studio atau CLI, JDK 17):
```bash
cd android
./gradlew :app:testDebugUnitTest :app:assembleDebug
# server lain: ./gradlew assembleDebug -PapiBaseUrl=https://api.domainlu.id/
```
