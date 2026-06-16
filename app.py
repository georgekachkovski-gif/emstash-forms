"""
EMStash Form 1 & 42 Generator
Flask backend — run with: python app.py
Then open http://localhost:5000 in your browser.
"""
from flask import Flask, request, send_file, jsonify, render_template_string
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, create_string_object
import json, io, os

app = Flask(__name__)

# Allow embedding from Softr (and any origin)
@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["X-Frame-Options"] = "ALLOWALL"
    response.headers["Content-Security-Policy"] = "frame-ancestors *"
    return response
BASE = os.path.dirname(os.path.abspath(__file__))

# ── PDF helpers ────────────────────────────────────────────────────────────────

def set_fields(writer, field_map):
    for page in writer.pages:
        if "/Annots" not in page:
            continue
        for ref in page["/Annots"]:
            annot = ref.get_object()
            fid = annot.get("/T", "")
            if isinstance(fid, bytes):
                fid = fid.decode("utf-8", errors="ignore")
            if fid in field_map:
                val = field_map[fid]
                if val.startswith("/"):
                    annot.update({NameObject("/V"): NameObject(val), NameObject("/AS"): NameObject(val)})
                else:
                    annot.update({NameObject("/V"): create_string_object(val)})
                if "/AP" in annot:
                    del annot["/AP"]

def check_anon_by_y(writer, y_min, y_max, page_idx, check=True):
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
                val = NameObject("/On" if check else "/Off")
                annot.update({NameObject("/V"): val, NameObject("/AS"): val})

def set_anon_text_by_rect(writer, x_min, x_max, y_min, y_max, page_idx, value):
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
            x = float(rect[0])
            y = float(rect[1])
            if x_min <= x <= x_max and y_min <= y <= y_max:
                annot.update({NameObject("/V"): create_string_object(value)})
                if "/AP" in annot:
                    del annot["/AP"]

def fill_form1(data):
    reader = PdfReader(os.path.join(BASE, "form1_original.pdf"))
    writer = PdfWriter()
    writer.append(reader)
    writer.set_need_appearances_writer(True)

    # Split phone like "(416) 360-4000" into area code "416" and rest "360-4000"
    phone_raw = data["hosp_phone"].replace("(", "").replace(")", "")
    parts = phone_raw.split(None, 1)  # split on first whitespace
    area_code = parts[0] if parts else ""
    rest = parts[1] if len(parts) > 1 else ""

    set_fields(writer, {
        "2":  data["hosp_addr"],
        "3":  area_code,
        "10": "/Yes" if data["pp1"] else "/Off",
        "12": "/On3" if data["pp3"] else "/Off",
        "13": "/Yes" if data["pp4"] else "/Off",
        "14": "/On3" if data["pp5"] else "/Off",
        "15": data["hpi"],
        "16": data["psychhx"],
        "17": "/On1" if data["ft1"] else "/Off",
        "18": "/On2" if data["ft2"] else "/Off",
        "19": "/On3" if data["ft3"] else "/Off",
        "37": data["exam_date"],
        "38": data["exam_time"],
    })

    # Telephone number continuation field is anonymous (no /T) — target by rect
    set_anon_text_by_rect(writer, x_min=220, x_max=232, y_min=620, y_max=645, page_idx=0, value=rest)

    # "On ___" exam date field is also anonymous — target by rect
    set_anon_text_by_rect(writer, x_min=100, x_max=260, y_min=590, y_max=610, page_idx=0, value=data["exam_date"])

    if data["pp2"]:
        check_anon_by_y(writer, 370, 398, page_idx=0, check=True)
    buf = io.BytesIO()
    writer.write(buf)
    buf.seek(0)
    return buf

def fill_form42(data):
    reader = PdfReader(os.path.join(BASE, "form42_original.pdf"))
    writer = PdfWriter()
    writer.append(reader)
    writer.set_need_appearances_writer(True)
    set_fields(writer, {
        "4":  data["exam_date"],
        "9":  "/On" if data["ft1"] else "/Off",
        "10": "/On" if data["ft2"] else "/Off",
        "11": "/On" if data["ft3"] else "/Off",
        "27": data["exam_date"],
    })
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

# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    with open(os.path.join(BASE, "static", "index.html")) as f:
        return f.read()

@app.route("/generate", methods=["POST"])
def generate():
    try:
        data = request.get_json()
        # coerce booleans
        for k in ["pp1","pp2","pp3","pp4","pp5","ft1","ft2","ft3"]:
            data[k] = bool(data.get(k, False))
        f1  = fill_form1(data)
        f42 = fill_form42(data)
        combined = merge_to_bytes([f1, f42])
        date_str = data.get("exam_date", "").replace("/", "-")
        filename = f"Form1_Form42_{date_str}.pdf"
        return send_file(combined, mimetype="application/pdf",
                         as_attachment=False,
                         download_name=filename)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    print(f"\n✓ EMStash Form Generator running at http://localhost:{port}\n")
    app.run(debug=False, host="0.0.0.0", port=port)
