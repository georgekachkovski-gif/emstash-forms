# EMStash — Form 1 & 42 Generator

Fills the official Ontario Mental Health Act Form 1 and Form 42 PDFs.

---

## Deploy to Railway (free, ~2 minutes)

1. Go to **https://railway.app** and sign up (free)
2. Click **"New Project" → "Deploy from local folder"** (or connect GitHub)
3. Drag and drop this entire folder (or zip file)
4. Railway auto-detects Python and deploys — no config needed
5. Click **"Generate Domain"** in the Railway dashboard to get your public URL
   e.g. `https://emstash-forms-production.up.railway.app`

### Embed in Softr

1. In your Softr page editor, add a **"Custom Code"** or **"Embed"** block
2. Paste this, replacing YOUR_RAILWAY_URL:

```html
<iframe
  src="https://YOUR_RAILWAY_URL"
  width="100%"
  height="900px"
  style="border:none;border-radius:12px"
  allow="downloads"
></iframe>
```

3. Adjust height as needed (900px fits the full form comfortably)

---

## Run locally

```bash
pip install -r requirements.txt
python app.py
# Open http://localhost:5000
```

---

## Files

| File | Purpose |
|------|---------|
| `app.py` | Flask server |
| `static/index.html` | Wizard UI |
| `form1_original.pdf` | Official Ontario Form 1 (do not edit) |
| `form42_original.pdf` | Official Ontario Form 42 (do not edit) |
| `railway.toml` | Railway deployment config |
| `requirements.txt` | Python dependencies |

## Notes
- Physician name, patient name/address, and signatures are left blank for handwriting
- Box B is not used (Box A only)
- Generated PDF is the actual government form with fields filled — legally valid
