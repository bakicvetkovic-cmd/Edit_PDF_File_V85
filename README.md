# Edit PDF File V85

A desktop utility for making targeted changes to PDF documents, including scanned PDFs. It can replace selected printed content using character image snapshots from the source document, add and edit text, move/resize selected content, copy/paste content, and compare fonts.

## Features

- Select original content with a red rectangle and replace it using character snapshots captured from the PDF page.
- For scanned PDFs, capture missing character snapshots by selecting the required character when prompted.
- Preview changes before saving a new PDF; the original file is not overwritten by the Save New PDF command.
- Move and resize selected content with the blue frame, corner handles, arrow keys, or numeric width/height values in millimeters.
- Display selection width (W) and height (H) in millimeters. Extended guide lines reach the page edges for the supported selection modes.
- Add and edit text with system fonts, font style, size, color, alignment, and right margin.
- Copy, cut, and paste selected content. Clipboard content from other applications can be pasted as an image or text when supported.
- Inspect font choices visually. Text-based PDFs may provide embedded font information; scanned-PDF font matching is an estimate.
- Undo/Redo, zoom controls, and fit-to-window view.

## Requirements

- Windows 10/11 recommended (the application uses Windows clipboard formats for some image-paste operations).
- Python 3 installed with Tkinter available. The standard Windows Python installer includes Tkinter.
- Internet access may be required on first launch because the program installs missing Python packages automatically.
- Optional: the Tesseract OCR application for additional OCR support. The Python package `pytesseract` alone does not install the Tesseract executable. RapidOCR is also used as an OCR fallback and may be installed automatically when needed.

Python packages used by the application include PyMuPDF, NumPy, OpenCV, Pillow, pytesseract, fontTools, and (when needed) rapidocr_onnxruntime.

## Run

1. Extract the ZIP archive to a folder.
2. Double-click `Run_Edit_PDF_File.bat`.
3. If Windows asks which application to use, install Python and choose Python to run the `.bat` file.
4. On first launch, allow the program to install any missing Python packages. An internet connection may be required.

You can also start it from a terminal:

```bash
python Edit_PDF_File_V85.py
```

## Quick start: replace printed content

1. Click **Open PDF** and choose a PDF file.
2. Click **Select Original Data / Character**.
3. Drag a red rectangle around the complete original item you want to replace.
4. Click **Replace Original with New Data / Character**.
5. Enter the original content if prompted, then enter the replacement content.
6. If the program asks for a missing character snapshot, select that character in the document. The program uses the actual character image from the source page rather than typing a replacement in a different font.
7. Review the preview. If it looks correct, click **Save New PDF** and choose an output filename.

## Notes and limitations

- Work on a copy of important documents and review the preview carefully before saving.
- Scanned PDFs contain page images rather than a text layer. OCR and font-size/font-family estimates can be imperfect; select tightly around the relevant content and verify the result visually.
- Font comparison for scanned pages is a visual aid, not a guarantee of the original font identity.
- The editor is designed for targeted visual changes. It is not a full PDF layout or document-structure editor.
- The application may need internet access to install dependencies. PDF processing is performed locally by the application; no upload service is built into this program.

## Open-source license

A MIT license template is included as `LICENSE.txt`. Before publishing, replace the copyright-holder placeholder with the appropriate name or project owner and confirm that you have the rights to publish the source and dependencies under their respective licenses. This project’s license does not relicense third-party packages.
