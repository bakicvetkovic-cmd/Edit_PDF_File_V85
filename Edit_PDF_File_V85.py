import os, sys, tempfile, subprocess, ctypes, struct, io
try:
    import fitz
except ImportError:
    subprocess.check_call([sys.executable,'-m','pip','install','PyMuPDF'])
    import fitz
try:
    import numpy as np
except ImportError:
    subprocess.check_call([sys.executable,'-m','pip','install','numpy'])
    import numpy as np
try:
    import cv2
except ImportError:
    subprocess.check_call([sys.executable,'-m','pip','install','opencv-python'])
    import cv2
try:
    from PIL import Image, ImageTk, ImageDraw, ImageFilter, ImageGrab
except ImportError:
    subprocess.check_call([sys.executable,'-m','pip','install','Pillow'])
    from PIL import Image, ImageTk, ImageDraw, ImageFilter, ImageGrab
try:
    import pytesseract
except ImportError:
    subprocess.check_call([sys.executable,'-m','pip','install','pytesseract'])
    import pytesseract
try:
    import fontTools
except ImportError:
    subprocess.check_call([sys.executable,'-m','pip','install','fonttools'])
    import fontTools
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime

# V58 DIJAGNOSTIKA: izvestaj se cuva pored ovog .py fajla.
V71_LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Edit_PDF_File_log.txt')
def v63_log(message=''):
    try:
        with open(V68_LOG_PATH, 'a', encoding='utf-8') as _f:
            _f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")
    except Exception:
        pass
try:
    with open(V68_LOG_PATH, 'a', encoding='utf-8') as _f:
        _f.write('\n=== NOVA SESIJA V71 ===\n')
except Exception:
    pass
v63_log('Program started')

# V33: napredni lokalni OCR kao dopuna Tesseract-u. Koristi se samo kada
# Tesseract ne uspe da pročita tekst; PDF i ostale funkcije ostaju iste.
_rapidocr_engine = None
def _rapidocr_text(img):
    global _rapidocr_engine
    try:
        if _rapidocr_engine is None:
            try:
                from rapidocr_onnxruntime import RapidOCR
            except ImportError:
                subprocess.check_call([sys.executable,'-m','pip','install','rapidocr_onnxruntime'])
                from rapidocr_onnxruntime import RapidOCR
            _rapidocr_engine = RapidOCR()
        # RapidOCR radi sa PIL slikom ili numpy nizom, zavisno od verzije.
        arr=np.array(img.convert('RGB'))
        result, _ = _rapidocr_engine(arr)
        vals=[]
        if result:
            for item in result:
                try:
                    txt=str(item[1]).strip(); score=float(item[2])
                except Exception:
                    continue
                if txt and score >= 0.25:
                    vals.append((txt,score))
        vals.sort(key=lambda x:x[1], reverse=True)
        return ' '.join(x[0] for x in vals)
    except Exception:
        return ''

TITLE='Edit PDF File V85'


def ocr_boxes(img):
    """Return OCR character boxes in top-left coordinates."""
    try:
        raw=pytesseract.image_to_boxes(img, lang='srp_latn+eng', config='--psm 7')
    except Exception:
        return []
    H=img.height
    out=[]
    for line in raw.splitlines():
        p=line.split()
        if len(p)<5: continue
        ch=p[0]
        try:
            x0,y0,x1,y1=map(int,p[1:5])
        except Exception:
            continue
        top=max(0,H-y1); bottom=min(H,H-y0)
        if x1>x0 and bottom>top:
            out.append((ch,x0,top,x1,bottom))
    out.sort(key=lambda b:b[1])
    return out


def norm_char(ch):
    if ch in ',·': return '.'
    return ch


def _font_name_from_embedded_ttf(doc, page, resource_name):
    """Try to resolve a PDF font resource to the real family name."""
    try:
        # PyMuPDF's get_fonts() gives the resource xref and PDF BaseFont name.
        entry=None
        for f in page.get_fonts(full=True):
            if len(f) >= 5 and (f[3] == resource_name or f[4] == resource_name):
                entry=f; break
        if not entry:
            return None
        xref=int(entry[0])
        base=str(entry[3] or '')
        import re
        desc_info=doc.xref_get_key(xref,'DescendantFonts')
        if not desc_info or len(desc_info)<2:
            return None
        desc_text=str(desc_info[1])
        # For Type0/CID fonts the FontDescriptor is often embedded inline in
        # the DescendantFonts object, so there may be no separate descriptor xref.
        m=re.search(r'/FontFile2 (\d+) 0 R', desc_text)
        if not m:
            m=re.search(r'/FontFile (\d+) 0 R', desc_text)
        if not m:
            refs=re.findall(r'(\d+) 0 R', desc_text)
            if refs:
                for ref in refs:
                    try:
                        obj=doc.xref_object(int(ref), compressed=False)
                    except Exception:
                        continue
                    m=re.search(r'/FontFile2 (\d+) 0 R', obj)
                    if not m:
                        m=re.search(r'/FontFile (\d+) 0 R', obj)
                    if m: break
        if not m:
            return None
        font_xref=int(m.group(1))
        data=doc.xref_stream(font_xref)
        if not data:
            return None
        try:
            from fontTools.ttLib import TTFont
        except Exception:
            return None
        from io import BytesIO
        tt=TTFont(BytesIO(data), lazy=False)
        vals=[]
        for n in tt['name'].names:
            if n.nameID in (1,4,6):
                try: v=n.toUnicode().strip()
                except Exception: continue
                if v: vals.append((n.nameID,v))
        # Prefer family name (1), then full name (4), then PostScript (6).
        for wanted in (1,4,6):
            for nid,v in vals:
                if nid==wanted:
                    return v
        return None
    except Exception:
        return None


def _clean_embedded_name(name):
    if not name: return ''
    name=str(name)
    if '+' in name:
        name=name.split('+',1)[1]
    return name


class App:
    def __init__(self,root):
        self.root=root
        self.root.title(TITLE)
        self.root.geometry('1250x900')
        self.doc=None; self.path=None; self.page_index=0
        self.page_img=None; self.display_img=None; self.tkimg=None; self.view_img=None
        self.scale=1.0; self.rect=None; self.drag_start=None
        # V24: potpuno odvojen režim pomeranja, zasnovan na V19.
        self.move_rect=None
        self.move_action=None; self.move_anchor=None; self.move_orig_rect=None
        self.transform_base=None; self.transform_src_rect=None
        self.mode='idle'
        self.font_rect=None
        self.font_action='preview'
        self.add_text_point=None
        self.added_text_info=None
        # V67: interna clipboard memorija za Copy/Cut/Paste.
        self.clipboard_image=None
        self.clipboard_size=None
        self.clipboard_added_info=None
        self.clipboard_text=None
        self.clipboard_source=None
        self.paste_target=None
        self.last_click_point=None
        self.old_text=''; self.new_text=''
        self.char_samples={}       # character -> list of real image snapshots
        self.missing=[]; self.missing_i=0
        self.result=None
        # V16: istorija samo zavrsenih zamena (Undo/Redo). Sve ostalo ostaje isto.
        self.undo_stack=[]
        self.redo_stack=[]
        self._build_ui()
        self.root.bind('<Escape>',lambda e:self.cancel_rect())
        self.root.bind('<Control-z>',lambda e:(self.undo(), 'break')[1])
        self.root.bind('<Control-y>',lambda e:(self.redo(), 'break')[1])
        self.root.bind('<Control-c>',lambda e:(self.copy_selection(), 'break')[1])
        self.root.bind('<Control-x>',lambda e:(self.cut_selection(), 'break')[1])
        self.root.bind('<Control-v>',lambda e:(self.paste_selection(), 'break')[1])
        self.root.bind('<Left>',self.on_key); self.root.bind('<Right>',self.on_key)
        self.root.bind('<Up>',self.on_key); self.root.bind('<Down>',self.on_key)

    def _build_ui(self):
        # V81: kozmetičko grupisanje alatki po funkciji. Funkcije dugmadi nisu menjane.
        menubar=tk.Menu(self.root)
        editmenu=tk.Menu(menubar,tearoff=False)
        editmenu.add_command(label='↶ Undo',command=self.undo,accelerator='Ctrl+Z')
        editmenu.add_command(label='↷ Redo',command=self.redo,accelerator='Ctrl+Y')
        editmenu.add_separator()
        editmenu.add_command(label='Copy Selected Item',command=self.copy_selection,accelerator='Ctrl+C')
        editmenu.add_command(label='Cut Selected Item',command=self.cut_selection,accelerator='Ctrl+X')
        editmenu.add_command(label='Paste Item',command=self.paste_selection,accelerator='Ctrl+V')
        editmenu.add_separator()
        editmenu.add_command(label='Move Items',command=lambda:self.set_mode('move'))
        editmenu.add_command(label='Add Text',command=lambda:self.set_mode('addtext'))
        editmenu.add_command(label='Edit Added Text',command=self.edit_added_text)
        editmenu.add_command(label='Delete Selected Item',command=self.delete_move_selection)
        editmenu.add_command(label='Resize Selected Area',command=self.resize_move_selection_dialog)
        editmenu.add_command(label='Show Fonts',command=self.show_font_preview_from_selection)
        editmenu.add_command(label='Select Original Item',command=lambda:self.set_mode('old'))
        menubar.add_cascade(label='Edit',menu=editmenu)
        self.root.config(menu=menubar)

        # Dva reda trake ostaju kao u prethodnim verzijama, ali su dugmad sada
        # grupisana po funkciji. Između grupa je uspravni separator, a naziv
        # grupe stoji iznad njenih dugmadi.
        top1=ttk.Frame(self.root,padding=(8,6,8,3)); top1.pack(fill='x')
        top2=ttk.Frame(self.root,padding=(8,3,8,7)); top2.pack(fill='x')

        def add_group(parent, title, buttons, sep_before=True):
            if sep_before:
                ttk.Separator(parent,orient='vertical').pack(side='left',fill='y',padx=7)
            gf=ttk.Frame(parent)
            gf.pack(side='left',anchor='n')
            ttk.Label(gf,text=title,font=('TkDefaultFont',9,'bold')).pack(anchor='center',pady=(0,2))
            bf=ttk.Frame(gf)
            bf.pack()
            for item in buttons:
                text, command, padx = item[:3]
                kwargs = {}
                if len(item) >= 4:
                    kwargs['width'] = item[3]
                ttk.Button(bf,text=text,command=command,**kwargs).pack(side='left',padx=padx)
            return gf

        add_group(top1,'File Management',[
            ('Open PDF',self.open_pdf,2),
            ('Save New PDF',self.save,2),
        ],sep_before=False)

        add_group(top1,'Select and Replace Data / Characters',[
            ('Select Original\nData / Character',lambda:self.set_mode('old'),2,20),
            ('Replace Original with New\nData / Character',self.extract_old,2,22),
        ])

        add_group(top1,'Item Tools',[
            ('Move Items',lambda:self.set_mode('move'),2),
            ('Copy',self.copy_selection,2),
            ('Cut',self.cut_selection,2),
            ('Paste',self.paste_selection,2),
            ('Resize Item\n    (Selected Area)',self.resize_move_selection_dialog,2,24),
        ])

        add_group(top1,'Add / Edit',[
            ('Add Text',lambda:self.set_mode('addtext'),2),
            ('Edit Added Text',self.edit_added_text,2),
            ('Delete Selected Item',self.delete_move_selection,2),
        ])

        add_group(top2,'Font Preview',[
            ('Show Fonts',self.show_font_preview_from_selection,2),
        ],sep_before=False)

        add_group(top2,'Selection Frames',[
            ('Clear Frame',self.clear_rect,2),
        ])

        add_group(top2,'History',[
            ('↶ Undo',self.undo,2),
            ('↷ Redo',self.redo,2),
        ])

        add_group(top2,'Preview',[
            ('Create Preview',self.preview,2),
        ])

        # Zum ostaje odvojen, kao i do sada.
        ttk.Separator(top2,orient='vertical').pack(side='left',fill='y',padx=7)
        zg=ttk.Frame(top2)
        zg.pack(side='left',anchor='n')
        ttk.Label(zg,text='Zoom:',font=('TkDefaultFont',9,'bold')).pack(anchor='center',pady=(0,2))
        zbf=ttk.Frame(zg)
        zbf.pack()
        ttk.Button(zbf,text='−',width=3,command=lambda:self.change_zoom(0.85)).pack(side='left')
        self.zoom_var=tk.StringVar(value='100%')
        ttk.Button(zbf,textvariable=self.zoom_var,width=7,command=lambda:self.set_zoom(1.0)).pack(side='left',padx=2)
        ttk.Button(zbf,text='+',width=3,command=lambda:self.change_zoom(1.18)).pack(side='left')
        ttk.Button(zbf,text='Fit to Window',command=self.fit_view).pack(side='left',padx=4)

        # V15: nema više trajnih polja za stari/novi podatak.
        # Program prepoznaje stari podatak iz označenog područja, a novi
        # podatak traži u dijalogu tek kada su snapshot-i spremni.
        self.old=tk.StringVar()
        self.new=tk.StringVar()
        self.info=tk.StringVar(value='Open a PDF and select the item you want to replace with the red rectangle.')
        ttk.Label(self.root,textvariable=self.info,relief='sunken',anchor='w',padding=5).pack(fill='x',padx=8)

        view=ttk.Frame(self.root)
        view.pack(fill='both',expand=True,padx=8,pady=8)
        self.canvas=tk.Canvas(view,bg='#444',highlightthickness=0,cursor='crosshair')
        self.vbar=ttk.Scrollbar(view,orient='vertical',command=self.canvas.yview)
        self.hbar=ttk.Scrollbar(view,orient='horizontal',command=self.canvas.xview)
        self.canvas.configure(xscrollcommand=self.hbar.set,yscrollcommand=self.vbar.set)
        self.canvas.grid(row=0,column=0,sticky='nsew')
        self.vbar.grid(row=0,column=1,sticky='ns')
        self.hbar.grid(row=1,column=0,sticky='ew')
        view.rowconfigure(0,weight=1); view.columnconfigure(0,weight=1)
        self.canvas.bind('<ButtonPress-1>',self.on_press)
        self.canvas.bind('<B1-Motion>',self.on_drag)
        self.canvas.bind('<ButtonRelease-1>',self.on_release)
        self.canvas.bind('<MouseWheel>',self.on_wheel)
        self.canvas.bind('<Button-4>',self.on_wheel)
        self.canvas.bind('<Button-5>',self.on_wheel)

    def _current_view_source(self):
        # After a preview, zooming must zoom the PREVIEW, not restore the original page.
        return self.result if self.result is not None else self.page_img

    def set_zoom(self,z):
        src=self._current_view_source()
        if src is None: return
        z=max(0.35,min(4.0,float(z)))
        self.scale=z
        if hasattr(self,'zoom_var'):
            self.zoom_var.set(f'{round(z*100):g}%')
        self.show_image(src, keep_scale=True)

    def change_zoom(self,factor):
        src=self._current_view_source()
        if src is None: return
        self.set_zoom(self.scale*factor)

    def fit_view(self):
        src=self._current_view_source()
        if src is None: return
        self.show_image(src, keep_scale=False)
        if hasattr(self,'zoom_var'):
            self.zoom_var.set(f'{round(self.scale*100):g}%')

    def on_wheel(self,e):
        # Ctrl+wheel = zoom, normal wheel = scroll vertically.
        if getattr(e,'state',0) & 0x0004:
            if e.num==4 or e.delta>0: self.change_zoom(1.12)
            else: self.change_zoom(0.89)
        else:
            if e.num==4 or e.delta>0: self.canvas.yview_scroll(-3,'units')
            else: self.canvas.yview_scroll(3,'units')
        return 'break'

    def open_pdf(self):
        p=filedialog.askopenfilename(filetypes=[('PDF','*.pdf')])
        if not p:return
        try:
            d=fitz.open(p)
            if not d: raise RuntimeError('The PDF has no pages.')
            self.doc=d; self.path=p; self.page_index=0
            self._log_pdf_structure_diagnostic()
            self.old.set(''); self.new.set(''); self.rect=None; self.move_rect=None; self.result=None; self.added_text_info=None
            self.move_action=None; self.transform_base=None; self.transform_src_rect=None
            if hasattr(self,'zoom_var'): self.zoom_var.set('100%')
            self.char_samples={}; self.missing=[]; self.missing_i=0
            self.undo_stack=[]; self.redo_stack=[]
            self.render_page()
            self.set_mode('idle')
        except Exception as e:
            messagebox.showerror(TITLE,str(e))

    def _log_pdf_structure_diagnostic(self):
        """V62: detaljna provera stvarne strukture otvorenog PDF-a.
        Ne menja obradu niti izbor teksta; samo zapisuje dijagnostiku odmah
        nakon otvaranja dokumenta.
        """
        try:
            v63_log('=== PDF STRUKTURA DIJAGNOSTIKA V62 ===')
            v63_log('PDF: putanja=' + repr(self.path))
            v63_log('PDF: broj stranica=' + str(len(self.doc)))
            for i in range(len(self.doc)):
                page=self.doc[i]
                try:
                    txt=page.get_text('text') or ''
                except Exception as e:
                    txt=''; v63_log('PAGE '+str(i+1)+': get_text(text) GRESKA='+repr(e))
                try:
                    words=page.get_text('words') or []
                except Exception as e:
                    words=[]; v63_log('PAGE '+str(i+1)+': get_text(words) GRESKA='+repr(e))
                try:
                    dd=page.get_text('dict') or {}
                except Exception as e:
                    dd={}; v63_log('PAGE '+str(i+1)+': get_text(dict) GRESKA='+repr(e))
                try:
                    rd=page.get_text('rawdict') or {}
                except Exception as e:
                    rd={}; v63_log('PAGE '+str(i+1)+': get_text(rawdict) GRESKA='+repr(e))
                blocks=dd.get('blocks',[])
                text_blocks=[b for b in blocks if b.get('type')==0]
                image_blocks=[b for b in blocks if b.get('type')==1]
                spans=[sp for b in text_blocks for ln in b.get('lines',[]) for sp in ln.get('spans',[])]
                raw_blocks=rd.get('blocks',[])
                raw_chars=sum(len(sp.get('chars') or []) for b in raw_blocks for ln in b.get('lines',[]) for sp in ln.get('spans',[]))
                v63_log('PAGE '+str(i+1)+': text_len='+str(len(txt))+' | words='+str(len(words))+' | dict_blocks='+str(len(blocks))+' | text_blocks='+str(len(text_blocks))+' | image_blocks='+str(len(image_blocks))+' | spans='+str(len(spans))+' | raw_blocks='+str(len(raw_blocks))+' | raw_chars='+str(raw_chars))
                if txt.strip():
                    v63_log('PAGE '+str(i+1)+': text_sample='+repr(txt[:180]))
                if words:
                    v63_log('PAGE '+str(i+1)+': first_words='+repr([w[4] for w in words[:12]]))
                if spans:
                    v63_log('PAGE '+str(i+1)+': first_spans='+repr([(sp.get('text','')[:80],sp.get('font',''),sp.get('size',0),sp.get('bbox')) for sp in spans[:12]]))
                try:
                    fonts=page.get_fonts(full=True) or []
                    v63_log('PAGE '+str(i+1)+': get_fonts_count='+str(len(fonts)))
                    for f in fonts:
                        v63_log('PAGE '+str(i+1)+': FONT='+repr(tuple(f)))
                except Exception as e:
                    v63_log('PAGE '+str(i+1)+': get_fonts GRESKA='+repr(e))
        except Exception as e:
            v63_log('PDF STRUKTURA V62 GRESKA='+repr(e))

    def render_page(self):
        page=self.doc[self.page_index]
        dpi=150
        pix=page.get_pixmap(matrix=fitz.Matrix(dpi/72,dpi/72),alpha=False)
        self.page_img=Image.frombytes('RGB',[pix.width,pix.height],pix.samples)
        self.show_image(self.page_img)

    def show_image(self,img, keep_scale=False):
        self.view_img=img
        self.display_img=img.copy()
        if keep_scale:
            s=self.scale
        else:
            maxw=max(600,self.canvas.winfo_width()-2); maxh=max(500,self.canvas.winfo_height()-2)
            if img.width and img.height:
                s=min(maxw/img.width,maxh/img.height,1.0)
            else:s=1
            self.scale=s
        if s!=1:
            self.display_img=img.resize((int(img.width*s),int(img.height*s)),Image.Resampling.LANCZOS)
        self.tkimg=ImageTk.PhotoImage(self.display_img)
        self.canvas.delete('all')
        self.canvas.create_image(0,0,image=self.tkimg,anchor='nw')
        self._draw_rect()
        self._draw_font_rect()
        self._draw_move_rect()
        self.canvas.config(scrollregion=(0,0,self.display_img.width,self.display_img.height))

    def _draw_frame_dimensions(self, rect, color='blue', tag='dim_frame'):
        """Prikazuje dimenzije okvira u mm kao providan tekst, uz ivice okvira."""
        self.canvas.delete(tag)
        if not rect or self.page_img is None:
            return

        x0, y0, x1, y1 = rect
        width_mm = max(0, x1 - x0) * 25.4 / 150.0
        height_mm = max(0, y1 - y0) * 25.4 / 150.0
        sx0, sy0, sx1, sy1 = [v * self.scale for v in (x0, y0, x1, y1)]
        page_w = self.display_img.width if self.display_img is not None else int(self.page_img.width * self.scale)
        page_h = self.display_img.height if self.display_img is not None else int(self.page_img.height * self.scale)
        font = ('TkDefaultFont', 9, 'bold')
        gap = 4

        # Width label: center it on the upper frame edge, outside the blue line.
        w_text = f'W: {width_mm:.1f} mm'
        w_item = self.canvas.create_text(
            (sx0 + sx1) / 2, 0, text=w_text, fill=color,
            font=font, anchor='center', tags=tag
        )
        wb = self.canvas.bbox(w_item)
        if wb:
            wh = wb[3] - wb[1]
            wy = sy0 - gap - wh / 2
            if wy - wh / 2 < 0:
                wy = sy0 + gap + wh / 2
            wy = max(wh / 2, min(page_h - wh / 2, wy))
            self.canvas.coords(w_item, max(0, min(page_w, (sx0 + sx1) / 2)), wy)

        # Height label: keep its full text outside the vertical blue edge.
        h_text = f'H: {height_mm:.1f} mm'
        h_item = self.canvas.create_text(
            0, (sy0 + sy1) / 2, text=h_text, fill=color,
            font=font, anchor='center', tags=tag
        )
        hb = self.canvas.bbox(h_item)
        if hb:
            hw = hb[2] - hb[0]
            hh = hb[3] - hb[1]
            if sx0 >= hw + gap:
                hx = sx0 - gap - hw / 2
            elif page_w - sx1 >= hw + gap:
                hx = sx1 + gap + hw / 2
            else:
                # If neither side has room, place it just inside the frame edge.
                hx = sx0 + gap + hw / 2
            hy = (sy0 + sy1) / 2
            hy = max(hh / 2, min(page_h - hh / 2, hy))
            self.canvas.coords(h_item, max(hw / 2, min(page_w - hw / 2, hx)), hy)

    def _draw_extended_guides(self, rect, color, tag, dash=None):
        """Draw crosshair guide lines from a selection to the page edges."""
        self.canvas.delete(tag)
        if not rect or self.page_img is None:
            return
        x0, y0, x1, y1 = [v * self.scale for v in rect]
        page_w = self.display_img.width if self.display_img is not None else int(self.page_img.width * self.scale)
        page_h = self.display_img.height if self.display_img is not None else int(self.page_img.height * self.scale)
        options = {'fill': color, 'width': 2, 'tags': tag}
        if dash:
            options['dash'] = dash
        self.canvas.create_line(x0, 0, x0, page_h, **options)
        self.canvas.create_line(x1, 0, x1, page_h, **options)
        self.canvas.create_line(0, y0, page_w, y0, **options)
        self.canvas.create_line(0, y1, page_w, y1, **options)

    def _draw_rect(self):
        self.canvas.delete('sel')
        self.canvas.delete('dim_sel')
        self.canvas.delete('old_guides')
        if self.rect:
            x0,y0,x1,y1=[v*self.scale for v in self.rect]
            self._draw_extended_guides(self.rect, 'red', 'old_guides')
            self.canvas.create_rectangle(x0,y0,x1,y1,outline='red',width=2,tags='sel')
            self._draw_frame_dimensions(self.rect, color='red', tag='dim_sel')

    def _draw_font_rect(self):
        self.canvas.delete('font_sel')
        self.canvas.delete('dim_font')
        self.canvas.delete('font_guides')
        if self.font_rect:
            x0,y0,x1,y1=[v*self.scale for v in self.font_rect]
            self._draw_extended_guides(self.font_rect, 'green', 'font_guides')
            self.canvas.create_rectangle(x0,y0,x1,y1,outline='green',width=2,tags='font_sel')
            self._draw_frame_dimensions(self.font_rect, color='green', tag='dim_font')

    def _img_point(self,e):
        cx=self.canvas.canvasx(e.x); cy=self.canvas.canvasy(e.y)
        src=self._current_view_source() or self.page_img
        x=max(0,min(src.width,int(cx/self.scale)))
        y=max(0,min(src.height,int(cy/self.scale)))
        return x,y

    def _detect_selected_text(self):
        """Read the selected old-data area only for identification."""
        if not self.rect: return ''
        src=self._current_view_source() or self.page_img
        crop=src.crop(self.rect).convert('RGB')
        vals=[]
        for psm in (7,8,6):
            try:
                txt=pytesseract.image_to_string(crop, lang='srp_latn+eng', config=f'--psm {psm}').strip()
            except Exception:
                txt=''
            txt=' '.join(txt.split())
            if txt: vals.append(txt)
        if vals:
            # Prefer the shortest clean Tesseract result for a single selected datum.
            vals=sorted(set(vals), key=lambda x:(len(x), x))
            return vals[0]
        # V33 fallback: neural OCR similar to OCR engines used in modern
        # camera/translation applications. It runs locally after installation.
        return _rapidocr_text(crop)

    def set_mode(self,m):
        self.mode=m
        self.paste_target=None
        self.canvas.delete('paste_target')
        self.canvas.delete('drag')
        self.canvas.delete('dim_drag')
        # Remove guides/measurements from the previous mode; the active
        # selection renderer below will redraw only its own overlays.
        for overlay_tag in ('old_guides', 'font_guides', 'add_text_guides',
                            'dim_sel', 'dim_font', 'dim_addtext', 'dim_move'):
            self.canvas.delete(overlay_tag)
        self.move_action=None; self.transform_base=None; self.transform_src_rect=None
        if m=='idle':
            # V24: dok korisnik ne izabere režim, klik/prevlačenje ne sme da pravi okvir.
            self.canvas.delete('sel'); self.canvas.delete('move_sel'); self.canvas.delete('font_sel'); self.canvas.delete('add_text_sel')
            self.canvas.config(cursor='arrow')
            self.info.set('Open a PDF. To replace content, use “Select Original Item”; to move content, use “Move Items”; to add text, use “Add Text”.')
        elif m=='old':
            # V19: crveni okvir i zamena ostaju potpuno nepromenjeni.
            self.canvas.config(cursor='crosshair')
            self.canvas.delete('move_sel')
            self._draw_rect()
            self.info.set('Select the entire ORIGINAL ITEM with the red rectangle.')
        elif m=='move':
            # V66: klik na „Pomeranje podataka“ uvek vraća STANDARDNI PLAVI
            # okvir sa četiri ručice. Sivi isprekidani okvir je privremen
            # samo za rad u režimu dodavanja/izmene teksta i ne ostaje aktivan
            # kada korisnik pređe na pomeranje. Podaci o dodatom tekstu
            # (added_text_info) ostaju sačuvani radi kasnije izmene.
            self.canvas.config(cursor='crosshair')
            self.canvas.delete('sel')
            self.canvas.delete('drag')
            self.canvas.delete('move_sel')
            self.canvas.delete('move_handle')
            self.canvas.delete('add_text_sel')
            self.add_text_point=None
            self._draw_move_rect()
            self.info.set('MOVE MODE: the BLUE frame with four handles is active. Drag it or use the arrow keys.')
        elif m=='addtext':
            self.canvas.config(cursor='crosshair')
            self.canvas.delete('sel'); self.canvas.delete('move_sel'); self.canvas.delete('font_sel'); self.canvas.delete('move_handle')
            self._draw_add_text_rect()
            self.info.set('ADD TEXT: click where you want to place the new text. After adding, it remains inside a gray dashed frame. To move it, click “Move Items”.')
        elif m=='font':
            self.canvas.config(cursor='crosshair')
            self.canvas.delete('sel'); self.canvas.delete('move_sel'); self.canvas.delete('font_sel')
            self._draw_font_rect()
            self.info.set('GREEN FRAME: select the text you want to compare. When you release the mouse, the font preview window opens automatically.')
        elif m=='missing':
            self.canvas.config(cursor='crosshair')
            ch=self.missing[self.missing_i]
            self._draw_rect()
            self.info.set(f'Missing snapshot for character “{ch}”. Select that character only; when you release the mouse, the program captures it and continues.')

    def _move_selection_hit(self,e):
        if not self.move_rect or self.mode!='move':
            return None
        x,y=self._img_point(e)
        x0,y0,x1,y1=self.move_rect
        # V43: ugaone ručice služe ISKLJUČIVO za ručnu promenu veličine.
        # Prag je vezan za veličinu ručice na ekranu, pa ostaje lako klikabilan pri zoom-u.
        r=max(5.0, 7.0/max(self.scale,0.01))
        handles={
            'nw':(x0,y0), 'ne':(x1,y0),
            'sw':(x0,y1), 'se':(x1,y1),
        }
        for name,(hx,hy) in handles.items():
            if abs(x-hx)<=r and abs(y-hy)<=r:
                return name
        if x0<=x<=x1 and y0<=y<=y1:
            return 'move'
        return None

    def _draw_add_text_rect(self):
        """V66: dodat tekst je privremeno označen sivim isprekidanim okvirom.
        Tek klikom na „Pomeranje podataka“ prelazi u standardni plavi okvir.
        """
        self.canvas.delete('add_text_sel')
        self.canvas.delete('dim_addtext')
        self.canvas.delete('add_text_guides')
        if not self.move_rect:
            return
        x0,y0,x1,y1=[v*self.scale for v in self.move_rect]
        self._draw_extended_guides(self.move_rect, 'gray', 'add_text_guides', dash=(6,4))
        self.canvas.create_rectangle(
            x0,y0,x1,y1,
            outline='gray', width=2, dash=(6,4),
            tags='add_text_sel'
        )
        self._draw_frame_dimensions(self.move_rect, color='gray', tag='dim_addtext')

    def _draw_move_rect(self):
        self.canvas.delete('move_sel')
        self.canvas.delete('move_handle')
        self.canvas.delete('dim_move')
        if not self.move_rect:
            return
        # V66: kada je aktivan režim Pomeranje podataka, okvir je UVEK PLAV,
        # uključujući i dodat tekst. Sivi isprekidani okvir više se ne koristi
        # za aktivnu selekciju u ovom režimu.
        x0,y0,x1,y1=[v*self.scale for v in self.move_rect]

        # V84: plavi okvir za pomeranje prikazuje produžene linije do ivica
        # cele stranice dokumenta, kao pomoć pri preciznom poravnanju.
        page_w=self.display_img.width if self.display_img is not None else int(self.page_img.width*self.scale)
        page_h=self.display_img.height if self.display_img is not None else int(self.page_img.height*self.scale)
        self.canvas.create_line(x0,0,x0,page_h,fill='blue',width=2,tags='move_sel')
        self.canvas.create_line(x1,0,x1,page_h,fill='blue',width=2,tags='move_sel')
        self.canvas.create_line(0,y0,page_w,y0,fill='blue',width=2,tags='move_sel')
        self.canvas.create_line(0,y1,page_w,y1,fill='blue',width=2,tags='move_sel')
        self._draw_frame_dimensions(self.move_rect, color='blue', tag='dim_move')

        handle_color='blue'
        hs=5
        for hx,hy in ((x0,y0),(x1,y0),(x0,y1),(x1,y1)):
            self.canvas.create_rectangle(hx-hs,hy-hs,hx+hs,hy+hs,
                                         outline=handle_color,fill='white',width=1,tags='move_handle')

    def _snapshot_alpha(self,snap):
        a=np.array(snap.convert('RGB'))
        gray=cv2.cvtColor(a,cv2.COLOR_RGB2GRAY).astype(np.float32)
        bg=float(np.percentile(gray,98))
        alpha=np.clip((bg-gray)*9.0,0,255).astype(np.uint8)
        alpha[gray>=bg-1]=0
        rgba=np.dstack([a,alpha]).astype(np.uint8)
        return Image.fromarray(rgba,'RGBA')

    def _erase(self,base,rect):
        arr=np.array(base.convert('RGB'))
        x0,y0,x1,y1=rect
        pad=max(3,int(min(x1-x0,y1-y0)*0.22))
        xa=max(0,x0-pad); ya=max(0,y0-pad); xb=min(base.width,x1+pad); yb=min(base.height,y1+pad)
        ring=arr[ya:yb,xa:xb].copy()
        mask=np.ones(ring.shape[:2],dtype=bool)
        mask[y0-ya:y1-ya,x0-xa:x1-xa]=False
        vals=ring[mask]
        bg=tuple(np.median(vals,axis=0).astype(np.uint8)) if len(vals) else (255,255,255)
        patch=Image.new('RGB',(x1-x0,y1-y0),bg)
        base.paste(patch,(x0,y0))
        return base

    def _transform_image(self,base,src_rect,dst_rect):
        x0,y0,x1,y1=src_rect
        dx0,dy0,dx1,dy1=dst_rect
        crop=base.crop((x0,y0,x1,y1)).convert('RGB')
        rgba=self._snapshot_alpha(crop)
        nw=max(1,dx1-dx0); nh=max(1,dy1-dy0)
        if rgba.size != (nw,nh):
            rgba=rgba.resize((nw,nh),Image.Resampling.LANCZOS)
        out=base.copy().convert('RGBA')
        out=self._erase(out,src_rect)
        out.alpha_composite(rgba,(dx0,dy0))
        return out.convert('RGB')

    def _show_move_transform(self):
        if self.transform_base is None or self.transform_src_rect is None or not self.move_rect:
            return
        preview=self._transform_image(self.transform_base,self.transform_src_rect,self.move_rect)
        self.show_image(preview,keep_scale=True)
        self._draw_move_rect()

    def on_press(self,e):
        if self.page_img is None:return
        self.last_click_point=self._img_point(e)
        if self.mode=='paste_target':
            self.paste_target=self.last_click_point
            self.canvas.delete('paste_target')
            x,y=self.paste_target
            r=7
            self.canvas.create_oval((x-r)*self.scale,(y-r)*self.scale,(x+r)*self.scale,(y+r)*self.scale,outline='purple',width=2,tags='paste_target')
            self.info.set(f'Paste location selected: ({x}, {y}). Now click “Paste”.')
            return
        if self.mode=='addtext':
            self.add_text_point=self._img_point(e)
            return
        if self.mode=='font':
            self.drag_start=self._img_point(e)
            self._drag_current=self.drag_start
            return
        if self.mode=='move':
            hit=self._move_selection_hit(e)
            if hit:
                src=self._current_view_source() or self.page_img
                self.transform_base=src.copy()
                self.transform_src_rect=tuple(self.move_rect)
                # 'move' = pomeranje; nw/ne/sw/se = ručna promena veličine.
                self.move_action=hit
                self.move_anchor=self._img_point(e)
                self.move_orig_rect=tuple(self.move_rect)
                return
            self.move_action='new'
            self.drag_start=self._img_point(e)
            self._drag_current=self.drag_start
            return
        # V19 original selection behavior follows unchanged.
        self.drag_start=self._img_point(e)
        self._drag_current=self.drag_start

    def on_drag(self,e):
        if self.mode=='font':
            if not self.drag_start:return
            x,y=self._img_point(e); x0,y0=self.drag_start
            self._drag_current=(x,y)
            self.canvas.delete('drag')
            drag_rect=(min(x0,x),min(y0,y),max(x0,x),max(y0,y))
            self._draw_extended_guides(drag_rect, 'green', 'drag')
            self.canvas.create_rectangle(x0*self.scale,y0*self.scale,x*self.scale,y*self.scale,outline='green',width=2,tags='drag')
            self._draw_frame_dimensions(drag_rect, color='green', tag='dim_drag')
            return
        if self.mode=='move':
            if self.move_action in ('move','nw','ne','sw','se') and self.move_orig_rect:
                x,y=self._img_point(e); ox,oy=self.move_anchor
                x0,y0,x1,y1=self.move_orig_rect
                if self.move_action=='move':
                    dx=x-ox; dy=y-oy; w=x1-x0; h=y1-y0
                    nx0=max(0,min(self.page_img.width-w,x0+dx)); ny0=max(0,min(self.page_img.height-h,y0+dy))
                    self.move_rect=(int(nx0),int(ny0),int(nx0+w),int(ny0+h))
                else:
                    nx0,ny0,nx1,ny1=x0,y0,x1,y1
                    if self.move_action in ('nw','sw'): nx0=x
                    if self.move_action in ('ne','se'): nx1=x
                    if self.move_action in ('nw','ne'): ny0=y
                    if self.move_action in ('sw','se'): ny1=y
                    minsize=3
                    if nx1-nx0<minsize:
                        if self.move_action in ('nw','sw'): nx0=nx1-minsize
                        else: nx1=nx0+minsize
                    if ny1-ny0<minsize:
                        if self.move_action in ('nw','ne'): ny0=ny1-minsize
                        else: ny1=ny0+minsize
                    nx0=max(0,min(nx0,self.page_img.width-minsize)); nx1=max(minsize,min(nx1,self.page_img.width))
                    ny0=max(0,min(ny0,self.page_img.height-minsize)); ny1=max(minsize,min(ny1,self.page_img.height))
                    self.move_rect=(int(min(nx0,nx1)),int(min(ny0,ny1)),int(max(nx0,nx1)),int(max(ny0,ny1)))
                self._show_move_transform()
                return
            if self.move_action=='new' and self.drag_start:
                x,y=self._img_point(e); x0,y0=self.drag_start
                self._drag_current=(x,y)
                self.canvas.delete('drag')
                drag_rect=(min(x0,x),min(y0,y),max(x0,x),max(y0,y))
                self._draw_extended_guides(drag_rect, 'blue', 'drag')
                self.canvas.create_rectangle(x0*self.scale,y0*self.scale,x*self.scale,y*self.scale,outline='blue',width=2,tags='drag')
                self._draw_frame_dimensions(drag_rect, color='blue', tag='dim_drag')
            return
        # V19 original red selection drawing.
        if not self.drag_start:return
        x,y=self._img_point(e); x0,y0=self.drag_start
        self._drag_current=(x,y)
        self.canvas.delete('drag')
        drag_rect=(min(x0,x),min(y0,y),max(x0,x),max(y0,y))
        self._draw_extended_guides(drag_rect, 'red', 'drag')
        self.canvas.create_rectangle(x0*self.scale,y0*self.scale,x*self.scale,y*self.scale,outline='red',width=2,tags='drag')
        self._draw_frame_dimensions(drag_rect, color='red', tag='dim_drag')

    def _commit_move_transform(self):
        if self.transform_base is None or self.transform_src_rect is None or not self.move_rect:return False
        if tuple(self.move_rect)==tuple(self.transform_src_rect):
            self.show_image(self.transform_base,keep_scale=True)
            self._draw_move_rect()
            return False
        previous=self.result.copy() if self.result is not None else self.page_img.copy()
        final=self._transform_image(self.transform_base,self.transform_src_rect,self.move_rect)
        self.undo_stack.append(previous); self.redo_stack.clear(); self.result=final
        if self.added_text_info is not None and tuple(self.added_text_info.get('rect',()))==tuple(self.transform_src_rect):
            self.added_text_info['rect']=tuple(self.move_rect)
        self.show_image(final,keep_scale=True)
        self._draw_move_rect()
        self.info.set('The item was moved/resized. The blue frame remains active.')
        return True

    def on_release(self,e):
        if self.mode=='paste_target':
            return
        if self.mode=='addtext':
            if self.add_text_point is None:
                return
            x,y=self.add_text_point
            self.add_text_point=None
            self._add_text_dialog(x,y)
            return
        if self.mode=='font':
            if not self.drag_start:return
            x0,y0=self.drag_start; x1,y1=self._img_point(e)
            self.drag_start=None; self.canvas.delete('drag'); self.canvas.delete('dim_drag')
            x0,x1=sorted((x0,x1)); y0,y1=sorted((y0,y1))
            if x1-x0<2 or y1-y0<2:return
            self.font_rect=(x0,y0,x1,y1)
            self._draw_font_rect()
            if self.font_action=='preview':
                self.show_font_preview_from_selection()
            else:
                self.detect_font_size()
            return
        if self.mode=='move':
            if self.move_action in ('move','nw','ne','sw','se'):
                self._commit_move_transform()
                self.move_action=None; self.move_anchor=None; self.move_orig_rect=None
                self.transform_base=None; self.transform_src_rect=None
                self._draw_move_rect(); return
            if self.move_action!='new' or not self.drag_start:return
            x0,y0=self.drag_start; x1,y1=self._img_point(e)
            self.drag_start=None; self.move_action=None; self.canvas.delete('drag')
            x0,x1=sorted((x0,x1)); y0,y1=sorted((y0,y1))
            if x1-x0<2 or y1-y0<2:return
            self.move_rect=(x0,y0,x1,y1)
            self._draw_move_rect()
            self.info.set('The blue frame is selected. Drag inside it to move the item, or use the arrow keys. Arrow = 1 pixel; Shift + Arrow = 10 pixels.')
            return
        # V19 original release logic, verbatim in behavior.
        if not self.drag_start:return
        x0,y0=self.drag_start; x1,y1=self._img_point(e)
        self.drag_start=None; self.canvas.delete('drag'); self.canvas.delete('dim_drag')
        x0,x1=sorted((x0,x1)); y0,y1=sorted((y0,y1))
        if x1-x0<2 or y1-y0<2:return
        if self.mode=='old':
            self.rect=(x0,y0,x1,y1); self._draw_rect()
            detected=self._detect_selected_text()
            if detected:
                self.old.set(detected)
                self.info.set(f'Original item selected: „{detected}“. Click “Replace Original with New Data”.')
            else:
                self.old.set('')
                self.info.set('The original item is selected, but the program could not read it reliably. Click “Replace Original with New Data”; the program will then ask you to enter the original item.')
        elif self.mode=='missing':
            ch=self.missing[self.missing_i]
            src=self._current_view_source() or self.page_img
            snap=src.crop((x0,y0,x1,y1)).convert('RGB')
            self.char_samples.setdefault(ch,[]).append(snap)
            self.missing_i+=1
            if self.missing_i<len(self.missing):
                self.set_mode('missing')
            else:
                self.mode='old'
                self.info.set('All missing character snapshots have been captured. The program is now creating a preview automatically.')
                self.preview()

    def _selection_pdf_rect(self, rect):
        # Page is rendered at exactly 150 DPI in V25.
        k=72.0/150.0
        x0,y0,x1,y1=rect
        return fitz.Rect(x0*k,y0*k,x1*k,y1*k)

    @staticmethod
    def _rect_intersection_area(a,b):
        x0=max(a.x0,b.x0); y0=max(a.y0,b.y0)
        x1=min(a.x1,b.x1); y1=min(a.y1,b.y1)
        if x1<=x0 or y1<=y0:return 0.0
        return (x1-x0)*(y1-y0)

    def _font_size_from_scan(self, crop):
        # Kod skena prikazujemo dve različite mere:
        # 1) stvarnu visinu vidljivog znaka na papiru (mm),
        # 2) približnu nominalnu veličinu fonta (pt).
        boxes=[]
        try:
            boxes=ocr_boxes(crop)
        except Exception:
            boxes=[]
        heights=[b[4]-b[2] for b in boxes if b[4]-b[2]>=3]
        if not heights:
            try:
                a=np.array(crop.convert('RGB'))
                g=cv2.cvtColor(a,cv2.COLOR_RGB2GRAY)
                _,bw=cv2.threshold(g,210,255,cv2.THRESH_BINARY_INV)
                n,lab,stats,_=cv2.connectedComponentsWithStats(bw,8)
                heights=[int(st[3]) for st in stats[1:] if st[4]>=3 and 2<=st[3]<=max(10,crop.height*0.9)]
            except Exception:
                heights=[]
        if not heights:
            return None,None,None,None
        med=float(np.median(heights))
        mm=med*25.4/150.0
        # Direktan fizicki preračun: 1 inch = 25.4 mm = 72 pt.
        # Zato mm * 72 / 25.4 daje pt-ekvivalent izmerene visine.
        # Ovo nije isto sto i garantovana nominalna velicina fonta, ali je
        # konzistentna mera i ne uvodi dodatni kalibracioni faktor.
        pt=mm*(72.0/25.4)
        return pt,med,mm,heights

    def _system_font_files(self):
        """Return unique Windows font files with readable family names."""
        try:
            from fontTools.ttLib import TTFont
        except Exception:
            TTFont=None
        root=os.path.join(os.environ.get('WINDIR',r'C:\\Windows'),'Fonts')
        files=[]
        if not os.path.isdir(root): return files
        for base,dirs,fnames in os.walk(root):
            for fn in fnames:
                if not fn.lower().endswith(('.ttf','.otf','.ttc')): continue
                files.append(os.path.join(base,fn))
        out=[]; seen=set()
        for path in files:
            fam=None
            if TTFont:
                try:
                    tt=TTFont(path, lazy=True, fontNumber=0)
                    vals=[]
                    for n in tt['name'].names:
                        if n.nameID in (1,4):
                            try:v=n.toUnicode().strip()
                            except Exception:continue
                            if v: vals.append((n.nameID,v))
                    fam=next((v for nid,v in vals if nid==1),None) or next((v for nid,v in vals if nid==4),None)
                    tt.close()
                except Exception: pass
            if not fam:
                fam=os.path.splitext(os.path.basename(path))[0]
            key=(fam.lower(),os.path.abspath(path).lower())
            if key in seen: continue
            seen.add(key); out.append((fam,path))
        out.sort(key=lambda item: str(item[0]).casefold())
        return out

    def _normalize_ink_mask(self, img, threshold=210, target_h=None):
        """Iseci mastilo i po potrebi skaliraj SAMO po visini, bez deformisanja širine."""
        arr=np.array(img.convert('L'))
        ys,xs=np.where(arr<threshold)
        if len(xs)<5:
            return None
        x0,x1=int(xs.min()),int(xs.max()+1)
        y0,y1=int(ys.min()),int(ys.max()+1)
        crop=img.convert('L').crop((x0,y0,x1,y1))
        if target_h is not None and crop.height != int(target_h):
            nh=max(3,int(target_h))
            nw=max(1,int(round(crop.width*nh/crop.height)))
            crop=crop.resize((nw,nh),Image.Resampling.LANCZOS)
        return crop

    def _mask_similarity(self, target, rendered):
        """Poređenje bez horizontalnog razvlačenja; dozvoljen je mali pomeraj."""
        a=np.array(target.convert('L'))<210
        b=np.array(rendered.convert('L'))<210
        if a.size==0 or b.size==0: return 0.0
        h=max(a.shape[0],b.shape[0]); w=max(a.shape[1],b.shape[1])
        # Radna mreža sa marginom; centriranje zadržava stvarni odnos širina.
        H=h+12; W=w+12
        best=0.0
        for dy in range(0,7):
            for dx in range(0,7):
                ca=np.zeros((H,W),dtype=bool); cb=np.zeros((H,W),dtype=bool)
                ay=(H-a.shape[0])//2; ax=(W-a.shape[1])//2
                by=(H-b.shape[0])//2+dy-3; bx=(W-b.shape[1])//2+dx-3
                if ay>=0 and ax>=0: ca[ay:ay+a.shape[0],ax:ax+a.shape[1]]=a
                if by>=0 and bx>=0: cb[by:by+b.shape[0],bx:bx+b.shape[1]]=b
                inter=np.logical_and(ca,cb).sum(); union=np.logical_or(ca,cb).sum()
                iou=float(inter/union) if union else 0.0
                # Dice bolje reaguje na tanke poteze i razlike u konturi.
                denom=ca.sum()+cb.sum()
                dice=float(2*inter/denom) if denom else 0.0
                score=0.55*iou+0.45*dice
                if score>best: best=score
        return best

    def _render_candidate_for_match(self, path, text, target_h):
        """Nađi nominalnu veličinu koja daje target_h vidljivu visinu, bez deformisanja širine."""
        from PIL import ImageFont
        target_h=max(3,int(round(target_h)))
        best=None
        for px in range(max(5,target_h//2), max(20,target_h*5)+1):
            try:
                f=ImageFont.truetype(path,px)
                bb=f.getbbox(text)
                ih=max(1,bb[3]-bb[1]); iw=max(1,bb[2]-bb[0])
                d=abs(ih-target_h)
                if best is None or d<best[0]: best=(d,px,f,bb,iw,ih)
            except Exception:
                continue
        if best is None: return None
        _,px,f,bb,iw,ih=best
        im=Image.new('L',(max(1,iw+12),max(1,ih+12)),255)
        d=ImageDraw.Draw(im)
        d.text((6-bb[0],6-bb[1]),text,font=f,fill=0)
        tight=self._normalize_ink_mask(im,210,target_h)
        return tight,px,ih

    def _font_style_category(self, path, family=''):
        """V41: odredi praktičnu kategoriju stila fonta za filter dijalog.
        Kategorije: Regular, Bold, Italic, Bold Italic, Ostalo.
        Koristi name/filename i, kada je moguće, OS/2/head metapodatke.
        """
        try:
            from fontTools.ttLib import TTFont
            tt=TTFont(path, lazy=True, fontNumber=0)
            names=[]
            if 'name' in tt:
                for n in tt['name'].names:
                    if n.nameID in (2,4,6):
                        try:
                            v=n.toUnicode().strip()
                        except Exception:
                            v=''
                        if v: names.append(v.lower())
            sub=' '.join(names)
            bold=False; italic=False
            if 'OS/2' in tt:
                try:
                    w=int(getattr(tt['OS/2'],'usWeightClass',400) or 400)
                    bold = w >= 600
                except Exception:
                    pass
            if 'head' in tt:
                try:
                    ms=int(getattr(tt['head'],'macStyle',0) or 0)
                    bold = bold or bool(ms & 1)
                    italic = italic or bool(ms & 2)
                except Exception:
                    pass
            tt.close()
        except Exception:
            sub=''
            bold=False; italic=False

        base=(os.path.basename(path)+' '+str(family)).lower()
        alltxt=sub+' '+base
        # Italic/oblique su pouzdani indikatori za nagnuti stil.
        italic = italic or any(k in alltxt for k in ('italic','oblique','kursiv'))
        # Bold/black/heavy/demi/semibold su indikatori jačeg reza.
        bold = bold or any(k in alltxt for k in ('bold','black','heavy','demi','semibold','extrabold','ultrabold'))
        # Light/thin/medium/condensed i dekorativni rezovi idu u Ostalo,
        # osim ako eksplicitno nose Bold/Italic kombinaciju.
        other_markers=('light','thin','medium','book','condensed','narrow','expanded','display','text','hand','script','mono','semicondensed','extracondensed')
        other = any(k in alltxt for k in other_markers)
        if bold and italic:
            return 'Bold Italic'
        if bold and not other:
            return 'Bold'
        if italic and not other:
            return 'Italic'
        # Ako nema indikatora težine/nagiba, tretiramo kao Regular.
        if not bold and not italic and not other:
            return 'Regular'
        return 'Other'

    def _font_filter_dialog(self, files):
        """V41: dijalog za sužavanje liste sistemskih fontova pre rasterizacije."""
        win=tk.Toplevel(self.root)
        win.title('Filter Font Preview')
        win.transient(self.root)
        win.grab_set()
        frm=ttk.Frame(win,padding=14); frm.pack(fill='both',expand=True)
        ttk.Label(frm,text='Choose which font styles to display:',font=('Segoe UI',11,'bold')).pack(anchor='w',pady=(0,10))
        vars_={k:tk.BooleanVar(value=True) for k in ('Regular','Bold','Italic','Bold Italic','Other')}
        counts={k:0 for k in vars_}
        styled=[]
        for fam,path in files:
            cat=self._font_style_category(path,fam)
            counts[cat]=counts.get(cat,0)+1
            styled.append((fam,path,cat))
        for cat in vars_:
            ttk.Checkbutton(frm,text=f'{cat}  ({counts.get(cat,0)})',variable=vars_[cat]).pack(anchor='w',pady=2)
        ttk.Separator(frm).pack(fill='x',pady=10)
        ttk.Label(frm,text='Tip: choose Regular for normal text, Bold for bold text, Italic for italic text, and Bold Italic for bold italic text.').pack(anchor='w',fill='x')
        result=[]
        btns=ttk.Frame(frm); btns.pack(fill='x',pady=(14,0))
        def apply():
            selected={k for k,v in vars_.items() if v.get()}
            if not selected:
                messagebox.showinfo(TITLE,'Select at least one font category.',parent=win); return
            chosen=[(fam,path) for fam,path,cat in styled if cat in selected]
            chosen.sort(key=lambda item: str(item[0]).casefold())
            result.extend(chosen)
            win.destroy()
        def cancel():
            result.append(None); win.destroy()
        ttk.Button(btns,text='Show Selected Fonts',command=apply).pack(side='left')
        ttk.Button(btns,text='Cancel',command=cancel).pack(side='right')
        win.protocol('WM_DELETE_WINDOW',cancel)
        win.wait_window()
        return result[0] if result and result[0] is None else result

    def _font_preview_candidates(self, crop, text, estimated_pt):
        """V39: poredi oblik fonta bez horizontalnog razvlačenja snapshot-a.
        Za svaki font traži veličinu koja daje istu stvarnu visinu znaka, pa
        zatim poredi konturu/širinu na zajedničkoj mreži. Ovo je znatno
        korisnije za skenirane PDF-ove nego prethodno resize na istu širinu.
        """
        if not text: return []
        files=self._system_font_files()
        if not files: return []
        target=self._normalize_ink_mask(crop,210,None)
        if target is None: return []
        target_h=target.height
        scored=[]
        for fam,path in files:
            try:
                rendered=self._render_candidate_for_match(path,text,target_h)
                if rendered is None: continue
                rimg,used_px,ink_h=rendered
                score=self._mask_similarity(target,rimg)
                # Blaga kazna ako je širina bitno drugačija; NE deformišemo sliku.
                width_ratio=rimg.width/max(1,target.width)
                width_pen=min(0.20,abs(np.log(max(1e-6,width_ratio)))*0.08)
                score=max(0.0,score-width_pen)
                scored.append((score,fam,path,used_px,ink_h,rimg.width))
            except Exception:
                continue
        scored.sort(reverse=True,key=lambda x:x[0])
        result=[]; seen=set()
        for item in scored:
            key=item[1].lower()
            if key in seen: continue
            seen.add(key); result.append(item)
            if len(result)>=15: break
        return result

    def _embedded_font_file_for_resource(self, page, resource_name):
        """Vrati privremeni fajl sa ugrađenim fontom iz PDF-a, ako postoji."""
        try:
            import re, tempfile
            entry=None
            for f in page.get_fonts(full=True):
                if len(f) >= 5 and (f[3] == resource_name or f[4] == resource_name):
                    entry=f; break
            if not entry:
                return None
            xref=int(entry[0])
            desc_info=self.doc.xref_get_key(xref,'DescendantFonts')
            if not desc_info or len(desc_info)<2:
                return None
            desc_text=str(desc_info[1])
            m=re.search(r'/FontFile2 (\d+) 0 R', desc_text) or re.search(r'/FontFile (\d+) 0 R', desc_text)
            if not m:
                refs=re.findall(r'(\d+) 0 R', desc_text)
                for ref in refs:
                    try:
                        obj=self.doc.xref_object(int(ref), compressed=False)
                    except Exception:
                        continue
                    m=re.search(r'/FontFile2 (\d+) 0 R', obj) or re.search(r'/FontFile (\d+) 0 R', obj)
                    if m: break
            if not m:
                return None
            data=self.doc.xref_stream(int(m.group(1)))
            if not data:
                return None
            suffix='.ttf' if b'OTTO' not in data[:4] else '.otf'
            fd,path=tempfile.mkstemp(prefix='pdf_font_',suffix=suffix)
            os.close(fd)
            with open(path,'wb') as fh: fh.write(data)
            return path
        except Exception:
            return None

    def _tight_text_crop(self, crop, threshold=225, pad=0):
        """Vrati samo stvarni sadržaj teksta, bez viška bele površine."""
        snap=crop.convert('RGB')
        arr=np.array(snap)
        gray=np.mean(arr,axis=2)
        ys,xs=np.where(gray<threshold)
        if len(xs)<=5:
            return snap
        x0=max(0,int(xs.min())-pad); y0=max(0,int(ys.min())-pad)
        x1=min(snap.width,int(xs.max())+1+pad); y1=min(snap.height,int(ys.max())+1+pad)
        return snap.crop((x0,y0,x1,y1))

    def _render_font_at_ink_height(self, path, text, target_h, max_width=900):
        """Render font tako da vidljiva visina slova bude približno target_h piksela."""
        from PIL import ImageFont
        target_h=max(3,int(round(target_h)))
        best=None
        # Pretraga nominalne veličine; važna je stvarna visina glifa, ne pt broj.
        for px in range(max(5,target_h//2), max(18,target_h*4)+1):
            try:
                f=ImageFont.truetype(path,px)
                bb=f.getbbox(text)
                ink_h=max(1,bb[3]-bb[1]); ink_w=max(1,bb[2]-bb[0])
                diff=abs(ink_h-target_h)
                item=(diff,px,f,bb,ink_w,ink_h)
                if best is None or item[0]<best[0]: best=item
            except Exception:
                continue
        if best is None: return None
        _,px,f,bb,ink_w,ink_h=best
        w=min(max_width,max(80,ink_w+30)); h=max(40,ink_h+28)
        im=Image.new('RGB',(w,h),'white')
        d=ImageDraw.Draw(im)
        d.text((15-bb[0],14-bb[1]),text,font=f,fill='black')
        return im,px,ink_h

    def _text_pdf_preview_args(self, page, rect):
        """V62: tekstualni PDF obrađuje se isključivo preko PDF tekstualnog sloja.
        OCR se ovde nikada ne poziva. Ako rawdict nema chars, koristi se
        get_text("dict") + get_text("words") kao pouzdanija rezerva.
        """
        v63_log('=== TEXT-PDF DIJAGNOSTIKA V62 ===')
        v63_log('TEXT-PDF: selekcija image rect=' + repr(rect))
        sel=self._selection_pdf_rect(rect)
        v63_log('TEXT-PDF: selekcija PDF rect=' + repr(tuple(sel)))

        # 1) Ne zaključuj da je PDF sken samo zato što get_text('text')
        #    vraća prazno. Kod pojedinih generisanih PDF-ova jedan extractor
        #    može biti prazan dok drugi i dalje vidi fontove/znakove.
        plain=page.get_text('text') or ''
        dict_data=page.get_text('dict') or {}
        words=page.get_text('words') or []
        raw=page.get_text('rawdict') or {}
        v61_blocks=len(dict_data.get('blocks',[]))
        v61_text_blocks=sum(1 for b in dict_data.get('blocks',[]) if b.get('type')==0)
        v61_spans=sum(len(line.get('spans',[])) for b in dict_data.get('blocks',[]) if b.get('type')==0 for line in b.get('lines',[]))
        v61_raw_blocks=len(raw.get('blocks',[]))
        v63_log('TEXT-PDF: page=' + str(self.page_index+1) + ' | text_len=' + str(len(plain)) + ' | words=' + str(len(words)) + ' | dict_blocks=' + str(v61_blocks) + ' | text_blocks=' + str(v61_text_blocks) + ' | spans=' + str(v61_spans) + ' | raw_blocks=' + str(v61_raw_blocks))
        v63_log('TEXT-PDF: text uzorak=' + repr(plain[:300]))

        # 2) Char-level rawdict.
        raw_chars=[]
        for bi,block in enumerate(raw.get('blocks',[])):
            for li,line in enumerate(block.get('lines',[])):
                for si,span in enumerate(line.get('spans',[])):
                    for ci,ch in enumerate(span.get('chars') or []):
                        c=str(ch.get('c',''))
                        bb=fitz.Rect(ch.get('bbox',(0,0,0,0)))
                        raw_chars.append((bb,c,str(span.get('font','')),float(span.get('size',0) or 0),bi,li,si,ci))
        v63_log('TEXT-PDF: rawdict karaktera=' + str(len(raw_chars)))

        selected=[]
        for item in raw_chars:
            bb=item[0]
            inter=self._rect_intersection_area(sel,bb)
            if inter <= 0: continue
            cx=(bb.x0+bb.x1)/2.0; cy=(bb.y0+bb.y1)/2.0
            if sel.contains(fitz.Point(cx,cy)) or inter/max(1e-9,bb.width*bb.height)>=0.20:
                selected.append(item)

        if selected:
            # Grupisanje po približnoj liniji; zatim X. Ovo je vizuelni redosled,
            # a ne redosled kojim je proizvođač PDF-a zapisao glifove.
            selected.sort(key=lambda z:(round(z[0].y0,1),z[0].x0))
            v63_log('TEXT-PDF: RAW izabrani=' + repr([(x[1],round(x[0].x0,2),round(x[0].y0,2),x[2],x[3]) for x in selected]))
            lines=[]
            for it in selected:
                bb,c,font,size,*_=it
                placed=False
                for ln in lines:
                    if abs(bb.y0-ln['y']) <= max(2.0,bb.height*0.45):
                        ln['items'].append(it); placed=True; break
                if not placed:
                    lines.append({'y':bb.y0,'items':[it]})
            for ln in lines: ln['items'].sort(key=lambda z:z[0].x0)
            lines.sort(key=lambda ln:ln['y'])
            parts=[]
            for ln in lines:
                chars=[x[1] for x in ln['items']]
                # Ne ubacuj razmak između karaktera koji ga nemaju u PDF-u;
                # razmak koji je stvarno zaseban char ostaje.
                parts.append(''.join(chars))
            best_text='\n'.join(parts).strip()
            best_item=max(selected,key=lambda x:self._rect_intersection_area(sel,x[0]))
            best_font=best_item[2]; best_size=best_item[3]
            v63_log('TEXT-PDF: SORTIRANI redovi=' + repr(parts))
            v63_log('TEXT-PDF: KRAJNJI tekst za fontove=' + repr(best_text))
            v63_log('TEXT-PDF: font=' + repr(best_font) + ' size=' + repr(best_size))
            crop=self.page_img.crop(rect).convert('RGB')
            real=_font_name_from_embedded_ttf(self.doc,page,best_font)
            label=_clean_embedded_name(real or best_font)
            exact_path=self._embedded_font_file_for_resource(page,best_font)
            if exact_path is None:
                for fam,path in self._system_font_files():
                    if fam.lower()==label.lower(): exact_path=path; break
            mm=best_size*25.4/72.0
            return crop,best_text,best_size,mm,None,exact_path,label

        # 3) rawdict kod nekih generisanih PDF-ova nema chars, iako dict/words
        # imaju tekst. Zato koristimo words kao rezervu, bez ikakvog OCR-a.
        v63_log('TEXT-PDF: get_text(words) ukupno=' + str(len(words)))
        selected_words=[]
        for w in words:
            if len(w)<5: continue
            bb=fitz.Rect(w[0],w[1],w[2],w[3])
            inter=self._rect_intersection_area(sel,bb)
            if inter<=0: continue
            cx=(bb.x0+bb.x1)/2; cy=(bb.y0+bb.y1)/2
            if sel.contains(fitz.Point(cx,cy)) or inter/max(1e-9,bb.width*bb.height)>=0.20:
                selected_words.append((bb,str(w[4]),int(w[5]) if len(w)>5 else 0,int(w[6]) if len(w)>6 else 0,int(w[7]) if len(w)>7 else 0))
        selected_words.sort(key=lambda z:(z[0].y0,z[0].x0))
        v63_log('TEXT-PDF: selektovane WORDS=' + repr([(w[1],tuple(round(v,2) for v in w[0])) for w in selected_words]))
        if not selected_words:
            # Važno: ovo je i dalje TEXT-PDF putanja. Ne vraćamo OCR jer je
            # utvrđeno da tekstualni sloj postoji; samo nema ništa u selekciji.
            v63_log('TEXT PDF: extractors found text, but the selection did not cover any words.')
            return None

        # Nađi span/font koji prostorno pokriva najveći deo izabrane reči.
        d=page.get_text('dict')
        spans=[]
        for block in d.get('blocks',[]):
            for line in block.get('lines',[]):
                for span in line.get('spans',[]):
                    bb=fitz.Rect(span.get('bbox',(0,0,0,0)))
                    spans.append((bb,str(span.get('font','')),float(span.get('size',0) or 0),str(span.get('text',''))))
        def span_for_word(bb):
            hits=[]
            for sp in spans:
                a=self._rect_intersection_area(bb,sp[0])
                if a>0: hits.append((a,sp))
            return max(hits,key=lambda x:x[0])[1] if hits else None

        text_parts=[]; best=None
        for w in selected_words:
            text_parts.append(w[1])
            sp=span_for_word(w[0])
            if sp:
                area=self._rect_intersection_area(sel,sp[0])
                if best is None or area>best[0]: best=(area,sp)
        best_text=' '.join(text_parts).strip()
        if best is None:
            best_font=''; best_size=0; label=''; exact_path=None
        else:
            best_font=best[1][1]; best_size=best[1][2]
            real=_font_name_from_embedded_ttf(self.doc,page,best_font)
            label=_clean_embedded_name(real or best_font)
            exact_path=self._embedded_font_file_for_resource(page,best_font)
            if exact_path is None:
                for fam,path in self._system_font_files():
                    if fam.lower()==label.lower(): exact_path=path; break
        v63_log('TEXT-PDF: WORDS SORTIRANI=' + repr(text_parts))
        v63_log('TEXT-PDF: KRAJNJI tekst za fontove=' + repr(best_text))
        v63_log('TEXT-PDF: font=' + repr(best_font) + ' size=' + repr(best_size))
        crop=self.page_img.crop(rect).convert('RGB')
        mm=best_size*25.4/72.0 if best_size else 0
        return crop,best_text,best_size,mm,None,exact_path,label

    def _show_font_preview(self, crop, text, estimated_pt, mm, guessed=None, exact_font_path=None, exact_font_label=None):
        v63_log('PREVIEW: tekst primljen=' + repr(text) + ' | pt=' + repr(estimated_pt) + ' | mm=' + repr(mm) + ' | exact_font=' + repr(exact_font_label))
        """V40: jednostavan vizuelni katalog fontova.
        Levo je isti selektovani tekst ispisan u fontu, a desno originalni
        snapshot u stvarnoj veličini selekcije. Kod ugrađenog PDF fonta
        prikazuje se samo taj font. Kod skena prikazuju se svi sistemski fontovi.
        """
        try:
            if not text:
                text=self._detect_selected_text_from_crop(crop)
            if not text:
                messagebox.showinfo(TITLE,'The program could not read the text. Select one short word or a few characters in the same font.')
                return

            # Originalni snapshot: samo sadržaj selekcije, bez proizvoljnog uvećanja.
            snap=self._tight_text_crop(crop,225,0).convert('RGB')
            snap_w,snap_h=snap.size
            original_snap_w, original_snap_h = snap_w, snap_h
            # Ako je snapshot ogroman, samo ga smanji da stane u red; ne uvećavaj ga.
            max_snap_w,max_snap_h=520,110
            r=min(1.0,max_snap_w/max(1,snap_w),max_snap_h/max(1,snap_h))
            if r<1:
                snap=snap.resize((max(1,int(snap_w*r)),max(1,int(snap_h*r))),Image.Resampling.LANCZOS)

            # Kandidati: ugrađeni font iz PDF-a = samo taj font.
            if exact_font_path and exact_font_label:
                candidates=[(exact_font_label,exact_font_path,True)]
            elif exact_font_label:
                # Ako PDF zna ime fonta, ali nema ugrađen fajl, pronađi isto ime u Windows fontovima.
                found=None
                for fam,path in self._system_font_files():
                    if fam.lower()==str(exact_font_label).lower():
                        found=(fam,path); break
                candidates=[(found[0],found[1],True)] if found else [(str(exact_font_label),None,True)]
            else:
                # Skenirani PDF: prvo pitaj korisnika koje stilove želi da vidi,
                # pa tek onda rasterizuj izabrane fontove. Ovo sprečava usporenje
                # i nepotrebno listanje velikog broja fontova.
                all_files=self._system_font_files()
                if not all_files:
                    messagebox.showinfo(TITLE,'No fonts were found in the Windows Fonts folder.')
                    return
                filtered=self._font_filter_dialog(all_files)
                if filtered is None:
                    return
                candidates=[(fam,path,False) for fam,path in filtered]

            if not candidates:
                messagebox.showinfo(TITLE,'No fonts were selected for display.')
                return

            # Visinu kandidata uzimamo iz stvarnog sadržaja selekcije, a ne iz
            # pune visine zelenog okvira. Ovo je naročito važno kada je selektovano
            # više reči ili kada je okvir viši od samih slova.
            target_h=max(3, min(140, int(original_snap_h)))

            win=tk.Toplevel(self.root)
            win.title('Show Fonts – Visual Comparison')
            win.transient(self.root)
            # V54: širina prozora i kolona prilagođavaju se dužini selektovanog teksta.
            # Ne smanjujemo font samo da bi stao u fiksnu kolonu.
            char_hint=max(12, len(str(text)))
            desired_mid=min(1100, max(520, int(char_hint*14)))
            desired_snap=min(520, max(300, snap_w+20))
            screen_w=max(1100, int(win.winfo_screenwidth()-60))
            desired_win_w=min(screen_w, max(1180, 220+desired_mid+desired_snap+120))
            win.geometry(f'{desired_win_w}x820')
            win.minsize(1000,600)

            ttk.Label(win,text='Font Visual Comparison',font=('Segoe UI',13,'bold')).pack(anchor='w',padx=12,pady=(10,4))
            info=ttk.Frame(win)
            info.pack(fill='x',padx=12,pady=(0,8))
            ttk.Label(info,text=f'Recognized text: {text}',font=('Segoe UI',11,'bold')).pack(side='left',padx=(0,18))
            if estimated_pt is not None:
                ttk.Label(info,text=f'Character height: {mm:.2f} mm   |   approximate size: {estimated_pt:.2f} pt').pack(side='left')
            else:
                ttk.Label(info,text=f'Character height: {mm:.2f} mm').pack(side='left')

            ttk.Label(win,text='For scanned PDFs, only the selected font categories are shown. Each row displays the text in that font, with the original snapshot at its original size on the right. Compare the shapes of the letters and digits visually.',wraplength=max(900, desired_win_w-100)).pack(anchor='w',padx=12,pady=(0,8))

            outer=ttk.Frame(win); outer.pack(fill='both',expand=True,padx=10,pady=4)
            outer.rowconfigure(0,weight=1); outer.columnconfigure(0,weight=1)
            canvas=tk.Canvas(outer,background='#eeeeee',highlightthickness=0)
            sb=ttk.Scrollbar(outer,orient='vertical',command=canvas.yview)
            hsb=ttk.Scrollbar(outer,orient='horizontal',command=canvas.xview)
            canvas.configure(yscrollcommand=sb.set,xscrollcommand=hsb.set)
            canvas.grid(row=0,column=0,sticky='nsew')
            sb.grid(row=0,column=1,sticky='ns')
            hsb.grid(row=1,column=0,sticky='ew')
            inner=ttk.Frame(canvas); wid=canvas.create_window((0,0),window=inner,anchor='nw')
            def cfg(e=None):
                # Ne forsiramo širinu unutrašnjeg Frame-a na širinu canvasa.
                # Time Tkinter može da sabije/skrati sadržaj kod dugih selekcija.
                canvas.configure(scrollregion=canvas.bbox('all'))
            inner.bind('<Configure>',cfg)

            # V42: točkić miša skroluje listu fontova gore/dole.
            # Vežemo događaj i na sve trenutno postojeće pod-widgete dijaloga,
            # jer se kursor najčešće nalazi iznad Label/Frame elemenata, a ne
            # direktno iznad Canvas-a.
            def font_wheel(e):
                if e.num == 4 or e.delta > 0:
                    canvas.yview_scroll(-3, 'units')
                else:
                    canvas.yview_scroll(3, 'units')
                return 'break'

            def bind_font_wheel(widget):
                try:
                    widget.bind('<MouseWheel>', font_wheel)
                    widget.bind('<Button-4>', font_wheel)
                    widget.bind('<Button-5>', font_wheel)
                except Exception:
                    pass
                for child in widget.winfo_children():
                    bind_font_wheel(child)

            bind_font_wheel(win)
            refs=[]
            win._font_preview_refs=refs

            for i,(fam,path,is_exact) in enumerate(candidates,1):
                row=ttk.Frame(inner,relief='solid',borderwidth=1,padding=7)
                row.pack(fill='x',padx=4,pady=3)
                left=ttk.Frame(row,width=210); left.pack(side='left',fill='y',padx=(2,10)); left.pack_propagate(True)
                mid=ttk.Frame(row,width=desired_mid); mid.pack(side='left',fill='both',expand=False,padx=(0,12)); mid.pack_propagate(True)
                right=ttk.Frame(row,width=desired_snap); right.pack(side='left',fill='both',expand=False,padx=(4,2)); right.pack_propagate(True)

                label=f'{i}. {fam}' + ('   [EMBEDDED PDF FONT]' if is_exact else '')
                ttk.Label(left,text=label,font=('Segoe UI',10,'bold'),wraplength=200).pack(anchor='nw')

                try:
                    if path is None:
                        raise RuntimeError('Font file not found')
                    rendered=self._render_font_at_ink_height(path,text,target_h,max_width=max(1400, desired_mid))
                    if rendered is None:
                        raise RuntimeError('font could not be rendered')
                    preview,used_px,ink_h=rendered
                    # Kandidat ostaje u stvarnoj proporciji; samo ga ograniči za prikaz.
                    pw,ph=preview.size
                    maxw,maxh=max(760, desired_mid-20),110
                    rr=min(1.0,maxw/max(1,pw),maxh/max(1,ph))
                    if rr<1: preview=preview.resize((max(1,int(pw*rr)),max(1,int(ph*rr))),Image.Resampling.LANCZOS)
                    tkprev=ImageTk.PhotoImage(preview); refs.append(tkprev)
                    ttk.Label(mid,image=tkprev).pack(anchor='w',pady=2)
                    ttk.Label(mid,text=f'Rendered at actual character height ≈ {ink_h}px').pack(anchor='w')
                except Exception as ex:
                    ttk.Label(mid,text=f'[Font preview unavailable: {ex}]').pack(anchor='w')

                try:
                    rs=snap.copy()
                    rw,rh=rs.size
                    maxrw,maxrh=max(300, desired_snap-20),95
                    rr=min(1.0,maxrw/max(1,rw),maxrh/max(1,rh))
                    if rr<1: rs=rs.resize((max(1,int(rw*rr)),max(1,int(rh*rr))),Image.Resampling.LANCZOS)
                    tks=ImageTk.PhotoImage(rs); refs.append(tks)
                    ttk.Label(right,text='ORIGINAL SNAPSHOT',font=('Segoe UI',9,'bold')).pack(anchor='w')
                    ttk.Label(right,image=tks).pack(anchor='w',pady=2)
                except Exception:
                    ttk.Label(right,text='The snapshot could not be displayed.').pack(anchor='w')

            ttk.Button(win,text='Close',command=win.destroy).pack(pady=8)
            win.update_idletasks()
            try:
                canvas.configure(scrollregion=canvas.bbox('all'))
                win.update_idletasks()
            except Exception:
                pass
        except Exception as e:
            messagebox.showerror(TITLE,'Error displaying fonts:\n\n'+str(e))

    def _detect_selected_text_from_crop(self,crop):
        """OCR for scanned/image-only PDF font preview.

        V66: RapidOCR is the primary OCR path for image-only PDFs.  Tesseract
        is used only as a fallback when RapidOCR is unavailable or returns no
        usable text.  OCR words are ordered by their actual polygon position
        (top-to-bottom, then left-to-right), so multi-word selections are not
        reconstructed from an arbitrary OCR string order.
        """
        try:
            base=crop.convert('RGB')

            # ---- V66 primary path: RapidOCR with geometry ----
            try:
                global _rapidocr_engine
                if _rapidocr_engine is None:
                    try:
                        from rapidocr_onnxruntime import RapidOCR
                    except ImportError:
                        v63_log('SCAN-OCR V66: RapidOCR nije instaliran -> pokusavam instalaciju')
                        subprocess.check_call([sys.executable,'-m','pip','install','rapidocr_onnxruntime'])
                        from rapidocr_onnxruntime import RapidOCR
                    _rapidocr_engine = RapidOCR()

                arr=np.array(base.convert('RGB'))
                result, _ = _rapidocr_engine(arr)
                items=[]
                if result:
                    for item in result:
                        try:
                            poly=item[0]
                            txt=str(item[1]).strip()
                            score=float(item[2])
                            if not txt or score < 0.25 or not poly:
                                continue
                            xs=[float(pt[0]) for pt in poly]
                            ys=[float(pt[1]) for pt in poly]
                            x0,x1=min(xs),max(xs)
                            y0,y1=min(ys),max(ys)
                            items.append({'text':txt,'score':score,'x0':x0,'x1':x1,'y0':y0,'y1':y1})
                        except Exception:
                            continue

                if items:
                    # Group OCR words into visual lines.  This keeps normal
                    # word order while preserving spaces between words.
                    items.sort(key=lambda z:((z['y0']+z['y1'])/2.0,z['x0']))
                    rows=[]
                    for it in items:
                        cy=(it['y0']+it['y1'])/2.0
                        h=max(1.0,it['y1']-it['y0'])
                        placed=False
                        for row in rows:
                            if abs(cy-row['cy']) <= max(4.0,min(h,row['h'])*0.65):
                                row['items'].append(it)
                                n=len(row['items'])
                                row['cy']=(row['cy']*(n-1)+cy)/n
                                row['h']=max(row['h'],h)
                                placed=True
                                break
                        if not placed:
                            rows.append({'cy':cy,'h':h,'items':[it]})
                    rows.sort(key=lambda r:r['cy'])

                    lines=[]
                    for row in rows:
                        row['items'].sort(key=lambda z:z['x0'])
                        line=''
                        prev=None
                        for it in row['items']:
                            if prev is not None:
                                gap=it['x0']-prev['x1']
                                prev_w=max(1.0,prev['x1']-prev['x0'])
                                # OCR already gives words, so a normal single
                                # space is sufficient between separate boxes.
                                if gap >= -0.25*min(prev_w,max(1.0,it['x1']-it['x0'])):
                                    line += ' '
                            line += it['text']
                            prev=it
                        if line.strip():
                            lines.append(line.strip())

                    txt=' '.join(lines).strip()
                    v63_log('SCAN-OCR V66 RapidOCR sirovi=' + repr([(i['text'],round(i['x0'],1),round(i['y0'],1),round(i['x1'],1),round(i['y1'],1),round(i['score'],3)) for i in items]))
                    v63_log('SCAN-OCR V66 redovi=' + repr(lines))
                    v63_log('SCAN-OCR V66 KRAJNJI tekst=' + repr(txt))
                    if txt:
                        return txt
                else:
                    v63_log('SCAN-OCR V66 RapidOCR nije vratio upotrebljive rezultate')
            except Exception as e:
                v63_log('SCAN-OCR V66 RapidOCR GRESKA=' + repr(e))

            # ---- Fallback: existing Tesseract character-order path ----
            from PIL import ImageOps
            def char_candidates(img):
                out=[]
                for psm in (7,6,11):
                    try:
                        raw=pytesseract.image_to_boxes(img, lang='srp_latn+eng', config=f'--psm {psm}')
                        v63_log(f'SCAN-OCR Tesseract psm={psm}: RAW=' + repr(raw[:5000]))
                    except Exception as _ocr_ex:
                        v63_log(f'SCAN-OCR Tesseract psm={psm}: GRESKA=' + repr(_ocr_ex))
                        continue
                    H=img.height; chars=[]
                    for line in raw.splitlines():
                        parts=line.split()
                        if len(parts)<5: continue
                        ch=parts[0]
                        try: x0,y0,x1,y1=map(int,parts[1:5])
                        except Exception: continue
                        top=max(0,H-y1); bottom=min(H,H-y0)
                        if x1>x0 and bottom>top: chars.append((x0,top,x1,bottom,ch))
                    if not chars: continue
                    chars.sort(key=lambda z:((z[1]+z[3])/2.0,z[0]))
                    rows=[]
                    for c in chars:
                        cy=(c[1]+c[3])/2.0; h=c[3]-c[1]; placed=False
                        for row in rows:
                            if abs(cy-row['cy']) <= max(3,min(h,row['h'])*0.65):
                                row['items'].append(c); n=len(row['items'])
                                row['cy']=(row['cy']*(n-1)+cy)/n; row['h']=max(row['h'],h); placed=True; break
                        if not placed: rows.append({'cy':cy,'h':h,'items':[c]})
                    rows.sort(key=lambda r:r['cy']); lines=[]
                    for row in rows:
                        items=sorted(row['items'],key=lambda z:(z[0],z[1]))
                        widths=[max(1,c[2]-c[0]) for c in items]
                        gaps=[max(0,b[0]-a[2]) for a,b in zip(items,items[1:])]
                        med_gap=float(np.median([g for g in gaps if g>0])) if any(g>0 for g in gaps) else 0.0
                        med_w=float(np.median(widths)) if widths else 1.0
                        space_thr=max(2.0,med_w*0.55,med_gap*1.45 if med_gap else 0.0)
                        line=''
                        for i,c in enumerate(items):
                            if i and (c[0]-items[i-1][2])>=space_thr: line+=' '
                            line+=str(c[4])
                        if line.strip(): lines.append(line.strip())
                    txt=' '.join(lines).strip()
                    if txt: out.append((txt,psm,len(chars)))
                return out

            pool=char_candidates(base)
            if pool:
                pool.sort(key=lambda x:(x[2],len(x[0])),reverse=True)
                v63_log('SCAN-OCR Tesseract IZABRAN=' + repr(pool[0][0]))
                return pool[0][0]

            vals=[]
            for psm in (7,6,8):
                try:
                    txt=pytesseract.image_to_string(base,lang='srp_latn+eng',config=f'--psm {psm}').strip()
                except Exception:
                    txt=''
                txt=' '.join(txt.split())
                if txt: vals.append(txt)
            if vals:
                return max(vals,key=lambda x:(len(x),x))
        except Exception as e:
            v63_log('SCAN-OCR V66 opsta GRESKA=' + repr(e))
        return _rapidocr_text(crop)

    def _show_font_result_dialog(self, title, lines, preview_args=None):
        """Rezultatski dijalog sa pravim dugmetom Prikaži fontove."""
        win=tk.Toplevel(self.root)
        win.title(title)
        win.transient(self.root)
        win.grab_set()
        win.resizable(True,True)
        frm=ttk.Frame(win,padding=14); frm.pack(fill='both',expand=True)
        txt=tk.Text(frm,width=72,height=max(10,min(22,len(lines)+3)),wrap='word')
        txt.pack(fill='both',expand=True)
        txt.insert('1.0','\n'.join(lines))
        txt.configure(state='disabled')
        btns=ttk.Frame(frm); btns.pack(fill='x',pady=(10,0))
        if preview_args is not None:
            ttk.Button(btns,text='Show Fonts',command=lambda:self._show_font_preview(*preview_args)).pack(side='left')
        ttk.Button(btns,text='Close',command=win.destroy).pack(side='right')
        win.update_idletasks()
        w=min(760,max(520,win.winfo_reqwidth())); h=min(620,max(300,win.winfo_reqheight()))
        win.geometry(f'{w}x{h}')

    def show_font_preview_from_selection(self):
        """V40: Prikaži fontove aktivira zeleni izbor; postojeći izbor se odmah obrađuje."""
        self.font_action='preview'
        self.add_text_point=None
        if not self.font_rect:
            if self.page_img is not None:
                self.set_mode('font')
                self.info.set('GREEN FRAME: select the text you want to compare. When you release the mouse, the font preview window opens automatically.')
            return
        if self.doc is None or self.page_img is None:
            return
        try:
            page=self.doc[self.page_index]
            args=self._text_pdf_preview_args(page,self.font_rect)
            if args is not None:
                crop,text,size,mm,guessed,exact_path,label=args
                self._show_font_preview(crop,text,size,mm,guessed,exact_path,label)
                return
            # Ako PDF ima tekstualni sloj, ne sme se prelaziti na OCR samo zato
            # što selekcija nije pogodila znak. OCR je dozvoljen samo za scan PDF.
            # Ako bilo koji PyMuPDF extractor vidi tekst, OCR se ne koristi.
            plain=(page.get_text('text') or '')
            words=(page.get_text('words') or [])
            dd=(page.get_text('dict') or {})
            has_extracted=bool(plain.strip() or words or any(b.get('type')==0 for b in dd.get('blocks',[])))
            if has_extracted:
                v63_log('TEXT PDF: text extractors found text, but the selection did not cover it; OCR WILL NOT RUN')
                messagebox.showinfo(TITLE, 'The PDF contains text, but the green frame did not cover it.\n\nMove or enlarge the green frame so it includes the characters you want to analyze.')
                return
            crop=self.page_img.crop(self.font_rect).convert('RGB')
            pt,med,mm,_=self._font_size_from_scan(crop)
            text=self._detect_selected_text_from_crop(crop)
            if not text:
                messagebox.showinfo(TITLE,'The program could not read the text. Select one short word or a few characters in the same font.')
                return
            self._show_font_preview(crop,text,pt,mm)
        except Exception as e:
            messagebox.showerror(TITLE,'Error displaying fonts:\n\n'+str(e))

    def detect_font_size(self):
        """Determine font/size for both text PDFs and scanned PDFs, with visual system-font preview for scans."""
        rect=self.font_rect
        if not rect:
            # V31: klik na „Odredi font i veličinu“ samo aktivira zeleni režim
            # za označavanje. Nema nepotrebnog dijaloga; analiza se pokreće
            # automatski tek kada korisnik završi označavanje.
            if self.page_img is not None:
                self.set_mode('font')
            return
        if self.doc is None:return
        try:
            page=self.doc[self.page_index]
            sel=self._selection_pdf_rect(rect)
            data=page.get_text('dict')
            hits=[]
            for block in data.get('blocks',[]):
                for line in block.get('lines',[]):
                    for span in line.get('spans',[]):
                        bbox=fitz.Rect(span.get('bbox',(0,0,0,0)))
                        area=self._rect_intersection_area(sel,bbox)
                        if area>0: hits.append((area,span,bbox))
            if hits:
                hits.sort(key=lambda x:x[0],reverse=True)
                lines=[]
                for area,span,bbox in hits:
                    name=span.get('font',''); real=_font_name_from_embedded_ttf(self.doc,page,name)
                    shown=_clean_embedded_name(real or name); size=float(span.get('size',0) or 0); flags=int(span.get('flags',0) or 0)
                    style=[]
                    if flags & 16:style.append('Bold')
                    if flags & 2:style.append('Italic')
                    lines.append((area,shown,size,style,span.get('text',''),name))
                best=lines[0]
                msg=['TEXT-BASED PDF – font and size were retrieved from the PDF itself.','',f'Font: {best[1]}',f'Size: {best[2]:.2f} pt']
                if best[3]:msg.append('Stil: '+' + '.join(best[3]))
                msg.append(f'Izabrani tekst: {best[4]}')
                if best[5]!=best[1]:msg.append(f'PDF naziv font resursa: {best[5]}')
                if len(lines)>1:
                    others=[]; seen=set()
                    for a,nm,sz,sty,tx,res in lines:
                        key=(nm,round(sz,3),tuple(sty))
                        if key not in seen: seen.add(key); others.append(f'{nm} — {sz:.2f} pt')
                    if len(others)>1: msg += ['', 'Multiple font/size combinations were found in the selected area:'] + ['• '+x for x in others]
                # I kod tekstualnog PDF-a omogućavamo vizuelno poređenje sa fontovima
                # instaliranim na računaru. Tekst se uzima direktno iz PDF-a.
                try:
                    preview_crop=self.page_img.crop(rect).convert('RGB')
                    exact_path=self._embedded_font_file_for_resource(page,best[5])
                    preview_args=(preview_crop,best[4],best[2],best[2]*25.4/72.0,best[1],exact_path,best[1])
                except Exception:
                    preview_args=None
                self._show_font_result_dialog('Font and Size',msg,preview_args)
                self.info.set(f'Font: {best[1]} | size: {best[2]:.2f} pt'); return

            src=self.page_img
            crop=src.crop(rect).convert('RGB')
            pt,med,mm,_=self._font_size_from_scan(crop)
            ocr_text=self._detect_selected_text_from_crop(crop)
            guess=None; score=0.0
            if pt is not None:
                candidates=self._font_preview_candidates(crop,ocr_text,pt)
                if candidates: guess,score,_=candidates[0]
            msg=['SCANNED PDF – result is an estimate.','']
            if guess: msg.append(f'Closest matching system font: {guess} (similarity {score*100:.0f}%)')
            else: msg.append('Font: could not be identified reliably automatically.')
            if pt is not None:
                msg.append(f'Measured character height: {mm:.2f} mm')
                msg.append(f'Estimated nominal font size: {pt:.2f} pt')
                msg.append(f'Character height in scan: {med:.1f} px at 150 DPI')
            else: msg.append('Size: could not be estimated. Select a slightly wider/taller area around the text only.')
            if ocr_text: msg.append(f'OCR text for comparison: {ocr_text}')
            msg += ['', 'Click “Show Fonts” to view the same text in fonts installed on your computer and choose the closest visual match.']
            preview_args=(crop,ocr_text,pt,mm,guess) if pt is not None and ocr_text else None
            self._show_font_result_dialog('Font and Size',msg,preview_args)
            if pt is not None:self.info.set(f'Scan estimate: {mm:.2f} mm | ~{pt:.2f} pt' + (f' | {guess}' if guess else ''))
        except Exception as e:
            messagebox.showerror(TITLE,'Error identifying font and size:\n\n'+str(e))

    def _font_files_by_style(self):
        """V44: mapira sistemske fontove po porodici i praktičnom stilu."""
        files=self._system_font_files()
        choices={}
        for fam,path in files:
            cat=self._font_style_category(path,fam)
            key=(str(fam).casefold(),cat)
            if key not in choices:
                choices[key]=(fam,path,cat)
        return sorted(choices.values(), key=lambda x:(str(x[0]).casefold(), str(x[2]).casefold()))

    def _add_text_dialog(self,x,y,prefill=None):
        """V44: osnovni unos novog teksta na izabranu poziciju."""
        if self.page_img is None:
            return
        try:
            choices=self._font_files_by_style()
            if not choices:
                messagebox.showwarning(TITLE,'No fonts were found in the Windows Fonts folder.')
                return
            families=[]
            for fam,_,_ in choices:
                if fam not in families:
                    families.append(fam)
            families=sorted(families,key=lambda v:str(v).casefold())
            fam_default='Arial' if 'Arial' in families else families[0]

            win=tk.Toplevel(self.root)
            win.title('Add Text')
            win.transient(self.root); win.grab_set(); win.resizable(False,False)
            frm=ttk.Frame(win,padding=14); frm.pack(fill='both',expand=True)

            ttk.Label(frm,text='Text to add:',font=('Segoe UI',10,'bold')).grid(row=0,column=0,columnspan=2,sticky='w',pady=(0,5))
            text_var=tk.StringVar(value='' if prefill is None else str(prefill))
            text_entry=tk.Text(frm,width=52,height=6,wrap='word',undo=True)
            text_entry.grid(row=1,column=0,columnspan=2,sticky='ew',pady=(0,10))
            if prefill is not None:
                text_entry.insert('1.0',str(prefill))

            ttk.Label(frm,text='Font:').grid(row=2,column=0,sticky='w',padx=(0,8),pady=4)
            fam_var=tk.StringVar(value=fam_default)
            fam_box=ttk.Combobox(frm,textvariable=fam_var,values=families,state='readonly',width=36)
            fam_box.grid(row=2,column=1,sticky='ew',pady=4)

            ttk.Label(frm,text='Style:').grid(row=3,column=0,sticky='w',padx=(0,8),pady=4)
            style_var=tk.StringVar(value='Regular')
            style_box=ttk.Combobox(frm,textvariable=style_var,values=('Regular','Bold','Italic','Bold Italic'),state='readonly',width=20)
            style_box.grid(row=3,column=1,sticky='w',pady=4)

            ttk.Label(frm,text='Size (pt):').grid(row=4,column=0,sticky='w',padx=(0,8),pady=4)
            size_var=tk.StringVar(value='8.00')
            size_spin=ttk.Spinbox(frm,from_=1.0,to=500.0,increment=1.0,textvariable=size_var,width=12).grid(row=4,column=1,sticky='w',pady=4)
            ttk.Label(frm,text='(Use arrows for ±1 pt or type a value)').grid(row=4,column=2,sticky='w',padx=(8,0),pady=4)

            ttk.Label(frm,text='Alignment:').grid(row=5,column=0,sticky='w',padx=(0,8),pady=4)
            align_var=tk.StringVar(value='Left')
            ttk.Combobox(frm,textvariable=align_var,values=('Left','Right','Center','Justify'),state='readonly',width=20).grid(row=5,column=1,sticky='w',pady=4)

            ttk.Label(frm,text='Right Margin (mm):').grid(row=6,column=0,sticky='w',padx=(0,8),pady=4)
            margin_var=tk.StringVar(value='5.00')
            ttk.Spinbox(frm,from_=0.0,to=100.0,increment=0.5,textvariable=margin_var,width=12).grid(row=6,column=1,sticky='w',pady=4)
            ttk.Label(frm,text='0.00 = flush with the document edge').grid(row=6,column=2,sticky='w',padx=(8,0),pady=4)

            ttk.Label(frm,text='Color:').grid(row=7,column=0,sticky='w',padx=(0,8),pady=4)
            color_var=tk.StringVar(value='#000000')
            color_preview=tk.Label(frm,text='   ',bg='#000000',relief='solid',width=5)
            color_preview.grid(row=7,column=1,sticky='w',pady=4)
            def choose_color():
                from tkinter import colorchooser
                c=colorchooser.askcolor(initialcolor=color_var.get(),parent=win,title='Choose text color')
                if c and c[1]:
                    color_var.set(c[1]); color_preview.configure(bg=c[1])
            ttk.Button(frm,text='Choose Color',command=choose_color).grid(row=7,column=1,sticky='e',pady=4)

            ttk.Label(frm,text='Alignment applies within the area from the clicked point to the document’s right margin: Left, Right, Center, or Justify.',wraplength=430).grid(row=8,column=0,columnspan=2,sticky='w',pady=(10,4))
            ttk.Label(frm,text='Text is inserted at the clicked position. After insertion, you can move and resize it using the blue frame.',wraplength=430).grid(row=9,column=0,columnspan=2,sticky='w',pady=(2,8))

            result={}
            def apply():
                txt=text_entry.get('1.0','end-1c')
                if not txt.strip():
                    messagebox.showwarning(TITLE,'Enter the text you want to add.',parent=win); return
                try:
                    pt=float(size_var.get().replace(',','.'))
                except Exception:
                    messagebox.showwarning(TITLE,'Font size must be a number in points (pt).',parent=win); return
                if pt<=0 or pt>500:
                    messagebox.showwarning(TITLE,'Font size must be greater than 0 and within a reasonable range.',parent=win); return
                try:
                    margin_mm=float(margin_var.get().replace(',','.'))
                except Exception:
                    messagebox.showwarning(TITLE,'Right margin must be a number in millimeters (mm).',parent=win); return
                if margin_mm<0 or margin_mm>100:
                    messagebox.showwarning(TITLE,'Right margin must be between 0 and 100 mm.',parent=win); return
                fam=fam_var.get(); style=style_var.get()
                matches=[(f,p,c) for f,p,c in choices if str(f).casefold()==str(fam).casefold() and c==style]
                if not matches:
                    matches=[(f,p,c) for f,p,c in choices if str(f).casefold()==str(fam).casefold() and c=='Regular']
                if not matches:
                    messagebox.showwarning(TITLE,f'No “{style}” style was found for font “{fam}”.',parent=win); return
                result.update(text=txt,family=matches[0][0],path=matches[0][1],style=matches[0][2],pt=pt,color=color_var.get(),align=align_var.get(),margin_mm=margin_mm)
                win.destroy()
            ttk.Button(frm,text='Add',command=apply).grid(row=10,column=0,sticky='w',pady=(8,0))
            ttk.Button(frm,text='Cancel',command=win.destroy).grid(row=10,column=1,sticky='e',pady=(8,0))
            # Enter u višelinijskom polju služi samo za novi red.
            # Dodavanje se izvršava isključivo klikom na dugme „Dodaj“.
            text_entry.focus_set()
            win.wait_window()
            if not result:
                self.set_mode('move')
                return
            self._insert_text_result(x,y,result['text'],result['path'],result['pt'],result['color'],result['family'],result['style'],result.get('align','Left'),result.get('margin_mm',5.0))
        except Exception as e:
            messagebox.showerror(TITLE,'Error adding text:\n\n'+str(e))

    def _insert_text_result(self,x,y,text,font_path,pt,color,family,style,align='Left',margin_mm=5.0):
        """V78: dodaje tekst od kliknute tačke uz izbor poravnanja i desne margine; čuva descendere."""
        from PIL import ImageFont, ImageColor
        base=(self._current_view_source() or self.page_img).copy().convert('RGB')
        try:
            px=max(1,int(round(float(pt)*150.0/72.0)))
            font=ImageFont.truetype(font_path,px)
            spacing=max(1,int(px*0.15))
            draw_tmp=ImageDraw.Draw(Image.new('L',(1,1)))

            start_x=max(0,min(int(x),base.width-1))
            margin_px=max(0,int(round(float(margin_mm)*150.0/25.4)))
            max_width=max(1,base.width-start_x-margin_px)

            def line_width(line):
                if not line:
                    return 0
                bb=draw_tmp.textbbox((0,0),line,font=font)
                return max(0,bb[2]-bb[0])

            def wrap_one_line(line):
                if line == '':
                    return ['']
                words=line.split(' ')
                out=[]; current=''
                for word in words:
                    candidate=word if not current else current+' '+word
                    if line_width(candidate) <= max_width:
                        current=candidate
                        continue
                    if current:
                        out.append(current)
                        current=''
                    part=''
                    for ch in word:
                        cand=part+ch
                        if part and line_width(cand) > max_width:
                            out.append(part)
                            part=ch
                        elif not part and line_width(cand) > max_width:
                            out.append(ch)
                            part=''
                        else:
                            part=cand
                    current=part
                if current or not out:
                    out.append(current)
                return out

            # Prvo prelamamo tekst tako da nijedan red ne izađe iz desne margine.
            wrapped_lines=[]
            for original_line in str(text).split('\n'):
                wrapped_lines.extend(wrap_one_line(original_line))

            # Kod Obostranog poravnanja treba znati koji je poslednji red svakog
            # originalnog pasusa, jer se poslednji red standardno ne razvlači.
            paragraphs=[]
            idx=0
            for original_line in str(text).split('\n'):
                n=len(wrap_one_line(original_line))
                paragraphs.append((idx,idx+n-1))
                idx+=n

            render_width=max_width if align in ('Right','Center','Justify') else max(1,max((line_width(v) for v in wrapped_lines),default=1))
            # V78: visina reda mora da obuhvati i donje delove slova kao sto su g, p, j, q.
            # PIL-ov textbbox ima gornji offset (y1), pa crtanje na yy=0 bez korekcije
            # moze da odsece descendere pri dnu. Crtamo svaki red sa -text_top.
            font_bbox=draw_tmp.textbbox((0,0),'Ag',font=font)
            text_top=int(font_bbox[1])
            text_bottom=int(font_bbox[3])
            line_height=max(1,text_bottom-text_top)
            total_h=max(1,len(wrapped_lines)*line_height + max(0,len(wrapped_lines)-1)*spacing)
            overlay=Image.new('RGBA',(render_width,total_h),(0,0,0,0))
            d=ImageDraw.Draw(overlay)

            def draw_justified(line, yy, is_last_of_paragraph):
                if not line or is_last_of_paragraph or ' ' not in line:
                    d.text((0,yy-text_top),line,font=font,fill=rgb+(255,))
                    return
                words=line.split(' ')
                widths=[line_width(w) for w in words]
                gaps=len(words)-1
                extra=max(0,render_width-sum(widths))
                gap=extra/gaps if gaps else 0
                xx=0.0
                for i,w in enumerate(words):
                    d.text((int(round(xx)),yy-text_top),w,font=font,fill=rgb+(255,))
                    xx += widths[i]
                    if i<gaps:
                        xx += gap

            rgb=ImageColor.getrgb(color)
            for i,line in enumerate(wrapped_lines):
                yy=i*(line_height+spacing)
                lw=line_width(line)
                if align=='Left':
                    xx=0
                    d.text((xx,yy-text_top),line,font=font,fill=rgb+(255,))
                elif align=='Right':
                    xx=max(0,render_width-lw)
                    d.text((xx,yy-text_top),line,font=font,fill=rgb+(255,))
                elif align=='Center':
                    xx=max(0,(render_width-lw)//2)
                    d.text((xx,yy-text_top),line,font=font,fill=rgb+(255,))
                else:  # Obostrano
                    last_para=False
                    for a,b in paragraphs:
                        if a<=i<=b:
                            last_para=(i==b)
                            break
                    draw_justified(line,yy,last_para)

            # Kod Levo okvir prati stvarnu širinu teksta; kod ostalih opcija
            # okvir predstavlja ceo raspoloživi prostor od klika do desne margine.
            if align=='Left':
                actual_w=max(1,max((line_width(v) for v in wrapped_lines),default=1))
                # Redovi su već prelomljeni prema max_width-u.
                overlay=overlay.crop((0,0,min(actual_w,overlay.width),overlay.height))

            ox=start_x
            oy=max(0,min(int(y),base.height-overlay.height))
            previous=self.result.copy() if self.result is not None else self.page_img.copy()
            self.undo_stack.append(previous); self.redo_stack.clear()
            base.paste(overlay,(ox,oy),overlay)
            self.result=base
            self.move_rect=(ox,oy,ox+overlay.width,oy+overlay.height)
            self.added_text_info={
                'text':text,'font_path':font_path,'pt':float(pt),'color':color,
                'family':family,'style':style,'align':align,'margin_mm':float(margin_mm),'rect':tuple(self.move_rect)
            }
            self.show_image(base,keep_scale=True)
            self.mode='addtext'
            self.canvas.config(cursor='crosshair')
            self.canvas.delete('move_sel'); self.canvas.delete('move_handle')
            self._draw_add_text_rect()
            self.info.set(f'Text added „{text}“ — {family}, {style}, {pt:.2f} pt, alignment: {align}, right margin: {float(margin_mm):.2f} mm.')
        except Exception as e:
            messagebox.showerror(TITLE,'Could not add text:\n\n'+str(e))

    def _edit_text_dialog(self, initial=None):
        """V79: isti unos i iste opcije kao „Dodaj tekst“."""
        info=initial or self.added_text_info
        if not info:
            messagebox.showinfo(TITLE,'Add text first; it can remain in the gray dashed frame. To move it, use “Move Items”.')
            return None
        choices=self._font_files_by_style()
        if not choices:
            messagebox.showwarning(TITLE,'No fonts were found in the Windows Fonts folder.')
            return None
        families=[]
        for fam,_,_ in choices:
            if fam not in families:
                families.append(fam)
        families=sorted(families,key=lambda v:str(v).casefold())
        fam_default=info.get('family') if info.get('family') in families else ('Arial' if 'Arial' in families else families[0])

        win=tk.Toplevel(self.root)
        win.title('Edit Added Text')
        win.transient(self.root); win.grab_set(); win.resizable(False,False)
        frm=ttk.Frame(win,padding=14); frm.pack(fill='both',expand=True)

        ttk.Label(frm,text='Text to edit:',font=('Segoe UI',10,'bold')).grid(row=0,column=0,columnspan=2,sticky='w',pady=(0,5))
        text_entry=tk.Text(frm,width=52,height=6,wrap='word',undo=True)
        text_entry.grid(row=1,column=0,columnspan=2,sticky='ew',pady=(0,10))
        text_entry.insert('1.0',str(info.get('text','')))

        ttk.Label(frm,text='Font:').grid(row=2,column=0,sticky='w',padx=(0,8),pady=4)
        fam_var=tk.StringVar(value=fam_default)
        ttk.Combobox(frm,textvariable=fam_var,values=families,state='readonly',width=36).grid(row=2,column=1,sticky='ew',pady=4)

        ttk.Label(frm,text='Style:').grid(row=3,column=0,sticky='w',padx=(0,8),pady=4)
        style_var=tk.StringVar(value=info.get('style','Regular'))
        ttk.Combobox(frm,textvariable=style_var,values=('Regular','Bold','Italic','Bold Italic'),state='readonly',width=20).grid(row=3,column=1,sticky='w',pady=4)

        ttk.Label(frm,text='Size (pt):').grid(row=4,column=0,sticky='w',padx=(0,8),pady=4)
        size_var=tk.StringVar(value=f"{float(info.get('pt',8.0)):.2f}")
        ttk.Spinbox(frm,from_=1.0,to=500.0,increment=1.0,textvariable=size_var,width=12).grid(row=4,column=1,sticky='w',pady=4)
        ttk.Label(frm,text='(Use arrows for ±1 pt or type a value)').grid(row=4,column=2,sticky='w',padx=(8,0),pady=4)

        ttk.Label(frm,text='Alignment:').grid(row=5,column=0,sticky='w',padx=(0,8),pady=4)
        align_var=tk.StringVar(value=info.get('align','Left'))
        ttk.Combobox(frm,textvariable=align_var,values=('Left','Right','Center','Justify'),state='readonly',width=20).grid(row=5,column=1,sticky='w',pady=4)

        ttk.Label(frm,text='Right Margin (mm):').grid(row=6,column=0,sticky='w',padx=(0,8),pady=4)
        margin_var=tk.StringVar(value=f"{float(info.get('margin_mm',5.0)):.2f}")
        ttk.Spinbox(frm,from_=0.0,to=100.0,increment=0.5,textvariable=margin_var,width=12).grid(row=6,column=1,sticky='w',pady=4)
        ttk.Label(frm,text='0.00 = flush with the document edge').grid(row=6,column=2,sticky='w',padx=(8,0),pady=4)

        ttk.Label(frm,text='Color:').grid(row=7,column=0,sticky='w',padx=(0,8),pady=4)
        color_var=tk.StringVar(value=info.get('color','#000000'))
        color_preview=tk.Label(frm,text='   ',bg=color_var.get(),relief='solid',width=5)
        color_preview.grid(row=7,column=1,sticky='w',pady=4)
        def choose_color():
            from tkinter import colorchooser
            c=colorchooser.askcolor(initialcolor=color_var.get(),parent=win,title='Choose text color')
            if c and c[1]:
                color_var.set(c[1]); color_preview.configure(bg=c[1])
        ttk.Button(frm,text='Choose Color',command=choose_color).grid(row=7,column=1,sticky='e',pady=4)

        ttk.Label(frm,text='Alignment applies within the area from the clicked point to the document’s right margin: Left, Right, Center, or Justify.',wraplength=430).grid(row=8,column=0,columnspan=2,sticky='w',pady=(10,4))
        ttk.Label(frm,text='Text is edited in its current position. Enter creates a new line; changes are applied only when you click “Apply”.',wraplength=430).grid(row=9,column=0,columnspan=2,sticky='w',pady=(2,8))

        result={}
        def apply():
            txt=text_entry.get('1.0','end-1c')
            if not txt.strip():
                messagebox.showwarning(TITLE,'Enter text.',parent=win); return
            try:
                pt=float(size_var.get().replace(',','.'))
            except Exception:
                messagebox.showwarning(TITLE,'Font size must be a number in points (pt).',parent=win); return
            if pt<=0 or pt>500:
                messagebox.showwarning(TITLE,'Font size must be greater than 0 and within a reasonable range.',parent=win); return
            try:
                margin_mm=float(margin_var.get().replace(',','.'))
            except Exception:
                messagebox.showwarning(TITLE,'Right margin must be a number in millimeters (mm).',parent=win); return
            if margin_mm<0 or margin_mm>100:
                messagebox.showwarning(TITLE,'Right margin must be between 0 and 100 mm.',parent=win); return
            fam=fam_var.get(); style=style_var.get()
            matches=[(f,p,c) for f,p,c in choices if str(f).casefold()==str(fam).casefold() and c==style]
            if not matches:
                matches=[(f,p,c) for f,p,c in choices if str(f).casefold()==str(fam).casefold() and c=='Regular']
            if not matches:
                messagebox.showwarning(TITLE,f'No “{style}” style was found for font “{fam}”.',parent=win); return
            result.update(text=txt,font_path=matches[0][1],pt=pt,color=color_var.get(),family=matches[0][0],style=matches[0][2],align=align_var.get(),margin_mm=margin_mm)
            win.destroy()
        ttk.Button(frm,text='Apply',command=apply).grid(row=10,column=0,sticky='w',pady=(8,0))
        ttk.Button(frm,text='Cancel',command=win.destroy).grid(row=10,column=1,sticky='e',pady=(8,0))
        # Enter u višelinijskom polju služi samo za novi red.
        # Izmena se izvršava isključivo klikom na dugme „Primeni“.
        text_entry.focus_set()
        win.wait_window()
        return result or None

    def edit_added_text(self):
        # V47: nije potrebno da selekcija bude bajt-po-bajt ista kao prvobitni okvir.
        # Dodat tekst može biti označen sivim ili plavim okvirom; prepoznaj ga po
        # preklapanju/centru selekcije sa zapamćenim okvirom dodatog teksta.
        if not self.move_rect or not self.added_text_info:
            messagebox.showinfo(TITLE,'Add text first; it can remain in the gray dashed frame. To move it, use “Move Items”.')
            return
        arect=tuple(self.added_text_info.get('rect',()))
        cur=tuple(self.move_rect)
        if len(arect)!=4 or len(cur)!=4:
            messagebox.showinfo(TITLE,'The blue frame does not currently contain editable added text.')
            return
        ax0,ay0,ax1,ay1=arect; x0,y0,x1,y1=cur
        ix0=max(ax0,x0); iy0=max(ay0,y0); ix1=min(ax1,x1); iy1=min(ay1,y1)
        inter=max(0,ix1-ix0)*max(0,iy1-iy0)
        ca=max(1,(ax1-ax0)*(ay1-ay0)); cc=max(1,(x1-x0)*(y1-y0))
        cx=(x0+x1)/2; cy=(y0+y1)/2
        center_inside=(ax0<=cx<=ax1 and ay0<=cy<=ay1)
        if inter/min(ca,cc) < 0.35 and not center_inside:
            messagebox.showinfo(TITLE,'The blue frame does not currently contain editable added text.')
            return
        # Uvek uređujemo originalni okvir dodatog teksta, ne slučajno proširenu
        # selekciju korisnika.
        self.move_rect=arect
        new=self._edit_text_dialog(self.added_text_info)
        if not new:return
        x0,y0,x1,y1=self.move_rect
        previous=self.result.copy() if self.result is not None else self.page_img.copy()
        base=self._erase(self.result.copy().convert('RGBA'),tuple(self.move_rect)).convert('RGB')
        self.undo_stack.append(previous); self.redo_stack.clear()
        new_rect=self._render_text_on_rect(base,tuple(self.move_rect),new['text'],new['font_path'],new['pt'],new['color'],new.get('align','Left'),new.get('margin_mm',5.0))
        # Kod izmene veličine fonta NE smanjujemo novi tekst nazad na stare
        # dimenzije plavog okvira. Okvir prati stvarnu veličinu novog teksta.
        self.move_rect=tuple(new_rect)
        self.added_text_info.update(new)
        self.added_text_info['rect']=tuple(self.move_rect)
        self.result=base
        self.show_image(base,keep_scale=True)
        # V66: posle „Izmeni dodati tekst“ dodat tekst OSTANE u sivom
        # isprekidanom okviru. Plavi okvir se dobija samo klikom na
        # „Pomeranje podataka“.
        self.mode='addtext'
        self.canvas.config(cursor='crosshair')
        self.canvas.delete('move_sel'); self.canvas.delete('move_handle')
        self._draw_add_text_rect()
        self.info.set(f'Added text edited: “{new["text"]}” — {new["family"]}, {new["style"]}, {new["pt"]:.2f} pt. The gray dashed frame indicates added text; to activate the blue frame, click “Move Items”.')

    def _render_text_on_rect(self,base,rect,text,font_path,pt,color,align='Left',margin_mm=5.0):
        """V79: isti način prikaza kao kod „Dodaj tekst“, ali na postojećoj poziciji."""
        from PIL import ImageFont, ImageColor
        x0,y0,x1,y1=rect
        px=max(1,int(round(float(pt)*150.0/72.0)))
        font=ImageFont.truetype(font_path,px)
        spacing=max(1,int(px*0.15))
        draw_tmp=ImageDraw.Draw(Image.new('L',(1,1)))
        start_x=max(0,min(int(x0),base.width-1))
        margin_px=max(0,int(round(float(margin_mm)*150.0/25.4)))
        max_width=max(1,base.width-start_x-margin_px)

        def line_width(line):
            if not line: return 0
            bb=draw_tmp.textbbox((0,0),line,font=font)
            return max(0,bb[2]-bb[0])

        def wrap_one_line(line):
            if line=='': return ['']
            words=line.split(' '); out=[]; current=''
            for word in words:
                candidate=word if not current else current+' '+word
                if line_width(candidate)<=max_width:
                    current=candidate; continue
                if current:
                    out.append(current); current=''
                part=''
                for ch in word:
                    cand=part+ch
                    if part and line_width(cand)>max_width:
                        out.append(part); part=ch
                    elif not part and line_width(cand)>max_width:
                        out.append(ch); part=''
                    else:
                        part=cand
                current=part
            if current or not out: out.append(current)
            return out

        wrapped_lines=[]
        for original_line in str(text).split('\n'):
            wrapped_lines.extend(wrap_one_line(original_line))
        paragraphs=[]; idx=0
        for original_line in str(text).split('\n'):
            n=len(wrap_one_line(original_line)); paragraphs.append((idx,idx+n-1)); idx+=n

        render_width=max_width if align in ('Right','Center','Justify') else max(1,max((line_width(v) for v in wrapped_lines),default=1))
        font_bbox=draw_tmp.textbbox((0,0),'Ag',font=font)
        text_top=int(font_bbox[1]); text_bottom=int(font_bbox[3])
        line_height=max(1,text_bottom-text_top)
        total_h=max(1,len(wrapped_lines)*line_height + max(0,len(wrapped_lines)-1)*spacing)
        overlay=Image.new('RGBA',(render_width,total_h),(0,0,0,0)); d=ImageDraw.Draw(overlay)
        rgb=ImageColor.getrgb(color)

        def draw_justified(line,yy,is_last):
            if not line or is_last or ' ' not in line:
                d.text((0,yy-text_top),line,font=font,fill=rgb+(255,)); return
            words=line.split(' '); widths=[line_width(w) for w in words]; gaps=len(words)-1
            extra=max(0,render_width-sum(widths)); gap=extra/gaps if gaps else 0; xx=0.0
            for i,w in enumerate(words):
                d.text((int(round(xx)),yy-text_top),w,font=font,fill=rgb+(255,))
                xx += widths[i]
                if i<gaps: xx += gap

        for i,line in enumerate(wrapped_lines):
            yy=i*(line_height+spacing); lw=line_width(line)
            if align=='Left': xx=0; d.text((xx,yy-text_top),line,font=font,fill=rgb+(255,))
            elif align=='Right': xx=max(0,render_width-lw); d.text((xx,yy-text_top),line,font=font,fill=rgb+(255,))
            elif align=='Center': xx=max(0,(render_width-lw)//2); d.text((xx,yy-text_top),line,font=font,fill=rgb+(255,))
            else:
                last_para=False
                for a,b in paragraphs:
                    if a<=i<=b: last_para=(i==b); break
                draw_justified(line,yy,last_para)

        if align=='Left':
            actual_w=max(1,max((line_width(v) for v in wrapped_lines),default=1))
            overlay=overlay.crop((0,0,min(actual_w,overlay.width),overlay.height))
        ox=max(0,min(start_x,base.width-overlay.width))
        oy=max(0,min(int(y0),base.height-overlay.height))
        base.paste(overlay,(ox,oy),overlay)
        return (ox,oy,ox+overlay.width,oy+overlay.height)

    def _copy_source_rect(self):
        """V67: vrati trenutno selektovan pravougaonik i sliku nad kojom se radi."""
        if not self.move_rect or self.page_img is None:
            return None, None
        src=self._current_view_source() or self.page_img
        x0,y0,x1,y1=[int(v) for v in self.move_rect]
        x0=max(0,min(x0,src.width)); x1=max(0,min(x1,src.width))
        y0=max(0,min(y0,src.height)); y1=max(0,min(y1,src.height))
        if x1<=x0 or y1<=y0:
            return None, None
        return src,(x0,y0,x1,y1)

    def _read_system_clipboard(self):
        """V70: robustno čitanje Windows clipboard-a.
        Podržava tekst, datoteke/slike preko Pillow-a, CF_DIB/CF_DIBV5 i
        CF_BITMAP preko Windows GDI API-ja. Ne menja postojeću internu
        memoriju programa.
        """
        text_value=None; image_value=None
        # Tekst
        try:
            val=self.root.clipboard_get()
            if val and str(val).strip():
                text_value=str(val)
        except Exception:
            pass

        # Pillow: slike i kopirani fajlovi
        try:
            grabbed=ImageGrab.grabclipboard()
            if isinstance(grabbed, Image.Image):
                image_value=grabbed.convert('RGB')
            elif isinstance(grabbed,(list,tuple)):
                for fp in grabbed:
                    try:
                        ext=os.path.splitext(str(fp))[1].lower()
                        if ext in ('.png','.jpg','.jpeg','.bmp','.gif','.tif','.tiff','.webp'):
                            image_value=Image.open(fp).convert('RGB'); break
                    except Exception:
                        continue
        except Exception:
            pass

        if image_value is None and os.name == 'nt':
            try:
                user32=ctypes.windll.user32
                kernel32=ctypes.windll.kernel32
                gdi32=ctypes.windll.gdi32
                # IsClipboardFormatAvailable: 2=CF_BITMAP, 8=CF_DIB, 17=CF_DIBV5
                available=[]
                for fmt in (2,8,17):
                    try:
                        if user32.IsClipboardFormatAvailable(fmt):
                            available.append(fmt)
                    except Exception:
                        pass
                v63_log('CLIPBOARD: dostupni formati='+str(available))

                # VAŽNO: OpenClipboard(0) je pouzdanije od prosleđivanja Tk HWND-a.
                opened=False
                try:
                    opened=bool(user32.OpenClipboard(0))
                except Exception:
                    opened=False
                if opened:
                    try:
                        # 1) DIB / DIBV5
                        for fmt in (8,17):
                            if not user32.IsClipboardFormatAvailable(fmt):
                                continue
                            hdata=user32.GetClipboardData(fmt)
                            if not hdata:
                                v63_log(f'CLIPBOARD: GetClipboardData({fmt}) nije uspeo')
                                continue
                            ptr=kernel32.GlobalLock(hdata)
                            if not ptr:
                                v63_log(f'CLIPBOARD: GlobalLock({fmt}) nije uspeo')
                                continue
                            try:
                                header=ctypes.string_at(ptr,40)
                                if len(header)<40:
                                    continue
                                vals=struct.unpack('<IiiHHIIIIII',header)
                                bi_size,bi_width,bi_height,bi_planes,bi_bitcount,bi_compression,bi_sizeimage,bi_xppm,bi_yppm,bi_clrused,bi_clrimportant=vals
                                if bi_size < 40 or bi_width == 0 or bi_height == 0:
                                    continue
                                if bi_bitcount <= 8:
                                    colors=bi_clrused if bi_clrused else (1 << bi_bitcount)
                                    offset=bi_size + colors*4
                                elif bi_compression == 3:
                                    offset=bi_size + 12
                                elif bi_compression == 6:
                                    offset=bi_size + 16
                                else:
                                    offset=bi_size
                                rowbytes=((abs(int(bi_width))*int(bi_bitcount)+31)//32)*4
                                total_guess=max(int(bi_sizeimage or 0), abs(int(bi_height))*rowbytes)
                                total=max(40,int(offset)+total_guess)
                                dib=ctypes.string_at(ptr,total)
                                bmp_header=struct.pack('<2sIHHI',b'BM',14+len(dib),0,0,14)
                                try:
                                    image_value=Image.open(io.BytesIO(bmp_header+dib)).convert('RGB')
                                except Exception:
                                    try:
                                        max_len=kernel32.GlobalSize(hdata)
                                        if max_len and max_len>40:
                                            dib=ctypes.string_at(ptr,int(max_len))
                                            bmp_header=struct.pack('<2sIHHI',b'BM',14+len(dib),0,0,14)
                                            image_value=Image.open(io.BytesIO(bmp_header+dib)).convert('RGB')
                                    except Exception:
                                        pass
                            finally:
                                try: kernel32.GlobalUnlock(hdata)
                                except Exception: pass
                            if image_value is not None:
                                v63_log(f'CLIPBOARD: slika pročitana kao CF_DIB format={fmt} size={image_value.size}')
                                break

                        # 2) CF_BITMAP – kopija koja ne postoji kao DIB.
                        if image_value is None and user32.IsClipboardFormatAvailable(2):
                            hbmp=user32.GetClipboardData(2)
                            if hbmp:
                                class BITMAP(ctypes.Structure):
                                    _fields_=[
                                        ('bmType',ctypes.c_long),('bmWidth',ctypes.c_long),
                                        ('bmHeight',ctypes.c_long),('bmWidthBytes',ctypes.c_long),
                                        ('bmPlanes',ctypes.c_ushort),('bmBitsPixel',ctypes.c_ushort),
                                        ('bmBits',ctypes.c_void_p)]
                                bm=BITMAP()
                                if gdi32.GetObjectW(hbmp,ctypes.sizeof(BITMAP),ctypes.byref(bm)):
                                    w=int(bm.bmWidth); h=int(bm.bmHeight)
                                    if w>0 and h>0:
                                        class BITMAPINFOHEADER(ctypes.Structure):
                                            _fields_=[
                                                ('biSize',ctypes.c_uint32),('biWidth',ctypes.c_int32),
                                                ('biHeight',ctypes.c_int32),('biPlanes',ctypes.c_uint16),
                                                ('biBitCount',ctypes.c_uint16),('biCompression',ctypes.c_uint32),
                                                ('biSizeImage',ctypes.c_uint32),('biXPelsPerMeter',ctypes.c_int32),
                                                ('biYPelsPerMeter',ctypes.c_int32),('biClrUsed',ctypes.c_uint32),
                                                ('biClrImportant',ctypes.c_uint32)]
                                        bih=BITMAPINFOHEADER()
                                        bih.biSize=40; bih.biWidth=w; bih.biHeight=-h; bih.biPlanes=1; bih.biBitCount=32; bih.biCompression=0
                                        buf=ctypes.create_string_buffer(w*h*4)
                                        if gdi32.GetDIBits(0,hbmp,0,h,buf,ctypes.byref(bih),0):
                                            image_value=Image.frombuffer('RGBA',(w,h),buf,'raw','BGRA',0,1).convert('RGB').copy()
                                            v63_log(f'CLIPBOARD: slika pročitana kao CF_BITMAP size={image_value.size}')
                    finally:
                        try: user32.CloseClipboard()
                        except Exception: pass
            except Exception as e:
                v63_log('CLIPBOARD: Windows API greska='+repr(e))
        return text_value,image_value

    def _enter_paste_target_mode(self):
        self.mode='paste_target'
        self.canvas.config(cursor='crosshair')
        self.canvas.delete('sel'); self.canvas.delete('move_sel'); self.canvas.delete('move_handle'); self.canvas.delete('add_text_sel'); self.canvas.delete('paste_target')
        self.info.set('The copied item is ready. Click the exact place where you want to paste it, then click “Paste”.')

    def copy_selection(self):
        """V68: kopira selektovani podatak i čeka da korisnik klikne mesto za lepljenje."""
        src,rect=self._copy_source_rect()
        if src is None:
            messagebox.showinfo(TITLE,'First select the item you want to copy. Use “Move Items” to select an item.')
            return
        self.clipboard_image=src.crop(rect).convert('RGB')
        self.clipboard_size=self.clipboard_image.size
        self.clipboard_text=None
        self.clipboard_source='internal'
        self.clipboard_added_info=None
        if self.added_text_info and tuple(self.added_text_info.get('rect',()))==tuple(rect):
            self.clipboard_added_info=dict(self.added_text_info)
            self.clipboard_text=str(self.added_text_info.get('text',''))
            self.clipboard_added_info['rect']=tuple(rect)
        self.paste_target=None
        self._enter_paste_target_mode()

    def cut_selection(self):
        """V68: iseče podatak, stavi ga u internu memoriju i čeka mesto za Paste."""
        src,rect=self._copy_source_rect()
        if src is None:
            messagebox.showinfo(TITLE,'First select the item you want to cut. Use “Move Items” to select an item.')
            return
        self.clipboard_image=src.crop(rect).convert('RGB')
        self.clipboard_size=self.clipboard_image.size
        self.clipboard_text=None
        self.clipboard_source='internal'
        self.clipboard_added_info=None
        if self.added_text_info and tuple(self.added_text_info.get('rect',()))==tuple(rect):
            self.clipboard_added_info=dict(self.added_text_info)
            self.clipboard_text=str(self.added_text_info.get('text',''))
            self.clipboard_added_info['rect']=tuple(rect)
        previous=src.copy()
        final=self._erase(src.convert('RGBA'),rect).convert('RGB')
        self.undo_stack.append(previous); self.redo_stack.clear()
        self.result=final
        self.move_rect=None
        self.move_action=None; self.transform_base=None; self.transform_src_rect=None
        if self.clipboard_added_info is not None:
            self.added_text_info=None
        self.show_image(final,keep_scale=True)
        self.canvas.delete('move_sel'); self.canvas.delete('move_handle'); self.canvas.delete('add_text_sel')
        self.paste_target=None
        self._enter_paste_target_mode()
        self.info.set('The item has been cut. Click the destination, then click “Paste”.')

    def _ask_paste_type(self, text_value=None, img=None):
        """V71: pre lepljenja pita da li sadržaj treba nalepiti kao sliku ili tekst."""
        has_text=bool(text_value is not None and str(text_value).strip())
        has_image=img is not None
        if not has_text and not has_image:
            return None
        win=tk.Toplevel(self.root)
        win.title('How would you like to paste the item?')
        win.transient(self.root); win.grab_set(); win.resizable(False,False)
        frm=ttk.Frame(win,padding=16); frm.pack(fill='both',expand=True)
        ttk.Label(frm,text='How would you like to paste the clipboard content?',font=('Segoe UI',10,'bold')).pack(pady=(0,10))
        result={'value':None}
        def choose(v):
            result['value']=v; win.destroy()
        bf=ttk.Frame(frm); bf.pack(fill='x')
        bimg=ttk.Button(bf,text='Paste as Image',command=lambda:choose('image'))
        bimg.pack(side='left',padx=(0,8))
        btxt=ttk.Button(bf,text='Paste as Text',command=lambda:choose('text'))
        btxt.pack(side='left',padx=(0,8))
        ttk.Button(bf,text='Cancel',command=win.destroy).pack(side='left')
        if not has_image:
            bimg.state(['disabled'])
        if not has_text:
            btxt.state(['disabled'])
        info=[]
        if has_image: info.append('• image is available')
        if has_text: info.append('• text is available')
        ttk.Label(frm,text='\n'.join(info),justify='left').pack(anchor='w',pady=(10,0))
        win.wait_window()
        return result['value']

    def paste_selection(self):
        """V68: nalepi na TAČNO mesto koje je korisnik kliknuo. Podržava našu internu memoriju, tekst i slike iz Windows clipboard-a."""
        if self.page_img is None:
            return
        if self.paste_target is None:
            # Omogućava i Ctrl+V direktno: prvo se izabere mesto klikom.
            self._enter_paste_target_mode()
            messagebox.showinfo(TITLE,'First click where you want to paste the item, then click “Paste”.')
            return
        x,y=self.paste_target
        # Ako postoji interna memorija (Kopiraj/Iseci iz editora), koristi nju.
        # Ako je nema, čitaj Windows clipboard – uključujući slike iz drugih programa.
        if self.clipboard_source == 'internal' and (self.clipboard_image is not None or self.clipboard_text):
            img=self.clipboard_image
            text_value=self.clipboard_text
        else:
            img=None
            text_value=None
            ext_text,ext_img=self._read_system_clipboard()
            text_value=ext_text
            img=ext_img
        if img is None and not text_value:
            messagebox.showinfo(TITLE,'The clipboard does not contain supported text or image content.')
            return

        paste_kind=self._ask_paste_type(text_value=text_value,img=img)
        if paste_kind is None:
            return
        if paste_kind=='text':
            # Tekst iz Word-a, Excel-a, PDF-a, browsera itd. ide kroz postojeći
            # dijalog Dodaj tekst, sada sa višelinijskim poljem.
            self.clipboard_text=text_value
            self.canvas.delete('paste_target')
            self.paste_target=None
            self._add_text_dialog(x,y,prefill=text_value)
            return
        base=(self._current_view_source() or self.page_img).copy().convert('RGB')
        w,h=img.size
        nx0=max(0,min(int(x),base.width-w)); ny0=max(0,min(int(y),base.height-h))
        rect=(nx0,ny0,nx0+w,ny0+h)
        previous=self.result.copy() if self.result is not None else self.page_img.copy()
        self.undo_stack.append(previous); self.redo_stack.clear()
        base.paste(img,(nx0,ny0))
        self.result=base
        self.move_rect=rect
        self.added_text_info=None
        self.show_image(base,keep_scale=True)
        self.mode='move'; self.canvas.config(cursor='crosshair')
        self.canvas.delete('paste_target'); self.canvas.delete('add_text_sel')
        self._draw_move_rect()
        self.paste_target=None
        self.info.set('The item was pasted at the selected location. Use the blue frame to move or resize it.')

    def delete_move_selection(self):
        # V46: može se obrisati i odmah nakon prvog plavog označavanja,
        # čak i kada dokument još nema result sloj. Tada se radi nad page_img.
        if not self.move_rect or self.page_img is None:
            messagebox.showinfo(TITLE,'First click “Move Items” and select the item with the blue frame.')
            return
        base=self.result.copy() if self.result is not None else self.page_img.copy()
        previous=base.copy()
        final=self._erase(base.convert('RGBA'),tuple(self.move_rect)).convert('RGB')
        self.undo_stack.append(previous); self.redo_stack.clear(); self.result=final
        self.move_rect=None; self.move_action=None; self.transform_base=None; self.transform_src_rect=None
        self.added_text_info=None
        self.show_image(final,keep_scale=True)
        self.info.set('The selected item was deleted. Undo restores it.')

    def resize_move_selection_dialog(self):
        """Numerički promeni širinu/visinu plavog selektovanog područja u mm.
        Podatak se skalira na novu dimenziju; gornji levi ugao ostaje na istom mestu.
        Renderovana stranica je 150 DPI, pa je konverzija 150 px / 25.4 mm.
        """
        if self.mode!='move' or not self.move_rect or self.page_img is None:
            messagebox.showinfo(TITLE,
                'First click “Move Items” and select the item with the blue frame.')
            return
        from tkinter import simpledialog
        x0,y0,x1,y1=self.move_rect
        px_per_mm=150.0/25.4
        cur_w_mm=(x1-x0)/px_per_mm
        cur_h_mm=(y1-y0)/px_per_mm
        w=simpledialog.askstring(
            'Resize',
            f'Current width: {cur_w_mm:.2f} mm\n\nEnter NEW width in mm:',
            initialvalue=f'{cur_w_mm:.2f}', parent=self.root)
        if w is None: return
        h=simpledialog.askstring(
            'Resize',
            f'Current height: {cur_h_mm:.2f} mm\n\nEnter NEW height in mm:',
            initialvalue=f'{cur_h_mm:.2f}', parent=self.root)
        if h is None: return
        try:
            wmm=float(w.replace(',','.'))
            hmm=float(h.replace(',','.'))
        except ValueError:
            messagebox.showwarning(TITLE,'Width and height must be numbers.')
            return
        if wmm<=0 or hmm<=0:
            messagebox.showwarning(TITLE,'Width and height must be greater than 0 mm.')
            return
        nw=max(3,int(round(wmm*px_per_mm)))
        nh=max(3,int(round(hmm*px_per_mm)))
        if nw>self.page_img.width or nh>self.page_img.height:
            messagebox.showwarning(TITLE,'The entered size is larger than the document page.')
            return
        # Zadrži gornji levi ugao; ako bi nova veličina izašla van stranice,
        # pomeri početak samo koliko je potrebno da ceo podatak ostane na strani.
        nx0=min(x0,max(0,self.page_img.width-nw))
        ny0=min(y0,max(0,self.page_img.height-nh))
        newrect=(int(nx0),int(ny0),int(nx0+nw),int(ny0+nh))
        src=self._current_view_source() or self.page_img
        previous=self.result.copy() if self.result is not None else self.page_img.copy()
        final=self._transform_image(src.copy(),tuple(self.move_rect),newrect)
        self.undo_stack.append(previous); self.redo_stack.clear()
        self.result=final; self.move_rect=newrect
        if self.added_text_info is not None:
            self.added_text_info['rect']=tuple(newrect)
        self.show_image(final,keep_scale=True)
        self._draw_move_rect()
        self.info.set(f'Size changed to {wmm:.2f} × {hmm:.2f} mm. The blue frame remains active.')

    def move_selection_by(self,dx,dy):
        if not self.move_rect or self.page_img is None or self.mode!='move':return
        x0,y0,x1,y1=self.move_rect; w=x1-x0; h=y1-y0
        src=self._current_view_source() or self.page_img
        nx0=max(0,min(src.width-w,x0+dx)); ny0=max(0,min(src.height-h,y0+dy))
        newrect=(int(nx0),int(ny0),int(nx0+w),int(ny0+h))
        if newrect==tuple(self.move_rect):return
        final=self._transform_image(src.copy(),tuple(self.move_rect),newrect)
        previous=self.result.copy() if self.result is not None else self.page_img.copy()
        self.undo_stack.append(previous); self.redo_stack.clear(); self.result=final; self.move_rect=newrect
        if self.added_text_info is not None:
            self.added_text_info['rect']=tuple(newrect)
        self.show_image(final,keep_scale=True)
        self._draw_move_rect()
        self.info.set('The item was moved with the arrow keys. One press = 1 pixel; Shift + Arrow = 10 pixels.')

    def on_key(self,e):
        if self.mode!='move' or not self.move_rect:return
        step=10 if (e.state & 0x0001) else 1
        key=e.keysym.lower()
        if key=='left': self.move_selection_by(-step,0)
        elif key=='right': self.move_selection_by(step,0)
        elif key=='up': self.move_selection_by(0,-step)
        elif key=='down': self.move_selection_by(0,step)
        else:return
        return 'break'

    def _segment_old_snapshots(self, crop, text):
        self._last_segment_boxes=[]
        """Return RAW image snippets for each expected character.
        OCR is used only to locate character boxes. The pixels inserted later
        always come from the original scan; no font is ever rendered.
        """
        text=text.strip()
        if not text:
            return []

        # 1) Best case: OCR gives one box per expected character. We only use
        # its coordinates; the snapshot itself is cropped from the scan.
        boxes=[]
        for lang in ('srp_latn+eng','eng'):
            try:
                raw=pytesseract.image_to_boxes(crop, lang=lang, config='--psm 7')
                H=crop.height; tmp=[]
                for line in raw.splitlines():
                    p=line.split()
                    if len(p)<5: continue
                    ch=norm_char(p[0])
                    try: x0,y0,x1,y1=map(int,p[1:5])
                    except Exception: continue
                    top=max(0,H-y1); bottom=min(H,H-y0)
                    if x1>x0 and bottom>top:
                        tmp.append((ch,x0,top,x1,bottom))
                tmp.sort(key=lambda b:b[1])
                if len(tmp)==len(text):
                    score=sum(norm_char(a)==norm_char(b) for a,b in zip(tmp,text))
                    if score >= max(1,len(text)-1):
                        boxes=tmp; break
            except Exception:
                pass

        if boxes:
            out=[]
            seg_boxes=[]
            for ch,x0,y0,x1,y1 in boxes:
                # Small fixed padding preserves the original glyph pixels,
                # including anti-aliasing, without capturing neighboring chars.
                px=max(1,int(round(crop.height*0.045)))
                py=max(1,int(round(crop.height*0.08)))
                xa=max(0,x0-px); xb=min(crop.width,x1+px)
                ya=max(0,y0-py); yb=min(crop.height,y1+py)
                out.append(crop.crop((xa,ya,xb,yb)).convert('RGB'))
                seg_boxes.append((xa,ya,xb,yb))
            self._last_segment_boxes=seg_boxes
            return out

        # 2) Fallback: connected components + vertical projection. This still
        # returns raw scan pixels and never creates a font.
        a=np.array(crop.convert('L'))
        bg=float(np.percentile(a,95))
        thr=int(max(110,min(235,bg-28)))
        mask=(a<thr).astype(np.uint8)*255
        num, labels, stats, cents=cv2.connectedComponentsWithStats(mask,8)
        comps=[]
        for i in range(1,num):
            x,y,w,h,area=stats[i]
            if area < max(3,int(crop.width*crop.height*0.00001)): continue
            if h < max(2,int(crop.height*0.15)): continue
            comps.append((x,y,w,h,area))
        comps.sort(key=lambda q:q[0])
        merged=[]
        for c in comps:
            x,y,w,h,area=c
            if merged:
                px,py,pw,ph,pa=merged[-1]
                gap=x-(px+pw)
                overlap=max(0,min(y+h,py+ph)-max(y,py))
                if gap <= max(2,int(crop.width*0.025)) and overlap >= 0.35*min(h,ph):
                    nx=min(px,x); ny=min(py,y); nr=max(px+pw,x+w); nb=max(py+ph,y+h)
                    merged[-1]=(nx,ny,nr-nx,nb-ny,pa+area); continue
            merged.append(c)
        comps=merged
        expected=len(text)
        if len(comps)!=expected:
            col=(mask>0).sum(axis=0)
            active=col>=max(1,int(crop.height*0.012))
            runs=[]; st=None
            for i,v in enumerate(active):
                if v and st is None: st=i
                elif not v and st is not None:
                    if i-st>=1:runs.append((st,i))
                    st=None
            if st is not None:runs.append((st,len(active)))
            mergedruns=[]
            for r in runs:
                if mergedruns and r[0]-mergedruns[-1][1] <= max(2,int(crop.width*0.012)):
                    mergedruns[-1]=(mergedruns[-1][0],r[1])
                else: mergedruns.append(r)
            if len(mergedruns)==expected:
                ys=np.where(mask>0)[0]
                yy0=int(ys.min()) if len(ys) else 0; yy1=int(ys.max()+1) if len(ys) else crop.height
                comps=[(x0,yy0,x1-x0,yy1-yy0,1) for x0,x1 in mergedruns]
        if len(comps)!=expected:
            return []
        out=[]
        seg_boxes=[]
        for x,y,w,h,_ in comps:
            pad_x=max(1,int(round(crop.height*0.045))); pad_y=max(1,int(round(crop.height*0.08)))
            xa=max(0,x-pad_x); xb=min(crop.width,x+w+pad_x)
            ya=max(0,y-pad_y); yb=min(crop.height,y+h+pad_y)
            out.append(crop.crop((xa,ya,xb,yb)).convert('RGB'))
            seg_boxes.append((xa,ya,xb,yb))
        self._last_segment_boxes=seg_boxes
        return out

    def extract_old(self):
        if self.page_img is None or not self.rect:
            messagebox.showwarning(TITLE,'First open a PDF and select the original item.')
            return
        old=self.old.get().strip()
        if not old:
            from tkinter import simpledialog
            old=simpledialog.askstring(TITLE, 'The program could not reliably recognize the original item.\nEnter the original item:', parent=self.root) or ''
            old=old.strip()
            if not old: return
            self.old.set(old)
        source=self._current_view_source() or self.page_img
        crop=source.crop(self.rect).convert('RGB')
        snaps=self._segment_old_snapshots(crop,old)
        if not snaps:
            messagebox.showwarning(TITLE,
                'The program could not split the original item into individual characters.\n\n'
                'Slightly enlarge the red rectangle so it covers the entire item, then try again.\n\n'
                'IMPORTANT: replacement characters are not retyped in a font. When a matching character is found, the actual image/snapshot from the scan is used.')
            return
        self.char_samples={}
        for ch,snap in zip(old,snaps):
            self.char_samples.setdefault(ch,[]).append(snap)
        # V15: novi podatak se unosi tek sada, u jednom dijalogu.
        from tkinter import simpledialog
        new=simpledialog.askstring(TITLE,'Enter the NEW ITEM:',parent=self.root) or ''
        new=new.strip()
        if not new:
            self.info.set('Character snapshots were found. The new item has not been entered.')
            return
        self.new.set(new)
        self._ask_missing(new)

    def _ask_missing(self,new):
        missing=[]
        for ch in new:
            if ch not in self.char_samples:
                if ch not in missing: missing.append(ch)
        if missing:
            self.missing=missing; self.missing_i=0; self.set_mode('missing')
        else:
            self.info.set('All required character snapshots are available. The program is creating a preview.')
            self.preview()

    def _transparent_snapshot(self,snap):
        """Make paper background transparent while preserving the scanned ink pixels."""
        a=np.array(snap.convert('RGB'))
        gray=cv2.cvtColor(a,cv2.COLOR_RGB2GRAY)
        # Estimate paper from brightest pixels. Keep all darker scan pixels intact.
        bg=float(np.percentile(gray,96))
        alpha=np.clip((bg-gray)*14.0,0,255).astype(np.uint8)
        alpha[gray>=bg-1]=0
        rgba=np.dstack([a,alpha]).astype(np.uint8)
        return Image.fromarray(rgba,'RGBA')

    def _ink_box(self,snap):
        """Tight bounding box around the actual dark scanned character.
        The selection rectangle/padding is never used as the character size.
        """
        a=np.array(snap.convert('RGB'))
        g=cv2.cvtColor(a,cv2.COLOR_RGB2GRAY)
        # The source is a black/gray scan on a light paper background. Use a
        # fixed, conservative threshold so the measured glyph height is stable
        # across different white margins in snapshots.
        mask=(g < 210)
        ys,xs=np.where(mask)
        if len(xs)==0:
            return (0,0,snap.width,snap.height)
        return (int(xs.min()),int(ys.min()),int(xs.max()+1),int(ys.max()+1))

    def _tight_glyph(self,snap):
        """Return only the real scanned ink, with no selection/padding."""
        b=self._ink_box(snap)
        return snap.crop(b).convert('RGB')

    def _compose(self,base,rect,text):
        """Replace using real pixel snapshots, matched to the OLD glyph size.

        The red rectangle only defines the area to erase. Character size comes
        from the actual ink bounding box of the original character(s). New
        characters are tight-cropped from their snapshots, scaled to the old
        character height, and placed on the old character's baseline/top.
        No font is rendered.
        """
        x0,y0,x1,y1=rect
        old=self.old.get()
        if not old or not text: return None

        chosen=[]
        for ch in text:
            arr=self.char_samples.get(ch)
            if not arr: return None
            chosen.append(arr[0])

        # Recover the old character slots from the ORIGINAL scan.
        old_slots=self._segment_old_snapshots(base.crop(rect).convert('RGB'),old)
        if len(old_slots)!=len(old):
            return None

        old_tight=[self._tight_glyph(s) for s in old_slots]
        old_boxes=[self._ink_box(s) for s in old_slots]
        old_h=[max(1,b[3]-b[1]) for b in old_boxes]

        layer=Image.new('RGBA',base.size,(0,0,0,0))

        if len(text)==len(old):
            # Same number of characters: each new glyph occupies the same
            # character position as its old counterpart. Its HEIGHT is exactly
            # the old glyph's ink height; its width follows the new snapshot's
            # own aspect ratio. This fixes 7 -> 0 (or any digit/letter change).
            # _last_segment_boxes contains the exact crop boxes (relative to
            # the selected red rectangle) used to make each original snapshot.
            # Use the ORIGINAL GLYPH POSITION as the anchor, not the red
            # rectangle. The red rectangle is only the erase area.
            seg_boxes=getattr(self,'_last_segment_boxes',[])
            for i,(old_snap,new_snap) in enumerate(zip(old_slots,chosen)):
                ob=self._ink_box(old_snap)
                old_g=self._tight_glyph(old_snap)
                new_g=self._tight_glyph(new_snap)
                target_h=old_h[i]
                scale=target_h/float(max(1,new_g.height))
                nw=max(1,int(round(new_g.width*scale)))
                rs=new_g.resize((nw,target_h),Image.Resampling.LANCZOS)

                if i < len(seg_boxes):
                    sx0,sy0,_,_=seg_boxes[i]
                    # Exact old ink box in page coordinates. Align the new
                    # character by its LEFT EDGE and BASELINE (bottom edge).
                    old_left=x0+sx0+ob[0]
                    old_bottom=y0+sy0+ob[3]
                    px=int(round(old_left))
                    py=int(round(old_bottom-target_h))
                else:
                    # Defensive fallback; normally the segment boxes are always
                    # available when old_slots were obtained above.
                    px=int(round(x0+ob[0]))
                    py=int(round(y0+ob[1]))
                layer.alpha_composite(self._snapshot_alpha(rs),(px,py))
        else:
            # Different character count: preserve the original glyph height
            # (median) and lay out the new snapshots proportionally inside the
            # original selected width. The font is still never rendered.
            target_h=int(round(float(np.median(old_h)))) if old_h else max(1,int((y1-y0)*0.5))
            items=[]
            for snap in chosen:
                g=self._tight_glyph(snap)
                sc=target_h/float(max(1,g.height))
                rs=g.resize((max(1,int(round(g.width*sc))),target_h),Image.Resampling.LANCZOS)
                items.append(self._snapshot_alpha(rs))
            gap=max(1,int(round(np.median([max(1,s.width//10) for s in old_slots]))))
            total=sum(i.width for i in items)+gap*max(0,len(items)-1)
            W=x1-x0
            if total>W:
                # Compress horizontally only as a last resort; never change
                # the vertical character height.
                factor=(W/max(1,total))*0.99
                items=[im.resize((max(1,int(round(im.width*factor))),im.height),Image.Resampling.LANCZOS) for im in items]
                gap=max(1,int(round(gap*factor)))
                total=sum(im.width for im in items)+gap*max(0,len(items)-1)
            x=x0+max(0,(W-total)//2)
            y=y0+max(0,((y1-y0)-target_h)//2)
            for im in items:
                layer.alpha_composite(im,(int(x),int(y)))
                x+=im.width+gap

        out=base.convert('RGBA')
        out=self._erase(out,rect)
        out.alpha_composite(layer)
        return out.convert('RGB')

    def _snapshot_alpha(self,snap):
        """Make paper transparent while preserving the original scan's ink pixels.
        Alpha follows darkness softly; no font or re-rendering is involved.
        """
        a=np.array(snap.convert('RGB'))
        gray=cv2.cvtColor(a,cv2.COLOR_RGB2GRAY).astype(np.float32)
        bg=float(np.percentile(gray,98))
        # Preserve dark/anti-aliased pixels; remove only near-paper pixels.
        alpha=np.clip((bg-gray)*9.0,0,255).astype(np.uint8)
        alpha[gray>=bg-1]=0
        rgba=np.dstack([a,alpha]).astype(np.uint8)
        return Image.fromarray(rgba,'RGBA')

    def _erase(self,base,rect):
        # Background estimate from a thin ring around the selection.
        arr=np.array(base.convert('RGB'))
        x0,y0,x1,y1=rect
        pad=max(3,int(min(x1-x0,y1-y0)*0.22))
        xa=max(0,x0-pad); ya=max(0,y0-pad); xb=min(base.width,x1+pad); yb=min(base.height,y1+pad)
        ring=arr[ya:yb,xa:xb].copy()
        mask=np.ones(ring.shape[:2],dtype=bool)
        mask[y0-ya:y1-ya,x0-xa:x1-xa]=False
        vals=ring[mask]
        if len(vals):
            bg=tuple(np.median(vals,axis=0).astype(np.uint8))
        else:bg=(255,255,255)
        # Slight blur of the sampled background avoids a hard-edged rectangle.
        patch=Image.new('RGB',(x1-x0,y1-y0),bg)
        base.paste(patch,(x0,y0))
        return base

    def preview(self):
        if not self.rect or self.page_img is None:
            messagebox.showwarning(TITLE,'Select the original item.')
            return
        old=self.old.get(); new=self.new.get()
        if not old or not new:
            messagebox.showwarning(TITLE,'Enter the original and replacement items.')
            return
        missing=[c for c in new if c not in self.char_samples]
        if missing:
            self.missing=list(dict.fromkeys(missing)); self.missing_i=0; self.set_mode('missing'); return
        base=self._current_view_source() or self.page_img
        result=self._compose(base.copy(),self.rect,new)
        if result is None:
            messagebox.showerror(TITLE,'A character snapshot is missing.')
            return
        # V16: pre svake nove zavrsene izmene sacuvaj trenutno stanje.
        # Ako je ovo prva izmena, prethodno stanje je originalna stranica.
        previous=(self.result.copy() if self.result is not None else self.page_img.copy())
        self.undo_stack.append(previous)
        self.redo_stack.clear()
        self.result=result
        # Keep the current zoom. The preview replaces the displayed image but
        # never resets the zoom level.
        self.show_image(result, keep_scale=True)
        self.info.set('The preview is ready. The replacement was assembled ONLY from images/snapshots in the document. If it looks correct, click “Save New PDF”.')


    def undo(self):
        """Vrati poslednju zavrsenu izmenu, bez menjanja originalnog PDF-a."""
        if not self.undo_stack:
            self.info.set('There is no change to undo.')
            return
        current=(self.result.copy() if self.result is not None else self.page_img.copy())
        self.redo_stack.append(current)
        previous=self.undo_stack.pop()
        # Kada je Undo stepen poslednji u istoriji, vraćamo se na originalnu stranicu.
        self.result=None if not self.undo_stack else previous
        src=self.page_img if self.result is None else self.result
        self.show_image(src, keep_scale=True)
        self.info.set('The last change was undone. Click “Redo” to restore it.')

    def redo(self):
        """Vrati poslednju poništenu izmenu."""
        if not self.redo_stack:
            self.info.set('There is no change to redo.')
            return
        current=(self.result.copy() if self.result is not None else self.page_img.copy())
        self.undo_stack.append(current)
        nxt=self.redo_stack.pop()
        # Redo states are always edited states in normal use.
        self.result=nxt
        self.show_image(self.result, keep_scale=True)
        self.info.set('The change was restored. You can continue editing.')

    def save(self):
        if self.result is None:
            messagebox.showwarning(TITLE,'Create a preview first.')
            return
        out=filedialog.asksaveasfilename(defaultextension='.pdf',filetypes=[('PDF','*.pdf')],initialfile='PDF_izmenjen.pdf')
        if not out:return
        try:
            src=fitz.open(self.path)
            page=src[self.page_index]
            # self.result is the cumulative 150-DPI rendered page.
            # Save exactly that cumulative image, so earlier replacements
            # cannot be lost when another character is changed.
            dpi=300
            hi=self.result.resize((self.result.width*2,self.result.height*2),Image.Resampling.LANCZOS)
            tmp=os.path.join(tempfile.gettempdir(),'pdf_podatak_cumulative_v14.png')
            hi.save(tmp,'PNG')
            page.insert_image(page.rect,filename=tmp,overlay=True)
            src.save(out,garbage=4,deflate=True)
            src.close()
            try: os.remove(tmp)
            except: pass
            messagebox.showinfo(TITLE,'Saved to:\n'+out)
        except Exception as e:
            messagebox.showerror(TITLE,str(e))

    def clear_rect(self):
        """Obriši samo aktivni crveni okvir/selektovanu oblast.
        Ne poništava već napravljene izmene i ne menja Undo/Redo istoriju.
        """
        self.drag_start=None
        self.move_action=None; self.move_anchor=None; self.move_orig_rect=None
        self.transform_base=None; self.transform_src_rect=None
        self.canvas.delete('drag')
        self.canvas.delete('font_sel')
        self.rect=None
        self.font_rect=None
        self.font_action='preview'
        self.add_text_point=None
        self.move_rect=None
        self.old.set('')
        self.new.set('')
        self.set_mode('idle')
        if self.page_img is not None:
            if self.result is not None:
                self.show_image(self.result,keep_scale=True)
            else:
                self.show_image(self.page_img,keep_scale=True)
            self.info.set('Frames have been cleared. To replace content, use “Select Original Item”; to move content, use “Move Items”; to add text, use “Add Text”.')
        else:
            self.info.set('The red frame has been cleared.')

    def cancel_rect(self):
        self.drag_start=None
        self.canvas.delete('drag')


if __name__=='__main__':
    root=tk.Tk()
    try: ttk.Style().theme_use('vista')
    except Exception: pass
    App(root)
    root.mainloop()
