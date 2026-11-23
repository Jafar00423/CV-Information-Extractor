"""
CV Information Extractor - Backend API
=======================================
FastAPI backend for extracting structured information from CV/Resume files.
Supports PDF (text-based & scanned), DOCX, and image formats (JPG/PNG).

Author: CV Extractor App
"""

import os
import re
import json
import io
import time
import logging
from pathlib import Path
from typing import Optional, List, Tuple
from datetime import datetime

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
import uvicorn

# Document processing libraries
try:
    import pdfplumber
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

try:
    from docx import Document as DocxDocument
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False

try:
    from PIL import Image
    import pytesseract
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

try:
    import pymupdf as fitz  # PyMuPDF v2+ (new API, no FutureWarning)
    PYMUPDF_AVAILABLE = True
except ImportError:
    try:
        import fitz  # fallback untuk PyMuPDF versi lama
        PYMUPDF_AVAILABLE = True
    except ImportError:
        PYMUPDF_AVAILABLE = False

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App Initialization
# ---------------------------------------------------------------------------
app = FastAPI(
    title="CV Information Extractor API",
    description="Extracts structured candidate information from CV/Resume files",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve frontend static files
app.mount("/static", StaticFiles(directory="."), name="static")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MAX_FILE_SIZE_MB = 10
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".jpg", ".jpeg", ".png"}

# ---------------------------------------------------------------------------
# Regex patterns for entity extraction
# ---------------------------------------------------------------------------
EMAIL_PATTERN = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", re.IGNORECASE
)
PHONE_PATTERN = re.compile(
    r"(?:(?:\+|00)[1-9]\d{0,2}[\s\-.]?)?"
    r"(?:\(?\d{2,4}\)?[\s\-.]?)?"
    r"\d{3,4}[\s\-.]?\d{3,4}[\s\-.]?\d{0,4}",
    re.IGNORECASE,
)
LINKEDIN_PATTERN = re.compile(
    r"(?:https?://)?(?:www\.)?linkedin\.com/in/[\w\-]+/?", re.IGNORECASE
)
GITHUB_PATTERN = re.compile(
    r"(?:https?://)?(?:www\.)?github\.com/[\w\-]+/?", re.IGNORECASE
)
PORTFOLIO_PATTERN = re.compile(
    r"https?://(?!(?:www\.)?(?:linkedin|github)\.com)[\w\-\.]+\.[a-zA-Z]{2,}(?:/[\w\-\./?=%&]*)?",
    re.IGNORECASE,
)
DATE_PATTERN = re.compile(
    r"(?:"
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"[\s,]+\d{4}"
    r"|"
    r"\d{4}[-/]\d{2}"
    r"|"
    r"\d{2}[-/]\d{4}"
    r"|"
    r"\d{4}"
    r")",
    re.IGNORECASE,
)
GPA_PATTERN = re.compile(
    r"(?:GPA|IPK|Grade|CGPA)[:\s]*(\d+[.,]\d+)(?:\s*/\s*(\d+[.,]\d+))?",
    re.IGNORECASE,
)

# Common degree keywords
DEGREE_KEYWORDS = [
    "Bachelor", "Master", "PhD", "Doctor", "Associate", "Diploma",
    "B.Sc", "M.Sc", "B.Eng", "M.Eng", "B.A", "M.A", "MBA", "S1", "S2", "S3",
    "Sarjana", "Magister", "Doktor", "D3", "D4",
]

# Common section headers — urutan penting (lebih spesifik duluan)
SECTION_HEADERS = {
    "summary":        r"(?:tentang saya|ringkasan profil|ringkasan|profil singkat|summary|profile|objective|about me|about)",
    "education":      r"(?:pendidikan terakhir|latar belakang pendidikan|riwayat pendidikan|pendidikan|education|academic|schooling)",
    "experience":     r"(?:pengalaman magang & organisasi|riwayat kerja|pengalaman kerja|pengalaman magang|pengalaman & organisasi|pengalaman|work experience|experience|work history|employment|career|magang)",
    "skills":         r"(?:keahlian & bahasa|keahlian|kemampuan|keterampilan|skills|technical skills|competencies|expertise)",
    "certifications": r"(?:sertifikasi|sertifikat|certif|sertif|license|lisensi|credential|penghargaan)",
    "projects":       r"(?:proyek|project|portfolio|karya)",
}

# Common technical skills to match
TECH_SKILLS_KEYWORDS = [
    "Python", "JavaScript", "TypeScript", "Java", "C\\+\\+", "C#", "Go", "Rust", "PHP",
    "Ruby", "Swift", "Kotlin", "Dart", "Scala", "R", "MATLAB",
    "React", "Angular", "Vue", "Node\\.js", "Express", "Django", "Flask", "FastAPI",
    "Spring", "Laravel", "Rails", "Next\\.js", "Nuxt",
    "SQL", "MySQL", "PostgreSQL", "MongoDB", "Redis", "Elasticsearch", "SQLite",
    "Docker", "Kubernetes", "AWS", "Azure", "GCP", "Git", "Linux",
    "TensorFlow", "PyTorch", "Scikit-learn", "Pandas", "NumPy",
    "HTML", "CSS", "Tailwind", "Bootstrap", "SASS",
    "REST API", "GraphQL", "Microservices", "CI/CD", "DevOps",
    "Figma", "Adobe", "Photoshop", "Illustrator",
    "Excel", "PowerPoint", "Word", "Tableau", "Power BI",
]


# ---------------------------------------------------------------------------
# Helper: Normalize date string to YYYY-MM
# ---------------------------------------------------------------------------
MONTH_MAP = {
    "jan": "01", "feb": "02", "mar": "03", "apr": "04",
    "may": "05", "jun": "06", "jul": "07", "aug": "08",
    "sep": "09", "oct": "10", "nov": "11", "dec": "12",
}

def normalize_date(raw: str) -> Optional[str]:
    """Convert various date formats to YYYY-MM."""
    if not raw:
        return None
    raw = raw.strip()
    if re.match(r"^\d{4}$", raw):
        return f"{raw}-01"
    m = re.match(r"^(\d{4})[-/](\d{2})$", raw)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    m = re.match(r"^(\d{2})[-/](\d{4})$", raw)
    if m:
        return f"{m.group(2)}-{m.group(1)}"
    m = re.match(
        r"^(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
        r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
        r"[\s,]+(\d{4})$",
        raw, re.IGNORECASE,
    )
    if m:
        month_str = m.group(1)[:3].lower()
        year = m.group(2)
        month_num = MONTH_MAP.get(month_str, "01")
        return f"{year}-{month_num}"
    return None


def extract_date_range(text: str):
    """Extract start and end dates from a date-range string."""
    text = text.strip()
    is_current = bool(re.search(r"\b(present|current|now|sekarang)\b", text, re.IGNORECASE))

    dates = DATE_PATTERN.findall(text)
    start_date = normalize_date(dates[0]) if len(dates) > 0 else None
    end_date = None
    if not is_current and len(dates) > 1:
        end_date = normalize_date(dates[1])

    return start_date, end_date, is_current


# ---------------------------------------------------------------------------
# Text extraction functions
# ---------------------------------------------------------------------------

def extract_text_from_pdf(file_bytes: bytes) -> Tuple[str, str]:
    """
    Extract text from PDF. Returns (text, method).
    Tries pdfplumber first; falls back to OCR via PyMuPDF + pytesseract.
    """
    if not PDF_AVAILABLE:
        raise RuntimeError("pdfplumber not installed.")

    text = ""
    method = "text"

    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            pages_text = []
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                pages_text.append(page_text)
            text = "\n".join(pages_text).strip()
    except Exception as e:
        logger.warning(f"pdfplumber failed: {e}")
        text = ""

    # If extracted text is too short, attempt OCR
    if len(text) < 100:
        logger.info("Text extraction insufficient, attempting OCR...")
        if PYMUPDF_AVAILABLE and OCR_AVAILABLE:
            try:
                doc = fitz.open(stream=file_bytes, filetype="pdf")
                ocr_pages = []
                for page_num in range(len(doc)):
                    page = doc.load_page(page_num)
                    pix = page.get_pixmap(dpi=200)
                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                    ocr_text = pytesseract.image_to_string(img, lang="eng+ind")
                    ocr_pages.append(ocr_text)
                text = "\n".join(ocr_pages).strip()
                method = "ocr" if not text or len(text) < 50 else "hybrid"
            except Exception as e:
                logger.warning(f"OCR failed: {e}")
                method = "ocr"
        else:
            method = "ocr"
            logger.warning("OCR libraries not available for scanned PDF.")

    return text, method


def extract_text_from_docx(file_bytes: bytes) -> Tuple[str, str]:
    """Extract text from DOCX including table content."""
    if not DOCX_AVAILABLE:
        raise RuntimeError("python-docx not installed.")
    doc = DocxDocument(io.BytesIO(file_bytes))
    parts = []

    # Extract paragraphs
    for para in doc.paragraphs:
        if para.text.strip():
            parts.append(para.text.strip())

    # Extract table content
    for table in doc.tables:
        for row in table.rows:
            row_text = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
            if row_text:
                parts.append(row_text)

    return "\n".join(parts), "text"


def extract_text_from_image(file_bytes: bytes) -> Tuple[str, str]:
    """Extract text from image using OCR."""
    if not OCR_AVAILABLE:
        raise RuntimeError("Pillow/pytesseract not installed.")
    img = Image.open(io.BytesIO(file_bytes))
    text = pytesseract.image_to_string(img, lang="eng+ind")
    return text.strip(), "ocr"


def extract_raw_text(file_bytes: bytes, filename: str) -> Tuple[str, str]:
    """Route file to appropriate text extractor based on extension."""
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        return extract_text_from_pdf(file_bytes)
    elif ext == ".docx":
        return extract_text_from_docx(file_bytes)
    elif ext in {".jpg", ".jpeg", ".png"}:
        return extract_text_from_image(file_bytes)
    else:
        raise ValueError(f"Unsupported file type: {ext}")


# ---------------------------------------------------------------------------
# Section splitter
# ---------------------------------------------------------------------------

def _is_section_header(line: str) -> Optional[str]:
    """
    Cek apakah sebuah baris merupakan header section CV.
    Mengembalikan nama section atau None.
    Kriteria: baris pendek (< 60 karakter), tidak diakhiri titik/koma,
    cocok dengan salah satu pola section header.
    """
    stripped = line.strip()
    if not stripped or len(stripped) > 70:
        return None
    # Tidak mungkin header kalau diakhiri kalimat (titik/koma/titik koma)
    if stripped.endswith(('.', ',', ';', ')')):
        return None
    for section_name, pattern in SECTION_HEADERS.items():
        if re.match(rf"^\s*{pattern}\s*[:\-—]?\s*$", stripped, re.IGNORECASE):
            return section_name
    return None


def split_sections(text: str) -> dict:
    """
    Memisahkan teks CV ke dalam section berdasarkan header keyword.
    Mengembalikan dict: nama_section -> teks konten.
    """
    lines = text.splitlines()
    sections = {k: [] for k in SECTION_HEADERS}
    sections["header"] = []
    current_section = "header"

    for line in lines:
        detected = _is_section_header(line)
        if detected:
            current_section = detected
        else:
            sections[current_section].append(line)

    return {k: "\n".join(v) for k, v in sections.items()}


# ---------------------------------------------------------------------------
# Entity extractor functions
# ---------------------------------------------------------------------------

def extract_candidate_profile(sections: dict, full_text: str) -> dict:
    """
    Ekstrak informasi kontak dan profil kandidat.
    Mendukung format CV Indonesia dan Inggris.
    """
    # Gunakan header + 1000 karakter pertama sebagai area pencarian kontak
    header_text = sections.get("header", "") + "\n" + full_text[:1000]
    summary_text = sections.get("summary", "")

    # ── Nama: baris pertama yang terlihat seperti nama orang ──
    name = None
    for line in full_text.splitlines()[:25]:
        line = line.strip()
        if not line or len(line) < 3 or len(line) > 70:
            continue
        if EMAIL_PATTERN.search(line):
            continue
        if re.search(r"https?://|linkedin|github|@", line, re.IGNORECASE):
            continue
        if re.match(r"(?:curriculum vitae|resume|cv|halaman|page|sampel|profil)\b", line, re.IGNORECASE):
            continue
        if re.search(r"\d{4}", line):  # jangan ambil baris yang ada tahun
            continue
        # Cocok: huruf, spasi, tanda baca nama (termasuk huruf Indonesia)
        if re.match(r"^[A-Za-zÀ-ÖØ-öø-ÿ\s\.\-']{3,65}$", line):
            # Minimal 2 kata ATAU nama semua kapital
            words = line.strip().split()
            if len(words) >= 2 or line.isupper():
                name = line.strip()
                break

    # ── Email ──
    emails = EMAIL_PATTERN.findall(header_text)

    # ── Telepon: nomor dengan minimal 7 digit, termasuk format Indonesia ──
    raw_phones = PHONE_PATTERN.findall(header_text)
    phones = [
        p.strip() for p in raw_phones
        if len(re.sub(r"\D", "", p)) >= 7
        # Exclude: angka uang (ada titik/koma setiap 3 digit seperti 28.000.000)
        and not re.match(r"^\d{1,3}(?:[.,]\d{3})+$", p.strip())
        # Pastikan dimulai dengan 0, +62, atau +[kode negara lain]
        and re.search(r"(?:^0|\+\d{1,3})", p.strip())
    ]

    # ── LinkedIn / GitHub ──
    linkedin = next(iter(LINKEDIN_PATTERN.findall(full_text)), None)
    github   = next(iter(GITHUB_PATTERN.findall(full_text)), None)

    # ── Portfolio: URL selain LinkedIn & GitHub ──
    portfolio = None
    for url in PORTFOLIO_PATTERN.findall(full_text):
        low = url.lower()
        if "linkedin.com" not in low and "github.com" not in low:
            portfolio = url
            break

    # ── Lokasi ──
    # Prioritas 1: pola "Kota, Provinsi" atau "Kota, Indonesia" di dalam 1 baris
    location = None
    # Cari kota Indonesia yang diikuti koma + provinsi atau "Indonesia"
    city_match = re.search(
        r"\b((?:Jakarta|Surabaya|Bandung|Yogyakarta|Malang|Medan|Makassar|Semarang|"
        r"Denpasar|Palembang|Balikpapan|Samarinda|Pontianak|Manado|Ambon|Sorong|"
        r"Bogor|Depok|Tangerang|Bekasi|Batam)[A-Za-z\s]*)"
        r",\s*(Indonesia|Jawa\s+\w+|Jawa\s+Timur|Jawa\s+Barat|Jawa\s+Tengah|"
        r"Banten|Bali|DKI\s+Jakarta|DIY|[A-Z][a-z]{3,20})\b",
        header_text
    )
    if city_match:
        location = city_match.group(0).strip()
    else:
        # Prioritas 2: label eksplisit
        loc_label = re.search(
            r"(?:Lokasi|Location|Kota|City|Domisili|Alamat|Address)[:\s]+([^\n|]{3,60})",
            header_text, re.IGNORECASE
        )
        if loc_label:
            loc_val = loc_label.group(1).strip().rstrip(",. ")
            # Ambil hanya sampai tanda pemisah atau newline
            loc_val = re.split(r"\||\n", loc_val)[0].strip()
            if len(loc_val) < 60:
                location = loc_val
        else:
            # Prioritas 3: pola umum "Kota, Negara/Provinsi" di baris header
            generic_match = re.search(
                r"\b([A-Z][a-zA-Z\s]{2,20}),\s*(Indonesia|[A-Z][a-z]{3,20})\b",
                header_text
            )
            if generic_match:
                location = generic_match.group(0).strip()

    return {
        "full_name": name,
        "email": emails[0] if emails else None,
        "phone": phones[0] if phones else None,
        "location": location,
        "linkedin": linkedin,
        "github": github,
        "portfolio": portfolio,
        "profile_summary": summary_text.strip() if summary_text.strip() else None,
    }


# Pola untuk baris yang merupakan entri pendidikan (mengandung nama institusi/gelar/tahun)
EDU_ENTRY_PATTERN = re.compile(
    r"(?:universitas|university|institut|institute|sekolah|school|akademi|academy|"
    r"politeknik|polytechnic|s[123]\s|d[34]\s|bachelor|master|sarjana|magister|diploma)",
    re.IGNORECASE
)

def extract_education(sections: dict) -> list:
    """
    Ekstrak riwayat pendidikan dari section pendidikan.
    Hanya memproses baris yang benar-benar berisi data pendidikan.
    """
    edu_text = sections.get("education", "")
    if not edu_text.strip():
        return []

    entries = []
    # Pisahkan per blok: 2+ baris kosong, atau baris baru yang diawali nama institusi/gelar
    blocks = re.split(r"\n{2,}", edu_text)

    for block in blocks:
        block = block.strip()
        if not block or len(block) < 8:
            continue

        lines = [l.strip() for l in block.splitlines() if l.strip()]
        if not lines:
            continue

        # Filter: blok ini harus mengandung kata kunci pendidikan atau gelar atau tahun + IPK
        block_has_edu = (
            EDU_ENTRY_PATTERN.search(block) or
            GPA_PATTERN.search(block) or
            any(re.search(rf"\b{re.escape(d)}\b", block, re.IGNORECASE) for d in DEGREE_KEYWORDS)
        )
        if not block_has_edu:
            continue  # Lewati blok yang tidak terlihat seperti pendidikan

        # ── GPA / IPK ──
        gpa = None
        gpa_match = GPA_PATTERN.search(block)
        if gpa_match:
            try:
                gpa = float(gpa_match.group(1).replace(",", "."))
            except ValueError:
                pass

        # ── Gelar ──
        degree = None
        for deg in DEGREE_KEYWORDS:
            if re.search(rf"\b{re.escape(deg)}\b", block, re.IGNORECASE):
                degree = deg
                break

        # ── Rentang tanggal ──
        # Cari baris yang mengandung tahun/tanggal
        date_line = ""
        for ln in lines:
            if re.search(r"\b(19|20)\d{2}\b", ln):
                date_line = ln
                break
        dates = DATE_PATTERN.findall(date_line or block)
        start_date = normalize_date(dates[0]) if dates else None
        end_date   = normalize_date(dates[1]) if len(dates) > 1 else None

        # ── Nama institusi: baris pertama yang mengandung kata kunci institusi ──
        institution = None
        for ln in lines:
            if EDU_ENTRY_PATTERN.search(ln) or re.search(
                r"(?:Universitas|University|Institut|Sekolah|Politeknik|Akademi)", ln, re.IGNORECASE
            ):
                # Bersihkan — dan gelar dari nama institusi
                institution = re.sub(r"\s*[—\-–]\s*.*$", "", ln).strip()
                break
        if not institution:
            institution = lines[0]

        # ── Jurusan / Program studi ──
        field = None
        field_match = re.search(
            r"(?:Jurusan|Major|Field|Program Studi|Program|Department|Prodi|Bidang)[:\s]+([^\n,|]{3,60})",
            block, re.IGNORECASE
        )
        if field_match:
            field = field_match.group(1).strip()
        else:
            # Coba ekstrak dari pola "Gelar Jurusan — Institusi" atau "Institusi | Jurusan"
            field_in_name = re.search(
                r"(?:S[123]|D[34]|Bachelor|Master|Sarjana|Magister)\s+([A-Za-z][A-Za-z\s]{3,40})",
                block, re.IGNORECASE
            )
            if field_in_name:
                field = field_in_name.group(1).strip()

        entries.append({
            "institution": institution,
            "degree": degree,
            "field_of_study": field,
            "start_date": start_date,
            "end_date": end_date,
            "gpa": gpa,
        })

    return entries


# Pola baris yang merupakan header jabatan/perusahaan (ada tahun atau tanda pemisah)
EXP_COMPANY_PATTERN = re.compile(
    r"(?:PT\s|CV\s|Ltd|Inc|Corp|Co\.|Tbk|Group|Indonesia|Solutions|Consulting|"
    r"University|Institute|School|Yayasan|Kementerian|Dinas|Badan)",
    re.IGNORECASE
)

def extract_work_experience(sections: dict) -> list:
    """
    Ekstrak pengalaman kerja dari section experience.
    Mendukung format Indonesia: 'Jabatan — Perusahaan (Kota)\nBulan Tahun – Bulan Tahun'.
    """
    exp_text = sections.get("experience", "")
    if not exp_text.strip():
        return []

    entries = []
    # Pisahkan blok antar pengalaman: 2+ baris kosong
    blocks = re.split(r"\n{2,}", exp_text)

    for block in blocks:
        block = block.strip()
        if not block or len(block) < 10:
            continue

        lines = [l.strip() for l in block.splitlines() if l.strip()]
        if not lines:
            continue

        # Harus ada setidaknya tahun di blok ini agar valid sebagai pengalaman
        if not re.search(r"\b(19|20)\d{2}\b", block):
            continue

        # ── Cari baris tanggal ──
        date_line = ""
        for ln in lines:
            if re.search(r"\b(19|20)\d{2}\b", ln) or re.search(
                r"\b(present|current|sekarang|kini|sampai sekarang)\b", ln, re.IGNORECASE
            ):
                date_line = ln
                break

        start_date, end_date, is_current = extract_date_range(date_line)

        # ── Pisahkan jabatan dan perusahaan ──
        # Format umum: "Jabatan — Perusahaan (Kota)" atau "Jabatan\nPerusahaan"
        job_title = None
        company   = None
        location_exp = None

        first_line = lines[0]

        # Coba pisah dengan pemisah: —, –, |, @
        sep_match = re.match(
            r"^(.+?)\s*[—–|@]\s*(.+?)(?:\s*[\(\[])?(.*?)(?:[\)\]].*)?$",
            first_line
        )
        if sep_match:
            job_title = sep_match.group(1).strip()
            rest      = sep_match.group(2).strip()
            # Bersihkan kota dari nama perusahaan jika ada tanda kurung
            loc_in_name = re.search(r"\(([^)]+)\)", rest)
            if loc_in_name:
                location_exp = loc_in_name.group(1).strip()
                company = re.sub(r"\s*\([^)]*\)", "", rest).strip()
            else:
                company = rest
        else:
            job_title = first_line
            # Cari perusahaan di baris berikutnya
            for ln in lines[1:3]:
                if EXP_COMPANY_PATTERN.search(ln) or re.search(
                    r"\b(?:PT|CV|Ltd|Inc|Corp|Tbk)\b", ln, re.IGNORECASE
                ):
                    company = re.sub(r"\s*\([^)]*\)", "", ln).strip()
                    break
            if not company and len(lines) > 1 and not re.search(r"\b(19|20)\d{2}\b", lines[1]):
                company = lines[1]

        # ── Tanggung jawab: baris bullet atau kalimat panjang ──
        responsibilities = []
        for ln in lines[1:]:
            # Lewati baris tanggal dan nama perusahaan
            if ln == company or re.match(r"^\s*\(?\d{4}\)?", ln):
                continue
            if re.search(r"\b(19|20)\d{2}\b", ln) and len(ln) < 40:
                continue
            # Ambil baris bullet atau kalimat bermakna (>15 karakter)
            cleaned = re.sub(r"^[\•\-\*\·▪►→✓✔\d\.]\s*", "", ln).strip()
            if cleaned and len(cleaned) > 15:
                responsibilities.append(cleaned)

        entries.append({
            "company":          company,
            "job_title":        job_title,
            "location":         location_exp,
            "start_date":       start_date,
            "end_date":         end_date,
            "is_current":       is_current,
            "responsibilities": responsibilities[:10],
        })

    return entries


def extract_skills(sections: dict, full_text: str) -> dict:
    """
    Ekstrak dan normalisasi skills dari section skills dan teks penuh.
    Mendukung skills yang disebutkan dalam bahasa Indonesia.
    """
    skills_section = sections.get("skills", "")
    # Prioritas: section skills dulu, lalu teks penuh untuk konfirmasi
    search_text = skills_section + "\n" + full_text

    # ── Hard / Technical Skills ──
    found_hard = set()
    for skill in TECH_SKILLS_KEYWORDS:
        if re.search(rf"\b{skill}\b", search_text, re.IGNORECASE):
            found_hard.add(skill.replace("\\+\\+", "++").replace("\\.", "."))

    # ── Ekstrak skills yang disebutkan langsung di baris "Hard Skills:" atau "Keahlian:" ──
    inline_skills_match = re.search(
        r"(?:Hard Skills?|Technical Skills?|Keahlian Teknis?|Kemampuan Teknis?)[:\s]+([^\n]{5,200})",
        skills_section, re.IGNORECASE
    )
    if inline_skills_match:
        raw_skills = inline_skills_match.group(1)
        # Pisahkan dengan koma, titik koma, atau garis miring
        for sk in re.split(r"[,;/]", raw_skills):
            sk = sk.strip().strip("()[]")
            if 2 < len(sk) < 50 and not re.search(r"\d{4}", sk):
                found_hard.add(sk)

    # ── Tools & Software ──
    tools_keywords = [
        "Docker", "Kubernetes", "Git", "GitHub", "GitLab", "Jenkins", "Jira", "Confluence",
        "VS Code", "IntelliJ", "Eclipse", "Postman", "Figma", "Tableau", "Power BI",
        "Slack", "Trello", "Notion", "Microsoft Excel", "Excel", "SAP", "Accurate",
        "Google Sheets", "Sheets", "PowerPoint", "Word", "Microsoft Office",
    ]
    found_tools = set()
    for tool in tools_keywords:
        if re.search(rf"\b{re.escape(tool)}\b", search_text, re.IGNORECASE):
            found_tools.add(tool)

    # Ekstrak tools dari baris "Tools:" atau "Software:"
    inline_tools_match = re.search(
        r"(?:Tools?|Software|Aplikasi|Perangkat Lunak)[:\s]+([^\n]{5,200})",
        skills_section, re.IGNORECASE
    )
    if inline_tools_match:
        raw_tools = inline_tools_match.group(1)
        for t in re.split(r"[,;]", raw_tools):
            t_clean = t.strip().strip("()[]")
            # Bersihkan keterangan dalam kurung
            t_clean = re.sub(r"\s*\([^)]*\)", "", t_clean).strip()
            if 1 < len(t_clean) < 50:
                found_tools.add(t_clean)

    # ── Bahasa (languages) ──
    lang_proficiency = []
    lang_text = skills_section + "\n" + sections.get("header", "")

    # Format: "Bahasa Indonesia (Native)" atau "English – Advanced"
    lang_patterns = [
        # "Bahasa Indonesia (Native)" atau "English (Proficient)"
        r"(Bahasa\s+\w+|English|Indonesian|Mandarin|French|German|Japanese|Arabic|Spanish|Jepang|Jerman)"
        r"\s*[\(\[]\s*([^)\]]{3,30})\s*[\)\]]",
        # "English – Intermediate" atau "English: Advanced"
        r"(Bahasa\s+\w+|English|Indonesian|Mandarin|French|German|Japanese|Arabic|Spanish)"
        r"\s*[-–:]\s*([A-Za-z][A-Za-z\s]{2,25})",
    ]
    seen_langs = set()
    for pat in lang_patterns:
        for lang, level in re.findall(pat, lang_text, re.IGNORECASE):
            lang_key = lang.lower().split()[-1]  # normalisasi key
            if lang_key not in seen_langs:
                seen_langs.add(lang_key)
                # Normalisasi nama bahasa
                display_lang = lang.strip()
                if re.match(r"bahasa", display_lang, re.IGNORECASE):
                    display_lang = display_lang  # tetap "Bahasa Indonesia"
                lang_proficiency.append({
                    "language":    display_lang,
                    "proficiency": level.strip().rstrip(", "),
                })

    # Hapus overlap antara tools dan hard_skills
    hard_skills_final = sorted(found_hard - found_tools)
    tools_final       = sorted(found_tools)

    return {
        "hard_skills": hard_skills_final,
        "tools":       tools_final,
        "languages":   lang_proficiency,
    }


def extract_certifications(sections: dict) -> list:
    """
    Ekstrak daftar sertifikasi dari section sertifikasi.
    Hanya mengambil baris yang terlihat seperti nama sertifikat (bukan info kandidat lain).
    """
    cert_text = sections.get("certifications", "")
    if not cert_text.strip():
        return []

    certs = []
    for line in cert_text.splitlines():
        line = line.strip()
        if not line or len(line) < 5:
            continue
        # Lewati baris yang terlihat seperti header kandidat baru
        if re.match(r"^(sampel|lembar|halaman|page\s*\d)", line, re.IGNORECASE):
            break
        # Lewati baris berupa email/telepon/nama kota — bukan sertifikasi
        if EMAIL_PATTERN.search(line) or re.search(r"\bHP\b|\bTelepon\b|\bEmail\b", line, re.IGNORECASE):
            break
        line = re.sub(r"^[\•\-\*\·▪►→✓✔\d\.]\s*", "", line)
        if line:
            year_match = re.search(r"\b(20\d{2}|19\d{2})\b", line)
            # Bersihkan tahun dari nama jika formatnya "Nama (2022)"
            name_clean = re.sub(r"\s*[\(,]\s*(20|19)\d{2}.*$", "", line).strip()
            # Juga bersihkan "— Issuer" menjadi nama sertifikat saja
            issuer = None
            issuer_match = re.match(r"^(.+?)\s*[—–]\s*(.+)$", name_clean)
            if issuer_match:
                name_clean = issuer_match.group(1).strip()
                issuer_raw = issuer_match.group(2).strip()
                # Hapus tahun dari issuer
                issuer = re.sub(r"\s*\(?(20|19)\d{2}\)?.*$", "", issuer_raw).strip()
            if name_clean and len(name_clean) > 3:
                certs.append({
                    "name":        name_clean,
                    "issued_year": year_match.group(1) if year_match else None,
                    "issuer":      issuer,
                })

    return certs


# ---------------------------------------------------------------------------
# Multi-profile splitter
# ---------------------------------------------------------------------------

# Kata-kata yang BUKAN nama orang meskipun all-caps — harus diabaikan sebagai boundary
_NOT_A_NAME = re.compile(
    r"^(?:PENGALAMAN|PENDIDIKAN|KEAHLIAN|KEMAMPUAN|KETERAMPILAN|SERTIFIKASI|SERTIFIKAT|"
    r"RINGKASAN|PROFIL|TENTANG|RIWAYAT|SKILLS?|EDUCATION|EXPERIENCE|CERTIFICATION|"
    r"SUMMARY|ABOUT|PROFILE|WORK|MAGANG|ORGANISASI|CURRICULUM|VITAE|RESUME|"
    r"HARD SKILLS?|TOOLS?|SOFTWARE|BAHASA|LANGUAGES?)\b",
    re.IGNORECASE
)

def split_into_profiles(text: str) -> List[str]:
    """
    Memisahkan teks PDF yang berisi beberapa profil CV menjadi list teks per profil.

    Strategi deteksi boundary profil baru:
    1. Baris nama ALL CAPS (2–4 kata) diikuti kontak (email/HP/kota) → boundary.
    2. Baris nama mixed-case diikuti email atau nomor HP → boundary.
    3. Kata section header (PENGALAMAN, PENDIDIKAN, dll.) dikecualikan.
    """
    lines = text.splitlines()
    profile_starts = [0]

    def _has_contact_nearby(start_i: int, window: int = 4) -> bool:
        """
        Cek apakah dalam window baris setelah start_i ada info kontak
        (email / nomor HP / nama kota Indonesia).
        Window diperluas ke 4 baris karena beberapa CV punya baris jabatan
        di antara nama dan kontak.
        """
        ctx = " ".join(lines[start_i+1 : start_i+1+window]) if start_i + 1 < len(lines) else ""
        return bool(
            EMAIL_PATTERN.search(ctx) or
            re.search(r"(?:HP|No[\.\s]*HP|Telepon|Phone|\+62|08\d{8,10})", ctx)
        )

    def _has_city_nearby(start_i: int, window: int = 3) -> bool:
        """Cek kota saja (lebih lemah, hanya untuk nama ALL CAPS)."""
        ctx = " ".join(lines[start_i+1 : start_i+1+window]) if start_i + 1 < len(lines) else ""
        return bool(re.search(
            r"(?:Surabaya|Jakarta|Bandung|Yogyakarta|Malang|Medan|Makassar|Semarang|"
            r"Denpasar|Palembang|Balikpapan|Samarinda|Pontianak|Manado|Ambon|Sorong)",
            ctx
        ))

    for i, line in enumerate(lines):
        line_s = line.strip()
        if not line_s or len(line_s) < 3:
            continue

        # ── Cek nama ALL CAPS: harus ada kontak ATAU kota dalam 4 baris ──
        if (
            re.match(r"^[A-Z][A-Z\s\.\-]{3,60}$", line_s)
            and len(line_s.split()) >= 2
            and not _NOT_A_NAME.match(line_s)
            and not re.search(r"\d", line_s)
        ):
            # Syarat lebih ketat: kontak WAJIB ada (email/HP), atau kota+kontak dalam 5 baris
            contact_ok = _has_contact_nearby(i, window=5)
            city_ok    = _has_city_nearby(i, window=3)
            if (contact_ok or city_ok) and i > profile_starts[-1] + 3:
                profile_starts.append(i)
                continue

        # ── Cek nama mixed-case diikuti kontak LANGSUNG (email/HP wajib ada) ──
        if re.match(r"^[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){1,3}$", line_s):
            # Syarat ketat: hanya email atau HP (bukan hanya kota)
            if _has_contact_nearby(i, window=4) and i not in profile_starts and i > profile_starts[-1] + 5:
                profile_starts.append(i)

    profile_starts = sorted(set(profile_starts))

    if len(profile_starts) <= 1:
        return [text]

    # Potong teks menjadi per-profil
    profiles = []
    for idx, start in enumerate(profile_starts):
        end   = profile_starts[idx + 1] if idx + 1 < len(profile_starts) else len(lines)
        chunk = "\n".join(lines[start:end]).strip()
        if chunk and len(chunk) > 50:
            profiles.append(chunk)

    logger.info(f"split_into_profiles: {len(profiles)} profil ditemukan dari {len(lines)} baris teks.")
    return profiles if profiles else [text]


# ---------------------------------------------------------------------------
# Single-profile extraction orchestrator
# ---------------------------------------------------------------------------

def _extract_single_profile(profile_text: str, filename: str,
                             extraction_method: str, start_time: float) -> dict:
    """
    Proses satu blok teks profil CV → dict terstruktur JSON.
    """
    warnings_list: List[str] = []

    sections = split_sections(profile_text)

    candidate_profile = extract_candidate_profile(sections, profile_text)
    education         = extract_education(sections)
    work_experience   = extract_work_experience(sections)
    skills            = extract_skills(sections, profile_text)
    certifications    = extract_certifications(sections)

    # Peringatan kepercayaan
    if not candidate_profile.get("full_name"):
        warnings_list.append("Nama kandidat tidak dapat diidentifikasi dengan pasti.")
    if not candidate_profile.get("email"):
        warnings_list.append("Tidak ada alamat email yang ditemukan.")
    if not education:
        warnings_list.append("Section pendidikan tidak terdeteksi.")
    if not work_experience:
        warnings_list.append("Section pengalaman kerja tidak terdeteksi.")

    elapsed = round(time.time() - start_time, 3)

    return {
        "candidate_profile": candidate_profile,
        "education":         education,
        "work_experience":   work_experience,
        "skills":            skills,
        "certifications":    certifications,
        "extraction_metadata": {
            "source_filename":        filename,
            "extraction_method":      extraction_method,
            "processing_time_seconds": elapsed,
            "extracted_at":           datetime.utcnow().isoformat() + "Z",
            "warnings":               warnings_list,
            "confidence_notes":       "High" if not warnings_list
                                      else ("Medium" if len(warnings_list) <= 2 else "Low"),
        },
    }


# ---------------------------------------------------------------------------
# Main extraction orchestrator (mendukung multi-profil dalam 1 file)
# ---------------------------------------------------------------------------

def extract_cv_data(file_bytes: bytes, filename: str) -> List[dict]:
    """
    Pipeline lengkap: raw text → deteksi multi-profil → section split → ekstraksi terstruktur.
    Mengembalikan LIST hasil (1 file bisa menghasilkan beberapa profil kandidat).
    """
    start_time = time.time()

    # 1. Ekstrak teks mentah
    try:
        raw_text, extraction_method = extract_raw_text(file_bytes, filename)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Ekstraksi teks gagal: {str(e)}")

    if not raw_text or len(raw_text.strip()) < 20:
        raise HTTPException(status_code=422, detail="Terlalu sedikit teks yang bisa diekstrak. File mungkin kosong atau berbasis gambar penuh.")

    # 2. Pisahkan multi-profil dalam 1 file
    profiles = split_into_profiles(raw_text)
    logger.info(f"{filename}: {len(profiles)} profil terdeteksi.")

    # 3. Proses setiap profil
    results = []
    for i, profile_text in enumerate(profiles):
        try:
            result = _extract_single_profile(profile_text, filename, extraction_method, start_time)
            # Tambahkan nomor profil jika ada lebih dari 1
            if len(profiles) > 1:
                result["extraction_metadata"]["profile_index"] = i + 1
                result["extraction_metadata"]["total_profiles_in_file"] = len(profiles)
            results.append(result)
        except Exception as e:
            logger.error(f"Gagal memproses profil {i+1} dari {filename}: {e}")

    return results


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@app.get("/")
async def serve_index():
    """Serve the frontend index page."""
    return FileResponse("index.html")


@app.post("/api/extract", summary="Extract information from one or more CV files")
async def extract_cv(files: List[UploadFile] = File(...)):
    """
    Upload one or more CV files and receive structured extraction results.

    Supported formats: PDF, DOCX, JPG, PNG
    Max file size: 10MB per file
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded.")

    results = []
    errors = []

    for upload in files:
        filename = upload.filename or "unknown"
        ext = Path(filename).suffix.lower()

        # Validate extension
        if ext not in ALLOWED_EXTENSIONS:
            errors.append({
                "filename": filename,
                "error": f"Unsupported file type '{ext}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
            })
            continue

        # Read and validate size
        file_bytes = await upload.read()
        size_mb = len(file_bytes) / (1024 * 1024)
        if size_mb > MAX_FILE_SIZE_MB:
            errors.append({
                "filename": filename,
                "error": f"File too large ({size_mb:.1f} MB). Maximum allowed: {MAX_FILE_SIZE_MB} MB.",
            })
            continue

        try:
            # extract_cv_data mengembalikan LIST (mendukung multi-profil dalam 1 file)
            profile_results = extract_cv_data(file_bytes, filename)
            results.extend(profile_results)
            logger.info(f"Berhasil diproses: {filename} → {len(profile_results)} profil")
        except HTTPException as he:
            errors.append({"filename": filename, "error": he.detail})
        except Exception as e:
            logger.error(f"Error tak terduga saat memproses {filename}: {e}")
            errors.append({"filename": filename, "error": f"Error tak terduga: {str(e)}"})

    return {
        "success": len(results),
        "failed":  len(errors),
        "results": results,
        "errors":  errors,
    }


@app.get("/api/health", summary="Health check")
async def health_check():
    """Check API health and available processing capabilities."""
    return {
        "status": "ok",
        "capabilities": {
            "pdf_text": PDF_AVAILABLE,
            "docx": DOCX_AVAILABLE,
            "ocr": OCR_AVAILABLE,
            "pdf_ocr": PYMUPDF_AVAILABLE and OCR_AVAILABLE,
        },
        "max_file_size_mb": MAX_FILE_SIZE_MB,
        "supported_formats": list(ALLOWED_EXTENSIONS),
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
