"""
app.py — VeryBerryLab Web Server
=================================
Upload a Pheno 4 Worksheet 2 .xlsx file and get the full interactive
research dashboard in your browser.

Run from the veryberrylab/ directory:
    python3 app.py

Then open:  http://localhost:5001
"""

import sys
from pathlib import Path

from flask import Flask, Response, render_template, request

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.etl import run_etl_from_bytes              # noqa: E402
from viz.pheno4_stats_viz import generate_html      # noqa: E402

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB cap


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("upload.html", error=None)


@app.errorhandler(413)
def too_large(_e):
    return render_template("upload.html", error="File exceeds 50 MB limit."), 413


@app.route("/analyze", methods=["POST"])
def analyze():
    if "worksheet" not in request.files:
        return render_template("upload.html", error="No file received."), 400

    f = request.files["worksheet"]

    if not f.filename:
        return render_template("upload.html", error="No file selected."), 400

    if not f.filename.lower().endswith(".xlsx"):
        return render_template(
            "upload.html",
            error=f"'{f.filename}' is not an .xlsx file. Please upload an Excel workbook.",
        ), 400

    xlsx_bytes = f.read()
    if len(xlsx_bytes) == 0:
        return render_template("upload.html", error="Uploaded file is empty."), 400

    try:
        df = run_etl_from_bytes(xlsx_bytes)
    except Exception as exc:
        return render_template(
            "upload.html",
            error=f"Could not read workbook: {exc}",
        ), 422

    if df.empty:
        return render_template(
            "upload.html",
            error=(
                "No data found. Make sure the workbook follows the Phenotyping 4 "
                "Worksheet 2 format (one sheet per cultivar, named Alb, Bri, Cab, …)."
            ),
        ), 422

    try:
        html_str = generate_html(df)
    except Exception as exc:
        return render_template(
            "upload.html",
            error=f"Analysis failed: {exc}",
        ), 500

    return Response(html_str, mimetype="text/html")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print()
    print("  ╔══════════════════════════════════════════════════╗")
    print("  ║  VeryBerryLab — Phenotyping Dashboard Server     ║")
    print("  ║  Open  →  http://localhost:5001                  ║")
    print("  ╚══════════════════════════════════════════════════╝")
    print()
    app.run(debug=False, port=5001, host="0.0.0.0")
