# Image Tools

All `doc img` commands convert a single image file to the target format.
If no output path is given, the converted file is saved to `~/Downloads`. Use `.` to save in the current directory.

---

### `doc img convert-png`
Convert any image file to PNG format.
The output file is saved as `<original-name>.png` in the chosen directory.

```bash
toolbook doc img convert-png <IMAGE_FILE> [OUTPUT_PATH] [--open]
```

| Argument | Required | Description |
|----------|----------|-------------|
| `IMAGE_FILE` | Yes | Path to the source image file |
| `OUTPUT_PATH` | No | Destination directory or file path. Omit → `~/Downloads`, `.` → current directory |
| `--open` | No | Open the converted image after saving |

**Examples:**
```bash
# Save to ~/Downloads/photo.png
toolbook doc img convert-png ./photo.jpg

# Save to current directory and open the file
toolbook doc img convert-png ./photo.jpg . --open

# Save to a custom directory
toolbook doc img convert-png ./photo.jpg ./output --open

# Save to an explicit file path
toolbook doc img convert-png ./photo.jpg ./output/renamed.png
```

**Python:**
```python
from toolbook.tDocs import IMGConvertToPNG

# Save to ~/Downloads/photo.png
result = IMGConvertToPNG("./photo.jpg")
print(result)  # ~/Downloads/photo.png

# Save to current directory: ./photo.png
result = IMGConvertToPNG("./photo.jpg", ".")
print(result)  # ./photo.png

# Save to a custom directory: ./output/photo.png
result = IMGConvertToPNG("./photo.jpg", "./output")
print(result)  # ./output/photo.png

# With live progress logs
result = IMGConvertToPNG("./photo.jpg", ".", log=print)
# 📄 Source  : /abs/path/photo.jpg
# 📂 Output  : ./photo.png
# ⏳ Converting …
# ✔  Conversion complete
```

---

### `doc img convert-jpg` / `convert-jpeg`
Convert any image file to JPEG format.
Transparent images (e.g. PNG with alpha) are flattened to an RGB background automatically.
The output file is saved as `<original-name>.jpg` in the chosen directory.

```bash
toolbook doc img convert-jpg  <IMAGE_FILE> [OUTPUT_PATH] [--open]
toolbook doc img convert-jpeg <IMAGE_FILE> [OUTPUT_PATH] [--open]
```

| Argument | Required | Description |
|----------|----------|-------------|
| `IMAGE_FILE` | Yes | Path to the source image file |
| `OUTPUT_PATH` | No | Destination directory or file path. Omit → `~/Downloads`, `.` → current directory |
| `--open` | No | Open the converted image after saving |

**Examples:**
```bash
# Save to ~/Downloads/photo.jpg
toolbook doc img convert-jpg ./photo.png

# Save to current directory and open the file
toolbook doc img convert-jpg ./photo.png . --open

# Save to a custom directory
toolbook doc img convert-jpeg ./photo.png ./output --open

# Save to an explicit file path
toolbook doc img convert-jpg ./photo.png ./output/renamed.jpg
```

**Python:**
```python
from toolbook.tDocs import IMGConvertToJPG

# Save to ~/Downloads/photo.jpg
result = IMGConvertToJPG("./photo.png")
print(result)  # ~/Downloads/photo.jpg

# Save to current directory: ./photo.jpg
result = IMGConvertToJPG("./photo.png", ".")
print(result)  # ./photo.jpg

# Save to a custom directory: ./output/photo.jpg
result = IMGConvertToJPG("./photo.png", "./output")
print(result)  # ./output/photo.jpg

# With live progress logs
result = IMGConvertToJPG("./photo.png", ".", log=print)
# 📄 Source  : /abs/path/photo.png
# 📂 Output  : ./photo.jpg
# ⏳ Converting …
# ✔  Conversion complete
```

---

### Output path rules

All image commands follow the same output path convention:

| `OUTPUT_PATH` value | Result |
|---------------------|--------|
| Omitted / `None` | `~/Downloads/<original-name>.<ext>` |
| `.` | `./<original-name>.<ext>` (current directory) |
| A directory path | `<directory>/<original-name>.<ext>` |
| A full file path (has extension) | Used as-is |
