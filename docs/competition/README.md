# Competition report files

This directory keeps the editable report source, the delivered DOCX, its exact input template, and generated figures together. The repository root is the working directory for all commands below; every project path is relative to the clone.

## Rebuild the DOCX

Requirements: Python 3.10 or newer, the packages listed in `requirements.txt`, and an installed Chinese font. On Windows the builder searches common Microsoft YaHei/SimHei fonts automatically. On Linux or macOS, set `PQC_REPORT_FONT` (and optionally `PQC_REPORT_FONT_BOLD`) to local font files that contain Simplified Chinese glyphs.

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r docs/competition/requirements.txt
python docs/competition/build_report.py
```

The script uses `docs/competition/reference_template.docx` by default. An alternate template may be supplied explicitly:

```powershell
python docs/competition/build_report.py --template path\to\another_template.docx
```

It regenerates the figures under `docs/competition/assets/`, writes `MLKEM1024_竞赛技术报告.docx` beside the script, and writes small build metadata under the ignored `build/competition_report/` directory. It reads archived project evidence and does not invoke Vivado, Vitis HLS, XSim, or the PYNQ board. Keep the generated DOCX as the submitted deliverable; use `docs/COMPETITION_REPORT.md` as the editable narrative source.

## Review before submission

Open the generated DOCX in Word or LibreOffice and inspect every page after rebuilding, especially page breaks, diagrams, tables, and the three reserved board/Jupyter photo slots. Replace those slots only with newly captured project photos; do not alter historical measurement values without updating the linked source evidence and its review record.
