"""Generate the committed demo and eval fixtures (design spec §9).

    uv run python scripts/make_demo_pdfs.py

PDFs are drawn with reportlab `Canvas(..., invariant=1)`, one `drawString` per
line in reading order, so the bytes are deterministic and pypdf extracts the
lines exactly as written. `scanned_quote.pdf` is a page image (Pillow) with no
text layer, for the OCR / needs-manual path. The script also writes the demo
`.eml`, the SMS `.txt` and `manifest.json`, so all demo content lives here.
reportlab and Pillow are dev dependencies; tests only read the committed files.
"""

from __future__ import annotations

import io
import json
from collections.abc import Sequence
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "fixtures" / "demo"
CASES = ROOT / "fixtures" / "eval" / "cases"

Page = Sequence[str]

# --------------------------------------------------------------------------- demo content

ATLAS_PDF: tuple[Page, ...] = (
    (
        "Atlas Air Charter",
        "Charter Quotation · Trip JS184",
        "Route: KTEB – KOPF (Teterboro to Opa-locka)",
        "Aircraft: Cessna Citation Latitude (N684AC) · Category: Midsize",
        "Configuration: 8 seats · Wi-Fi: Yes",
        "18 Oct 2026 · Departure 09:00 local · Passengers: 7",
        "Estimated flight time: 2h 58m",
        "Availability: Confirmed",
        "Charter price …………………… $41,800.00",
        "Positioning (ferry KHPN–KTEB) …………… $1,200.00",
        "Continued on page 2",
    ),
    (
        "Atlas Air Charter · Trip JS184 · page 2",
        "Ramp / handling fee (KOPF) …………… $420.00",
        "Fuel surcharge …………………… $1,400.00",
        "Federal excise tax (7.5%) and segment fees included in charter price.",
        "Total …………………………… $44,820.00",
        "Quote valid until 10 Oct 2026. Payment by wire transfer prior to departure.",
    ),
)

SKYBRIDGE_PDF: tuple[Page, ...] = (
    (
        "SkyBridge Aviation",
        "Quote JS184 · KTEB-KOPF · 18 Oct 2026",
        "Bombardier Challenger 350 · N350SB · Super-midsize · 9 passenger seats · Wi-Fi: Ka-band",
        "dep 09:30 (earliest crew availability) · flight time 2:48 · Aircraft available",
        "Flight charge: USD 45,900 / Positioning: USD 850 / Ramp & handling: USD 450",
    ),
    (
        "SkyBridge Aviation · Quote JS184 · page 2",
        "Catering: included · FET 7.5% & segment fees: included · Total USD 47,200",
        "Thank you for choosing SkyBridge.",
    ),
)

NORTHSTAR_PDF: tuple[Page, ...] = (
    (
        "Northstar Jets",
        "Charter quotation · JS184 · KTEB-KOPF",
        "Gulfstream G280 · N280NJ · super mid-size · 9 seats · WiFi onboard",
        "18-Oct-2026 10:00 · ETE 2h45m · Subject to availability",
        "Aircraft charge $50,200 · Repositioning $1,400 · FBO handling $800",
        "Catering: Included · Price includes FET and segment fees",
        "Total $52,400",
    ),
)

SUMMIT_PDF: tuple[Page, ...] = (
    (
        "Summit Executive Aviation",
        "REVISED QUOTE · JS184 · KTEB-KOPF",
        "Embraer Legacy 650 · N650SX · Heavy · 13 seats · Wi-Fi: not installed",
        "18 Oct 2026 09:00 · flight time 3h 05m · Available",
        "Charter price: $38,900",
        "Positioning from KBED: $1,900",
    ),
    (
        "Summit Executive Aviation · Revised quote JS184 · page 2",
        "Ramp / handling (KTEB): $480",
    ),
)

SCANNED_LINES = (
    "Harbor Jet Group",
    "Charter quote JS184 KTEB-KOPF",
    "Aircraft: Hawker 900XP (N900HJ)",
    "Charter price: $39,000",
    "Total: $40,250",
)

ATLAS_EMAIL = """\
From: Atlas Air Charter <quotes@atlas-air-charter.example>
To: Priya Shah <priya@jetstream-demo.example>
Subject: RE: JS184 KTEB-KOPF 18 Oct
Date: Fri, 02 Oct 2026 14:12:00 -0400
Message-ID: <js184-catering@atlas-air-charter.example>
MIME-Version: 1.0
Content-Type: text/plain; charset="utf-8"
Content-Transfer-Encoding: 7bit

Hi Priya,

Confirming catering is included for all 7 pax on JS184 KTEB-KOPF 18 Oct, aircraft confirmed.

Best regards,
Mark Ellis
Charter Sales | Atlas Air Charter
"""

SUMMIT_SMS = """\
From: Summit Executive Aviation <+16175550142>
Received: 2026-10-02T16:40:00-04:00

Hi it's Dan at Summit re JS184 KTEB-KOPF 18 Oct. quote is 38,900 all in, crew overnight \
700 extra. fuel may be extra, est. 850 depending on uplift at KOPF. Thx
"""

MANIFEST = {
    "trip": {
        "reference": "JS184",
        "origin": "KTEB",
        "destination": "KOPF",
        "depart_local": "2026-10-18T09:00",
        "depart_tz": "America/New_York",
        "pax": 7,
    },
    "files": [
        {
            "file": "atlas_quote_01.pdf",
            "operator": "Atlas Air Charter",
            "channel": "pdf_upload",
            "sender": "Atlas Air Charter <quotes@atlas-air-charter.example>",
            "subject": "JS184 quote",
            "received_offset_minutes": 84,
        },
        {
            "file": "quote-final-v7.pdf",
            "operator": "SkyBridge Aviation",
            "channel": "pdf_upload",
            "sender": "SkyBridge Aviation <sales@skybridge-aviation.example>",
            "subject": "Quote JS184",
            "received_offset_minutes": 126,
        },
        {
            "file": "atlas_email_catering.eml",
            "operator": "Atlas Air Charter",
            "channel": "email",
            "sender": "Atlas Air Charter <quotes@atlas-air-charter.example>",
            "subject": "RE: JS184 KTEB-KOPF 18 Oct",
            "received_offset_minutes": 180,
        },
        {
            "file": "operator_quote_18.pdf",
            "operator": "Northstar Jets",
            "channel": "pdf_upload",
            "sender": "Northstar Jets <charter@northstarjets.example>",
            "subject": "Northstar quotation JS184",
            "received_offset_minutes": 216,
        },
        {
            "file": "revised-quote.pdf",
            "operator": "Summit Executive Aviation",
            "channel": "pdf_upload",
            "sender": "Summit Executive Aviation <dan@summit-exec.example>",
            "subject": "Revised quote JS184",
            "received_offset_minutes": 312,
        },
        {
            "file": "summit_sms.txt",
            "operator": "Summit Executive Aviation",
            "channel": "sms",
            "sender": "Summit Executive Aviation <+16175550142>",
            "subject": None,
            "received_offset_minutes": 340,
        },
    ],
    "rfq": [
        {"operator": "Atlas Air Charter", "status": "quoted"},
        {"operator": "SkyBridge Aviation", "status": "quoted"},
        {"operator": "Northstar Jets", "status": "quoted"},
        {"operator": "Summit Executive Aviation", "status": "quoted"},
        {"operator": "Harbor Jet Group", "status": "declined", "responded_offset_minutes": 240},
        {"operator": "Coastal Wings", "status": "declined", "responded_offset_minutes": 360},
        {"operator": "Meridian Air", "status": "requested"},
        {"operator": "Blue Ridge Charter", "status": "requested"},
    ],
}

# --------------------------------------------------------------------------- eval PDFs

EVAL_PDFS: dict[str, tuple[Page, ...]] = {
    "eur_eu_grouping": (
        (
            "Alpine Executive Jets",
            "Quotation LSGG-LFMN · 18 Oct 2026 09:00",
            "Aircraft: Cessna Citation XLS+ · Category: Midsize",
            "Charter price …………… €32.500,00",
            "Handling LFMN …………… €450,00",
            "Total …………………… EUR 32.950,00",
        ),
    ),
    "fet_percent": (
        (
            "Keystone Air Charter",
            "Aircraft: Hawker 800XP · Tail N801KC",
            "Charter price: $38,000.00",
            "Federal excise tax (7.5%): $2,850.00",
            "Segment fees (2 segments): $10.60",
            "Total: $40,860.60",
        ),
    ),
    "total_mismatch": (
        (
            "Pinnacle Air",
            "Aircraft: Phenom 300 (N300PA)",
            "Charter price …………… $24,500.00",
            "Positioning …………… $900.00",
            "Landing fees …………… $180.00",
            "Total …………………… $26,100.00",
        ),
    ),
    "tail_model_variants": (
        (
            "Crescent Aviation",
            "Equipment: CL-350, reg N35CR, 9 executive seats, no Wi-Fi",
            "Charter price: $44,000",
            "Positioning: $1,300",
        ),
    ),
}


def draw_pdf(path: Path, pages: Sequence[Page]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas = Canvas(str(path), pagesize=letter, invariant=1)
    canvas.setTitle(path.stem)
    for page in pages:
        y = 740.0
        for index, line in enumerate(page):
            canvas.setFont(
                "Helvetica-Bold" if index == 0 else "Helvetica", 13 if index == 0 else 10
            )
            canvas.drawString(60, y, line)
            y -= 22 if index == 0 else 17
        canvas.showPage()
    canvas.save()


def draw_scanned(path: Path, lines: Sequence[str]) -> None:
    """A page image with no text layer (what a phone scan looks like to pypdf)."""
    image = Image.new("L", (850, 1100), color=255)
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    y = 80
    for line in lines:
        draw.text((70, y), line, fill=0, font=font)
        y += 28
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=False)
    buffer.seek(0)
    canvas = Canvas(str(path), pagesize=letter, invariant=1)
    canvas.drawImage(ImageReader(buffer), 0, 0, width=letter[0], height=letter[1])
    canvas.showPage()
    canvas.save()


def main() -> None:
    DEMO.mkdir(parents=True, exist_ok=True)
    draw_pdf(DEMO / "atlas_quote_01.pdf", ATLAS_PDF)
    draw_pdf(DEMO / "quote-final-v7.pdf", SKYBRIDGE_PDF)
    draw_pdf(DEMO / "operator_quote_18.pdf", NORTHSTAR_PDF)
    draw_pdf(DEMO / "revised-quote.pdf", SUMMIT_PDF)
    draw_scanned(DEMO / "scanned_quote.pdf", SCANNED_LINES)
    (DEMO / "atlas_email_catering.eml").write_bytes(ATLAS_EMAIL.replace("\n", "\r\n").encode())
    (DEMO / "summit_sms.txt").write_text(SUMMIT_SMS, encoding="utf-8")
    (DEMO / "manifest.json").write_text(json.dumps(MANIFEST, indent=2) + "\n", encoding="utf-8")
    for case_id, pages in EVAL_PDFS.items():
        draw_pdf(CASES / case_id / "input.pdf", pages)
    print(f"wrote demo fixtures to {DEMO} and {len(EVAL_PDFS)} eval PDFs")


if __name__ == "__main__":
    main()
