"""
EMStash Form 1 & 42 Generator
Flask backend — run with: python app.py
Then open http://localhost:5000 in your browser.
"""
from flask import Flask, request, send_file, jsonify
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    NameObject, create_string_object, DictionaryObject,
    ArrayObject, FloatObject, StreamObject
)
import json, io, os
from reportlab.pdfbase.pdfmetrics import stringWidth

app = Flask(__name__)

@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["X-Frame-Options"] = "ALLOWALL"
    response.headers["Content-Security-Policy"] = "frame-ancestors *"
    return response

BASE = os.path.dirname(os.path.abspath(__file__))

# ── PDF helpers ──────────────────────────────────────────────────────────
# All appearance streams are built manually (rather than relying on a PDF
# viewer's "NeedAppearances" auto-regeneration) so that filled values are
# guaranteed to render in every viewer and survive being re-read/merged.

def _escape_pdf_text(s):
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

def make_text_appearance(writer, rect, text, size=10, color="0 0 1 rg", multiline=False):
    """Build a minimal valid /AP /N appearance stream for a text field value."""
    w = float(rect[2]) - float(rect[0])
    h = float(rect[3]) - float(rect[1])

    if multiline and text:
        # Wrap long text into multiple lines so it doesn't run off the edge
        # of wide boxes, but keep simple top-down placement — same plain
        # style as single-line fields, just repeated per line.
        max_width = w - 6
        words = text.split()
        lines, cur = [], ""
        for word in words:
            trial = (cur + " " + word).strip()
            if stringWidth(trial, "Helvetica", size) <= max_width:
                cur = trial
            else:
                if cur:
                    lines.append(cur)
                cur = word
        if cur:
            lines.append(cur)
        line_spacing = size * 1.3
        # Start near the very top of the box, comfortably above any
        # pre-printed handwriting rule-line, then flow downward.
        first_baseline = h - size + 1
        parts = [f"/Tx BMC q BT /F1 {size} Tf {color} 1 0 0 1 2 {first_baseline:.2f} Tm {line_spacing:.2f} TL"]
        for i, line in enumerate(lines):
            if i == 0:
                parts.append(f"({_escape_pdf_text(line)}) Tj")
            else:
                parts.append(f"T* ({_escape_pdf_text(line)}) Tj")
        parts.append("ET Q EMC")
        content = " ".join(parts)
    else:
        ty = max(2, (h - size) / 2 + 2)
        content = f"/Tx BMC q BT /F1 {size} Tf {color} 2 {ty:.2f} Td ({_escape_pdf_text(text)}) Tj ET Q EMC"

    stream = StreamObject()
    stream.set_data(content.encode("latin-1", errors="replace"))
    stream[NameObject("/Type")] = NameObject("/XObject")
    stream[NameObject("/Subtype")] = NameObject("/Form")
    stream[NameObject("/BBox")] = ArrayObject([FloatObject(0), FloatObject(0), FloatObject(w), FloatObject(h)])
    font_obj = DictionaryObject()
    font_obj[NameObject("/Type")] = NameObject("/Font")
    font_obj[NameObject("/Subtype")] = NameObject("/Type1")
    font_obj[NameObject("/BaseFont")] = NameObject("/Helvetica")
    font_ref = writer._add_object(font_obj)
    font_dict = DictionaryObject()
    font_dict[NameObject("/F1")] = font_ref
    resources = DictionaryObject()
    resources[NameObject("/Font")] = font_dict
    stream[NameObject("/Resources")] = resources
    return writer._add_object(stream)

def make_check_appearance(writer, rect, checked=True):
    """Build a minimal /AP /N appearance stream for a checkbox tick mark."""
    w = float(rect[2]) - float(rect[0])
    h = float(rect[3]) - float(rect[1])
    if checked:
        content = f"q 1 0 0 1 0 0 cm 0 0 1 RG 1.3 w {w*0.18:.2f} {h*0.45:.2f} m {w*0.4:.2f} {h*0.15:.2f} l {w*0.85:.2f} {h*0.85:.2f} l S Q"
    else:
        content = ""
    stream = StreamObject()
    stream.set_data(content.encode("latin-1", errors="replace"))
    stream[NameObject("/Type")] = NameObject("/XObject")
    stream[NameObject("/Subtype")] = NameObject("/Form")
    stream[NameObject("/BBox")] = ArrayObject([FloatObject(0), FloatObject(0), FloatObject(w), FloatObject(h)])
    return writer._add_object(stream)

def set_named_text(writer, page_idx, field_id, value, multiline=False):
    page = writer.pages[page_idx]
    if "/Annots" not in page:
        return
    for ref in page["/Annots"]:
        annot = ref.get_object()
        fid = annot.get("/T", "")
        if isinstance(fid, bytes):
            fid = fid.decode("utf-8", errors="ignore")
        if fid == field_id:
            rect = annot.get("/Rect", [0, 0, 100, 12])
            ap_ref = make_text_appearance(writer, rect, value, multiline=multiline)
            ap_dict = DictionaryObject()
            ap_dict[NameObject("/N")] = ap_ref
            annot[NameObject("/AP")] = ap_dict
            annot[NameObject("/V")] = create_string_object(value)

def set_named_checkbox(writer, page_idx, field_id, checked):
    page = writer.pages[page_idx]
    if "/Annots" not in page:
        return
    for ref in page["/Annots"]:
        annot = ref.get_object()
        fid = annot.get("/T", "")
        if isinstance(fid, bytes):
            fid = fid.decode("utf-8", errors="ignore")
        if fid == field_id:
            rect = annot.get("/Rect", [0, 0, 12, 12])
            state = "/Yes" if checked else "/Off"
            on_ref = make_check_appearance(writer, rect, checked=True)
            off_ref = make_check_appearance(writer, rect, checked=False)
            ap_dict = DictionaryObject()
            n_dict = DictionaryObject()
            n_dict[NameObject("/Yes")] = on_ref
            n_dict[NameObject("/Off")] = off_ref
            ap_dict[NameObject("/N")] = n_dict
            annot[NameObject("/AP")] = ap_dict
            annot[NameObject("/V")] = NameObject(state)
            annot[NameObject("/AS")] = NameObject(state)

def set_anon_text_by_rect(writer, x_min, x_max, y_min, y_max, page_idx, value, multiline=True):
    """Set a text value into an anonymous (un-named) text field located by its rect box."""
    page = writer.pages[page_idx]
    if "/Annots" not in page:
        return
    for ref in page["/Annots"]:
        annot = ref.get_object()
        fid = annot.get("/T", "")
        if isinstance(fid, bytes):
            fid = fid.decode("utf-8", errors="ignore")
        rect = annot.get("/Rect", [])
        if not fid and len(rect) == 4:
            x, y = float(rect[0]), float(rect[1])
            if x_min <= x <= x_max and y_min <= y <= y_max:
                ap_ref = make_text_appearance(writer, rect, value, multiline=multiline)
                ap_dict = DictionaryObject()
                ap_dict[NameObject("/N")] = ap_ref
                annot[NameObject("/AP")] = ap_dict
                annot[NameObject("/V")] = create_string_object(value)

def check_anon_by_y(writer, y_min, y_max, page_idx, check=True):
    """Check/uncheck an anonymous checkbox located by its Y rect position."""
    page = writer.pages[page_idx]
    if "/Annots" not in page:
        return
    for ref in page["/Annots"]:
        annot = ref.get_object()
        fid = annot.get("/T", "")
        if isinstance(fid, bytes):
            fid = fid.decode("utf-8", errors="ignore")
        rect = annot.get("/Rect", [])
        if not fid and len(rect) == 4:
            y = float(rect[1])
            if y_min <= y <= y_max:
                state = "/On" if check else "/Off"
                on_ref = make_check_appearance(writer, rect, checked=True)
                off_ref = make_check_appearance(writer, rect, checked=False)
                ap_dict = DictionaryObject()
                n_dict = DictionaryObject()
                n_dict[NameObject("/On")] = on_ref
                n_dict[NameObject("/Off")] = off_ref
                ap_dict[NameObject("/N")] = n_dict
                annot[NameObject("/AP")] = ap_dict
                annot[NameObject("/V")] = NameObject(state)
                annot[NameObject("/AS")] = NameObject(state)

# ── Form fillers ─────────────────────────────────────────────────────────

def fill_form1(data):
    reader = PdfReader(os.path.join(BASE, "form1_original.pdf"))
    writer = PdfWriter()
    writer.append(reader)

    phone_raw = data["hosp_phone"].replace("(", "").replace(")", "")
    parts = phone_raw.split(None, 1)
    area_code = parts[0] if parts else ""
    rest = parts[1] if len(parts) > 1 else ""

    set_named_text(writer, 0, "2", data["hosp_addr"])
    set_named_text(writer, 0, "3", area_code)
    set_named_text(writer, 0, "15", data["hpi"], multiline=True)
    set_named_text(writer, 0, "16", data["psychhx"], multiline=True)
    # Fields 37/38 are the "Date and time Form 42 delivered" line — left
    # blank for the clinician to complete when the form is actually
    # delivered to the patient, per Mental Health Act requirements.

    set_named_checkbox(writer, 0, "10", data["pp1"])
    set_named_checkbox(writer, 0, "12", data["pp3"])
    set_named_checkbox(writer, 0, "13", data["pp4"])
    set_named_checkbox(writer, 0, "14", data["pp5"])
    set_named_checkbox(writer, 0, "17", data["ft1"])
    set_named_checkbox(writer, 0, "18", data["ft2"])
    set_named_checkbox(writer, 0, "19", data["ft3"])

    # Anonymous fields (no /T name in the original PDF)
    set_anon_text_by_rect(writer, x_min=220, x_max=232, y_min=620, y_max=645, page_idx=0, value=rest, multiline=False)
    set_anon_text_by_rect(writer, x_min=100, x_max=260, y_min=590, y_max=610, page_idx=0, value=data["exam_date"], multiline=False)
    check_anon_by_y(writer, 370, 398, page_idx=0, check=data["pp2"])

    # Future Test's "I base this opinion" observation boxes continue onto page 2 (index 1)
    set_anon_text_by_rect(writer, x_min=15, x_max=515, y_min=605, y_max=680, page_idx=1, value=data["mse"])
    set_anon_text_by_rect(writer, x_min=15, x_max=515, y_min=535, y_max=605, page_idx=1, value=data["collateral"])

    # "Date and time detention commences" (page 3) — pre-filled with exam date/time
    # for the clinician to confirm or edit; "Form 42 delivered" has no fillable
    # field in the original PDF and is correctly left for handwriting.
    detention_str = f"{data['exam_date']}  {data['exam_time']}".strip()
    set_anon_text_by_rect(writer, x_min=85, x_max=250, y_min=108, y_max=132, page_idx=2, value=detention_str, multiline=False)

    buf = io.BytesIO()
    writer.write(buf)
    buf.seek(0)
    return buf

def fill_form42(data):
    reader = PdfReader(os.path.join(BASE, "form42_original.pdf"))
    writer = PdfWriter()
    writer.append(reader)

    set_named_text(writer, 0, "4", data["exam_date"])
    set_named_text(writer, 1, "27", data["exam_date"])

    set_named_checkbox(writer, 0, "9", data["ft1"])
    set_named_checkbox(writer, 0, "10", data["ft2"])
    set_named_checkbox(writer, 0, "11", data["ft3"])

    check_anon_by_y(writer, 435, 455, page_idx=0, check=(data["pp1"] or data["pp2"]))
    check_anon_by_y(writer, 410, 430, page_idx=0, check=(data["pp3"] or data["pp4"]))
    check_anon_by_y(writer, 380, 408, page_idx=0, check=data["pp5"])

    buf = io.BytesIO()
    writer.write(buf)
    buf.seek(0)
    return buf

def merge_to_bytes(bufs):
    writer = PdfWriter()
    for buf in bufs:
        reader = PdfReader(buf)
        for page in reader.pages:
            writer.add_page(page)
    out = io.BytesIO()
    writer.write(out)
    out.seek(0)
    return out

# ── Routes ───────────────────────────────────────────────────────────────

@app.route("/")
def index():
    with open(os.path.join(BASE, "static", "index.html")) as f:
        return f.read()

@app.route("/generate", methods=["POST"])
def generate():
    try:
        data = request.get_json()
        for k in ["pp1", "pp2", "pp3", "pp4", "pp5", "ft1", "ft2", "ft3"]:
            data[k] = bool(data.get(k, False))
        f1 = fill_form1(data)
        f42 = fill_form42(data)
        combined = merge_to_bytes([f1, f42])
        date_str = data.get("exam_date", "").replace("/", "-")
        filename = f"Form1_Form42_{date_str}.pdf"
        return send_file(combined, mimetype="application/pdf",
                         as_attachment=False, download_name=filename)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"\n✓ EMStash Form Generator running at http://localhost:{port}\n")
    app.run(debug=False, host="0.0.0.0", port=port)
