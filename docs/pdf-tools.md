# PDF Tools

All `doc pdf` commands save output inside a folder named after the source PDF.
If no output path is given, files are saved to `~/Downloads`. Use `.` to save in the current directory.

---

### `doc pdf merge`
Merge all PDF files in a directory into a single PDF.
The output file is named `<folder-name>_merged.pdf`.

```bash
toolbook doc pdf merge <PDF_DIR> <OUTPUT_DIR> [--open]
```

| Argument | Required | Description |
|----------|----------|-------------|
| `PDF_DIR` | Yes | Directory containing the PDF files to merge |
| `OUTPUT_DIR` | Yes | Directory where the merged PDF will be saved |
| `--open` | No | Open the merged PDF after saving |

**Examples:**
```bash
toolbook doc pdf merge ./my-pdfs ./output
toolbook doc pdf merge C:\Docs\Reports C:\Docs\Merged --open
```

**Python:**
```python
from toolbook.tDocs import PDFMerger

# Merge all PDFs in a folder, save result to ./output
result = PDFMerger("./my-pdfs", "./output")
print(result)  # ./output/my-pdfs_merged.pdf

# With live progress logs
result = PDFMerger("./my-pdfs", "./output", log=print)
# 📂 Source folder : /abs/path/my-pdfs
# 📑 PDFs found    : 3
#
#   [1/3] invoice.pdf  (2 pages)
#   [2/3] report.pdf   (5 pages)
#   [3/3] summary.pdf  (1 page)
#
# 📄 Total pages   : 8
```

---

### `doc pdf split`
Split a PDF into individual pages, one PDF per page.
Pages are saved inside a folder named after the source PDF.

```bash
toolbook doc pdf split <PDF_FILE> [OUTPUT_PATH] [--open]
```

| Argument | Required | Description |
|----------|----------|-------------|
| `PDF_FILE` | Yes | Path to the PDF file to split |
| `OUTPUT_PATH` | No | Base directory for the output folder. Omit → `~/Downloads`, `.` → current directory |
| `--open` | No | Open the output folder after splitting |

**Examples:**
```bash
# Save to ~/Downloads/document/
toolbook doc pdf split ./document.pdf

# Save to current directory and open folder
toolbook doc pdf split ./document.pdf . --open

# Save to custom path
toolbook doc pdf split ./document.pdf ./output --open
```

**Python:**
```python
from toolbook.tDocs import PDFSplit

# Save to ~/Downloads/document/
result = PDFSplit("./document.pdf")
print(result)  # ~/Downloads/document

# Save to current directory: ./document/
result = PDFSplit("./document.pdf", ".")
print(result)  # ./document

# Save to custom path: ./output/document/
result = PDFSplit("./document.pdf", "./output")
print(result)  # ./output/document

# With live progress logs
result = PDFSplit("./document.pdf", ".", log=print)
# 📂 Output folder : ./document
# 📄 Source        : ./document.pdf
# 📑 Total pages   : 5
#
#   [1/5] Saved → page_1.pdf
#   [2/5] Saved → page_2.pdf
#   ...
```

---

### `doc pdf extract-img`
Extract all embedded images from a PDF, saving each as a separate image file.
Images are saved inside a folder named after the source PDF.

```bash
toolbook doc pdf extract-img <PDF_FILE> [OUTPUT_PATH] [--open]
```

| Argument | Required | Description |
|----------|----------|-------------|
| `PDF_FILE` | Yes | Path to the PDF file to extract images from |
| `OUTPUT_PATH` | No | Base directory for the output folder. Omit → `~/Downloads`, `.` → current directory |
| `--open` | No | Open the output folder after extracting |

**Examples:**
```bash
# Save to ~/Downloads/document/
toolbook doc pdf extract-img ./document.pdf

# Save to current directory and open folder
toolbook doc pdf extract-img ./document.pdf . --open

# Save to custom path
toolbook doc pdf extract-img ./document.pdf ./output --open
```

**Python:**
```python
from toolbook.tDocs import PDFIMGExtractor

# Save to ~/Downloads/document/
result = PDFIMGExtractor("./document.pdf")
print(result)  # ~/Downloads/document

# Save to current directory: ./document/
result = PDFIMGExtractor("./document.pdf", ".")
print(result)  # ./document

# Save to custom path: ./output/document/
result = PDFIMGExtractor("./document.pdf", "./output")
print(result)  # ./output/document

# With live progress logs
result = PDFIMGExtractor("./document.pdf", ".", log=print)
# 📂 Output folder : ./document
# 📄 Source        : ./document.pdf
# 📑 Total pages   : 3
#
#   Page 1/3 — 2 image(s) found
#     ✔ Saved → image_p1_21.png
#     ✔ Saved → image_p1_23.jpeg
#   Page 2/3 — 0 image(s) found
#   Page 3/3 — 1 image(s) found
#     ✔ Saved → image_p3_44.jpeg
#
# 🖼  Total images extracted: 3
```

---

### `doc pdf convert-docx`
Convert a PDF file to DOCX format.
The output file is saved as `<pdf-name>.docx` in the chosen directory.

```bash
toolbook doc pdf convert-docx <PDF_FILE> [OUTPUT_PATH] [--open]
```

| Argument | Required | Description |
|----------|----------|-------------|
| `PDF_FILE` | Yes | Path to the PDF file to convert |
| `OUTPUT_PATH` | No | Directory to save the .docx file. Omit → `~/Downloads`, `.` → current directory |
| `--open` | No | Open the generated .docx file after conversion |

**Examples:**
```bash
# Save to ~/Downloads/
toolbook doc pdf convert-docx ./document.pdf

# Save to current directory and open the file
toolbook doc pdf convert-docx ./document.pdf . --open

# Save to custom path
toolbook doc pdf convert-docx ./document.pdf ./output --open
```

**Python:**
```python
from toolbook.tDocs import PDFToDocx

# Save to ~/Downloads/document.docx
result = PDFToDocx("./document.pdf")
print(result)  # ~/Downloads/document.docx

# Save to current directory: ./document.docx
result = PDFToDocx("./document.pdf", ".")
print(result)  # ./document.docx

# Save to custom path: ./output/document.docx
result = PDFToDocx("./document.pdf", "./output")
print(result)  # ./output/document.docx

# With live progress logs
result = PDFToDocx("./document.pdf", ".", log=print)
# 📄 Source  : /abs/path/document.pdf
# 📂 Output  : ./document.docx
# ⏳ Converting …
# ✔  Conversion complete
```
