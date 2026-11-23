
# CV-Information-Extractor

Aplikasi ekstraksi dan standardisasi informasi Curriculum Vitae (CV) secara otomatis dari berbagai format dokumen (**PDF**, **DOCX**, dan **gambar / hasil scan via OCR**) ke dalam struktur data **JSON** yang rapi, dilengkapi antarmuka web untuk pratinjau, pencarian/filter, dan ekspor data.

## Latar Belakang & Tujuan

Membaca, menyalin, dan merekapitulasi informasi CV kandidat secara manual memakan waktu lama, rawan kesalahan ketik, serta tidak seragam karena variasi format file dan tata letak dokumen. Proyek ini bertujuan untuk:

- Mengotomatiskan ekstraksi teks dari dokumen CV berbasis teks maupun gambar/hasil scan.
- Menormalkan informasi kandidat ke dalam skema JSON yang konsisten dan terstruktur.
- Menerapkan aturan **anti-halusinasi** (`null` atau list kosong jika data memang tidak tercantum dalam CV).
- Menyediakan antarmuka web agar hasil ekstraksi mudah ditinjau, disaring, dan diekspor.

## Fitur Utama

- **Ekstraksi Multi-Format:** Mendukung dokumen PDF berbasis teks, dokumen DOCX (termasuk isi tabel), serta gambar/scan dengan *fallback* OCR (`pytesseract`).
- **Skema JSON Terstruktur & Anti-Halusinasi:** Mengelompokkan data ke dalam profil kandidat, pendidikan, pengalaman kerja, keahlian, sertifikasi, dan metadata ekstraksi tanpa mengarang informasi yang tidak ada.
- **Antarmuka Web Interaktif:** Menampilkan ringkasan metrik/kandidat, pencarian/filter, serta fitur ekspor hasil.
- **Pengujian Ekstraksi:** Dilengkapi skrip pengujian (`test_extract.py`) untuk memvalidasi proses ekstraksi.

## Struktur Berkas

```
txt
CV-Information-Extractor/
├── app.py              # Entry point / endpoint API backend (FastAPI)
├── index.html          # Antarmuka halaman web
├── style.css           # Styling antarmuka web
├── script.js           # Logika interaksi frontend & komunikasi ke API
├── requirements.txt    # Daftar dependensi Python
├── test_extract.py     # Skrip pengujian ekstraksi CV
├── LICENSE             # Lisensi proyek (MIT)
└── README.md           # Dokumentasi proyek 
```
##Cara Menjalankan Proyek
1. Persiapan Backend (Python)
Pastikan Python 3.10+ sudah terpasang di perangkat. Jika ingin menguji fitur OCR pada gambar atau PDF hasil scan, pastikan Tesseract OCR juga sudah terinstal di sistem operasi.

# Clone repositori
git clone [https://github.com/Jafar00423/CV-Information-Extractor.git](https://github.com/Jafar00423/CV-Information-Extractor.git)
cd CV-Information-Extractor

# Buat dan aktifkan virtual environment
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux / macOS:
source venv/bin/activate

# Instal dependensi
pip install -r requirements.txt

Jalankan server backend:
uvicorn app:app --reload --host 127.0.0.1 --port 8000

2. Menjalankan Frontend
Buka index.html menggunakan Live Server di editor (misalnya VS Code) atau buka langsung di browser, lalu pastikan konfigurasi URL API di script.js mengarah ke server backend yang aktif (http://127.0.0.1:8000).

3. Menjalankan Pengujian
python test_extract.py

Rencana Pengembangan Selanjutnya
Integrasi pencocokan otomatis CV terhadap Job Description (JD) dan pemeringkatan kandidat.

Peningkatan akurasi layout parsing untuk CV multi-kolom dan dokumen hasil scan beresolusi rendah.

Penambahan opsi ekspor lanjutan (seperti CSV / spreadsheet) langsung dari antarmuka web.

Lisensi
Proyek ini menggunakan lisensi MIT — lihat berkas LICENSE untuk detailnya.
