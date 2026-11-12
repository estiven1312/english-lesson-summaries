#!/usr/bin/env python3
"""Create smaller PDF distribution copies without modifying study originals."""
from __future__ import annotations
import argparse
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


def pdf_info(path):
    info = subprocess.run(['pdfinfo', '-box', str(path)],check=True,capture_output=True,text=True,timeout=60).stdout
    pages = int(re.search(r'^Pages:\s+(\d+)',info,re.M)[1])
    sizes = subprocess.run(['pdfinfo','-f','1','-l',str(pages),str(path)],check=True,
                           capture_output=True,text=True,timeout=60).stdout
    dimensions = re.findall(r'(?:Page\s+\d+\s+size|Page size):\s*([\d.]+) x ([\d.]+)',sizes)
    text = subprocess.run(['pdftotext','-layout',str(path),'-'],check=True,capture_output=True,
                          timeout=60).stdout
    return pages, dimensions, b' '.join(text.split())


def ghostscript():
    return next((x for name in ('gs','gswin64c','gswin32c') if (x := shutil.which(name))),None)


def compress_pdf(source: Path, target: Path, quality=90, dpi=220):
    """Keep the original if recompression grows it or changes page geometry/text."""
    if dpi < 150:
        raise ValueError('Use at least 150 DPI to keep screenshot text readable')
    if not 1 <= quality <= 100:
        raise ValueError('JPEG quality must be from 1 to 100')
    if source.resolve() == target.resolve():
        raise ValueError('Output must be a separate distribution copy, never the original')
    target.parent.mkdir(parents=True,exist_ok=True)
    before = source.stat().st_size
    report = {'original_bytes':before,'download_bytes':before,'status':'original-copy'}
    gs = ghostscript()
    if gs and all(shutil.which(x) for x in ('pdfinfo','pdftotext')):
        with tempfile.TemporaryDirectory(prefix='pdf-compress-') as directory:
            candidate = Path(directory)/'candidate.pdf'
            args = [gs,'-q','-dSAFER','-dBATCH','-dNOPAUSE','-sDEVICE=pdfwrite',
                    '-dCompatibilityLevel=1.6','-dAutoRotatePages=/None',
                    '-dDetectDuplicateImages=true','-dCompressFonts=true',
                    '-dDownsampleColorImages=true','-dDownsampleGrayImages=true','-dDownsampleMonoImages=false',
                    '-dColorImageDownsampleType=/Bicubic','-dGrayImageDownsampleType=/Bicubic',
                    f'-dColorImageResolution={dpi}',f'-dGrayImageResolution={dpi}',
                    '-dAutoFilterColorImages=false','-dColorImageFilter=/DCTEncode',
                    '-dAutoFilterGrayImages=false','-dGrayImageFilter=/DCTEncode',
                    f'-dJPEGQ={quality}',f'-sOutputFile={candidate}',str(source.resolve())]
            try:
                subprocess.run(args,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=300)
                if candidate.stat().st_size < before * .98:
                    if pdf_info(source) != pdf_info(candidate):
                        raise ValueError('Compressed PDF changed page count, dimensions, or extracted text')
                    shutil.copyfile(candidate,target)
                    report.update(download_bytes=target.stat().st_size,status='compressed')
                    return report
                report['status'] = 'kept-original-smaller'
            except (subprocess.SubprocessError,ValueError,OSError) as exc:
                report['status'] = 'kept-original-validation-or-compression-failed'
                report['detail'] = str(exc)
    else:
        report['status'] = 'kept-original-tools-unavailable'
    shutil.copyfile(source,target)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,default=Path('content/PDFs'))
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--quality',type=int,default=90)
    parser.add_argument('--dpi',type=int,default=220)
    args = parser.parse_args()
    if args.output.resolve().is_relative_to(args.input.resolve()):
        parser.error('Output must not be inside the input directory')
    reports = {}
    for source in sorted(args.input.rglob('*')):
        if source.suffix.lower()=='.pdf' and source.is_file() and not source.is_symlink():
            reports[source.relative_to(args.input).as_posix()] = compress_pdf(source,args.output/source.relative_to(args.input),args.quality,args.dpi)
    print(json.dumps(reports,indent=2))


if __name__=='__main__':main()
