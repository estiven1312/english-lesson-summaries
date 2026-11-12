"""PDF preparation. PyMuPDF preferred; system Poppler is an optional fallback."""
from __future__ import annotations
import importlib.util
import math
import re
import shutil
import subprocess
from pathlib import Path


def backend():
    if importlib.util.find_spec('pymupdf'):
        return 'pymupdf'
    if all(shutil.which(x) for x in ('pdfinfo', 'pdftotext', 'pdftoppm')):
        return 'poppler'
    raise RuntimeError('Install requirements.txt (PyMuPDF), or install Poppler: pdfinfo, pdftotext, pdftoppm.')


def command(args):
    result = subprocess.run(args, capture_output=True, timeout=120, check=True)
    return result.stdout.decode('utf-8', errors='replace')


def prepare(pdf: Path, work: Path, cfg: dict):
    work.mkdir(parents=True, exist_ok=True)
    engine = backend()
    document = None
    if engine == 'pymupdf':
        import pymupdf
        document = pymupdf.open(pdf)
        if document.needs_pass:
            document.close()
            raise ValueError('Password-protected PDF: unlock a copy before adding it to Inbox.')
        count = len(document)
    else:
        info = command(['pdfinfo', str(pdf)])
        count = int(re.search(r'^Pages:\s+(\d+)', info, re.M)[1])
    images, pages, text_count = [], [], 0
    try:
        if not 0 < count <= cfg['max_pages']:
            raise ValueError(f'PDF has {count} pages; allowed maximum is {cfg["max_pages"]}. Split it first.')
        for number in range(1, count + 1):
            if document is not None:
                page = document[number - 1]
                text = page.get_text()
                width, height = page.rect.width, page.rect.height
            else:
                text = command(['pdftotext', '-f', str(number), '-l', str(number), '-layout', str(pdf), '-'])
                info = command(['pdfinfo', '-f', str(number), '-l', str(number), str(pdf)])
                match = re.search(r'(?:Page\s+\d+\s+size|Page size):\s*([\d.]+) x ([\d.]+)', info)
                if not match:
                    raise ValueError(f'Cannot determine dimensions for page {number}.')
                width, height = map(float, match.groups())
            text_count += len(text)
            if text_count > cfg['max_text_chars']:
                raise ValueError('PDF text exceeds max_text_chars; split the PDF. Nothing was truncated.')
            record = {'page': number, 'text': text.strip(), 'images': []}
            if len(re.sub(r'\s+', '', text)) < cfg['text_threshold']:
                target_width = cfg['image_width']
                target_height = math.ceil(height / width * target_width)
                step = cfg['image_tile_height'] - cfg['image_overlap']
                for y in range(0, target_height, step):
                    if len(images) >= cfg['max_images']:
                        raise ValueError('PDF exceeds max_images; split it or raise the configured limit. Nothing was truncated.')
                    tile_height = min(cfg['image_tile_height'], target_height - y)
                    output = work / f'page-{number:03d}-y-{y:06d}.png'
                    if document is not None:
                        scale = target_width / width
                        clip = pymupdf.Rect(0, y / scale, width, min(height, (y + tile_height) / scale))
                        page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), clip=clip, alpha=False).save(output)
                    else:
                        command(['pdftoppm', '-f', str(number), '-l', str(number), '-singlefile',
                                 '-scale-to-x', str(target_width), '-scale-to-y', '-1',
                                 '-x', '0', '-y', str(y), '-W', str(target_width), '-H', str(tile_height),
                                 '-png', str(pdf), str(output.with_suffix(''))])
                    images.append(output)
                    record['images'].append(output.name)
                    if y + tile_height >= target_height:
                        break
            pages.append(record)
    finally:
        if document is not None:
            document.close()
    import json
    (work / 'pages.json').write_text(json.dumps(pages, ensure_ascii=False, indent=2), encoding='utf-8')
    return {'page_count': count, 'pages': pages, 'images': images, 'backend': engine}
