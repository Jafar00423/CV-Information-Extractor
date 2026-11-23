# -*- coding: utf-8 -*-
"""
Skrip uji coba ekstraksi CV lewat API endpoint.
Jalankan: python test_extract.py
"""
import sys
import io
# Paksa stdout pakai UTF-8 agar karakter khusus tidak error di Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import requests
import json

PDF_PATH = r"C:\Users\Jafar\Documents\Sampel CV Uji Coba (3 Profil).pdf"
URL      = "http://localhost:8000/api/extract"

print("=" * 60)
print("  UJI COBA CV INFORMATION EXTRACTOR")
print("=" * 60)

# 1. Health check
try:
    h = requests.get("http://localhost:8000/api/health", timeout=5)
    cap = h.json()["capabilities"]
    print(f"\n[HEALTH] Status     : {h.json()['status'].upper()}")
    print(f"[HEALTH] PDF Text   : {cap['pdf_text']}")
    print(f"[HEALTH] DOCX       : {cap['docx']}")
    print(f"[HEALTH] OCR        : {cap['ocr']}")
    print(f"[HEALTH] PDF+OCR    : {cap['pdf_ocr']}")
except Exception as e:
    print(f"[ERROR] Server tidak bisa dihubungi: {e}")
    sys.exit(1)

# 2. Kirim file PDF
print(f"\n[UPLOAD] Mengirim file: {PDF_PATH}")
try:
    with open(PDF_PATH, "rb") as f:
        filename = PDF_PATH.split("\\")[-1]
        resp = requests.post(
            URL,
            files=[("files", (filename, f, "application/pdf"))],
            timeout=60
        )
except Exception as e:
    print(f"[ERROR] Gagal mengirim: {e}")
    sys.exit(1)

if resp.status_code != 200:
    print(f"[ERROR] HTTP {resp.status_code}: {resp.text}")
    sys.exit(1)

data = resp.json()
print(f"\n[HASIL] HTTP Status  : {resp.status_code}")
print(f"[HASIL] Berhasil     : {data['success']} kandidat")
print(f"[HASIL] Gagal        : {data['failed']} file")

# 3. Tampilkan detail setiap kandidat
for i, r in enumerate(data["results"]):
    p   = r.get("candidate_profile", {})
    m   = r.get("extraction_metadata", {})
    sk  = r.get("skills", {})
    edu = r.get("education", [])
    exp = r.get("work_experience", [])
    cer = r.get("certifications", [])

    print(f"\n{'='*55}")
    print(f"  KANDIDAT #{i+1}")
    print(f"{'='*55}")
    print(f"  Nama Lengkap   : {p.get('full_name') or '(tidak ditemukan)'}")
    print(f"  Email          : {p.get('email') or '(tidak ditemukan)'}")
    print(f"  Telepon        : {p.get('phone') or '(tidak ditemukan)'}")
    print(f"  Lokasi         : {p.get('location') or '(tidak ditemukan)'}")
    print(f"  LinkedIn       : {p.get('linkedin') or '-'}")
    print(f"  GitHub         : {p.get('github') or '-'}")
    print(f"  Portfolio      : {p.get('portfolio') or '-'}")
    if p.get("profile_summary"):
        summary = p["profile_summary"][:120] + ("..." if len(p["profile_summary"]) > 120 else "")
        print(f"  Ringkasan      : {summary}")

    print(f"\n  -- METADATA EKSTRAKSI --")
    print(f"  File Sumber    : {m.get('source_filename')}")
    print(f"  Metode         : {m.get('extraction_method')}")
    print(f"  Kepercayaan    : {m.get('confidence_notes')}")
    print(f"  Waktu Proses   : {m.get('processing_time_seconds')}s")
    if m.get("warnings"):
        for w in m["warnings"]:
            print(f"  [!] Peringatan   : {w}")

    print(f"\n  -- PENDIDIKAN ({len(edu)} entri) --")
    if edu:
        for e in edu:
            print(f"  * {e.get('institution') or '?'}")
            print(f"    Gelar   : {e.get('degree') or '-'} | Jurusan: {e.get('field_of_study') or '-'}")
            print(f"    Periode : {e.get('start_date') or '?'} → {e.get('end_date') or 'Sekarang'}")
            if e.get("gpa"):
                print(f"    IPK     : {e['gpa']}")
    else:
        print("  (tidak ditemukan)")

    print(f"\n  -- PENGALAMAN KERJA ({len(exp)} entri) --")
    if exp:
        for e in exp:
            status = "[Aktif]" if e.get("is_current") else ""
            end    = "Sekarang" if e.get("is_current") else (e.get("end_date") or "?")
            print(f"  * {e.get('job_title') or '?'} @ {e.get('company') or '?'} {status}")
            print(f"    Periode : {e.get('start_date') or '?'} - {end}")
            if e.get("responsibilities"):
                for resp_item in e["responsibilities"][:3]:
                    print(f"    - {resp_item[:80]}")
    else:
        print("  (tidak ditemukan)")

    print(f"\n  -- SKILLS --")
    hard = sk.get("hard_skills", [])
    tools = sk.get("tools", [])
    langs = sk.get("languages", [])
    print(f"  Hard Skills    : {', '.join(hard) if hard else '(tidak ditemukan)'}")
    print(f"  Tools/Software : {', '.join(tools) if tools else '-'}")
    if langs:
        for l in langs:
            print(f"  Bahasa         : {l.get('language')} - {l.get('proficiency')}")

    print(f"\n  -- SERTIFIKASI ({len(cer)} entri) --")
    if cer:
        for c in cer:
            print(f"  * {c.get('name')} ({c.get('issued_year') or '-'})")
    else:
        print("  (tidak ditemukan)")

# 4. Tampilkan error jika ada
if data.get("errors"):
    print(f"\n{'='*55}")
    print("  ERRORS")
    print(f"{'='*55}")
    for e in data["errors"]:
        print(f"  [X] {e['filename']}: {e['error']}")

print(f"\n{'='*60}")
print("  UJI COBA SELESAI")
print(f"{'='*60}\n")
