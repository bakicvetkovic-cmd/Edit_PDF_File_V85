# User Guide — Edit PDF File V85

## 1. Overview

Edit PDF File is a Windows desktop tool for targeted visual edits to PDF pages. It is especially useful when a PDF is scanned and its printed content is stored as an image. For character-based replacement, the program captures character snapshots from the document and assembles the replacement from those snapshots.

The application works on a rendered page image while editing. Use **Preview** to inspect the result, then **Save New PDF** to export a new PDF file.

## 2. Opening a document

1. Click **Open PDF**.
2. Select the PDF file.
3. Use the zoom controls to inspect the page. **Fit to Window** adjusts the view to the available workspace.
4. Scroll horizontally or vertically if the page is larger than the viewing area.

## 3. Replacing an existing printed item

1. Click **Select Original Data / Character**.
2. Drag a red rectangle around the full item to be replaced. Include the complete printed characters, but avoid unrelated text where possible.
3. Click **Replace Original with New Data / Character**.
4. If the original content was not read reliably, enter it when prompted.
5. Enter the replacement content.
6. If a character snapshot is missing, the program asks you to select that character on the page. Select only the requested character; the program captures it and continues.
7. Inspect the preview. Repeat or adjust the selection if necessary.
8. Click **Save New PDF** to save the edited document under a new name.

**Important:** replacement characters are assembled from image snapshots found in the source document. The program does not retype them using a substitute font. If the source document does not contain a usable example of a required character, the program may ask you to select one or may be unable to complete the replacement.

## 4. Selecting, moving, and resizing content

1. Click **Move Items**.
2. Select the content with the blue frame. The frame has four corner handles and guide lines extending toward the page edges.
3. Drag inside the blue frame to move the selected content.
4. Drag a corner handle to resize it proportionally or use **Resize Item (Selected Area)** to enter exact dimensions.
5. Width (W) and height (H) are displayed in millimeters.
6. Use the arrow keys for precise movement: one press moves by 1 pixel; **Shift + Arrow** moves by 10 pixels.

## 5. Adding text

1. Click **Add Text**.
2. Click the location on the page where the text should begin.
3. In the dialog, enter the text. Press **Enter** to create a new line; click **Add** to insert the text.
4. Choose a font family, style (Regular, Bold, Italic, or Bold Italic), size in points, alignment, color, and right margin in millimeters.
5. The new text appears in a gray dashed frame. To move or resize it, click **Move Items** to activate the blue frame.

Alignment applies within the area from the clicked starting point to the document’s right margin. A right margin of 0 mm places the text flush with the page edge.

## 6. Editing added text

1. Select the added text using **Move Items** and its blue frame.
2. Click **Edit Added Text**.
3. Change the text or its font, style, size, alignment, right margin, or color.
4. Press **Enter** for a new line. Click **Apply** to commit the changes.
5. Use **Move Items** to return to the blue movement/resizing frame when needed.

Only text added by this application can be edited as text. Original scanned text is image content and must be handled through selection/replacement.

## 7. Copy, cut, and paste

- Select content with **Move Items**, then click **Copy** or **Cut**.
- Click the destination point on the page, then click **Paste**.
- When clipboard content is available from another application, choose **Paste as Image** or **Paste as Text** when prompted.
- Text pasted from the system clipboard opens a text-entry dialog so you can review or edit it before insertion.

Supported external image clipboard formats depend on the source application and Windows clipboard availability.

## 8. Font preview

1. Click **Show Fonts**.
2. Select the text with the green frame.
3. Release the mouse; the font preview window opens.
4. For a text-based PDF with embedded font information, the program may identify the embedded font directly. For scanned PDFs, it shows candidate system fonts alongside the original character snapshot for visual comparison.

Font-family identification on scanned pages is approximate. Use the preview to compare glyph shapes rather than treating the candidate as a guaranteed match.

## 9. Undo, redo, and clearing frames

- **Undo** reverses the last supported edit. Shortcut: `Ctrl+Z`.
- **Redo** restores an undone edit. Shortcut: `Ctrl+Y`.
- **Clear Frame** removes the active selection frame; it does not erase already-applied edits.
- **Delete Selected Item** removes the currently selected movable/added item where supported.
- Press `Esc` to cancel the active rectangle selection.

## 10. Saving and reviewing

1. Click **Create Preview** to render the current result for inspection.
2. Check text alignment, character shape, position, dimensions, and any overlap with nearby content.
3. Click **Save New PDF** and choose a destination and filename.
4. Open the saved PDF in a separate viewer and verify the final page before using or distributing it.

The original PDF is not overwritten by the normal **Save New PDF** workflow.

## 11. Troubleshooting

**The program cannot recognize the selected original text**

- Make sure the red rectangle fully covers the printed item.
- For scanned pages, OCR may not recognize every character. Enter the original item when prompted.
- If the program asks for a missing snapshot, select a clear instance of that character on the page.

**Font preview is inaccurate or incomplete**

- Scanned pages do not contain original font metadata. Candidate fonts are estimates for visual comparison.
- Select a short word or a few characters from the same font and avoid surrounding lines or graphics.
- Confirm that Windows has fonts installed and available to the current user.

**Clipboard image does not paste**

- Copy the image again from the source application and ensure it is an actual image on the clipboard.
- Try pasting as an image. Some applications expose clipboard formats differently, so not every source is guaranteed to work.

**Dependencies fail to install**

- Confirm that Python is installed and available on the system PATH.
- Check the internet connection and retry.
- Install the packages listed in `requirements.txt` manually if automatic installation fails.
- For Tesseract-based OCR, install the Tesseract application separately; installing `pytesseract` alone is not sufficient.
