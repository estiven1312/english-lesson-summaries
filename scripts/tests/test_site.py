"""Static-site behavior tests; no network, AI calls, or Git changes."""
from __future__ import annotations

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch
from urllib.parse import unquote,urlsplit

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from build_site import build
from compress_pdfs import compress_pdf


class Document(HTMLParser):
    def __init__(self,text):
        super().__init__();self.ids=set();self.links=[];self.anchors=[];self.feed(text)
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if 'id' in attrs:self.ids.add(attrs['id'])
        for attr in ('href','src'):
            if attr in attrs:self.links.append(attrs[attr])
        if tag=='a':self.anchors.append(attrs)


def broken_links(output):
    pages={p:Document(p.read_text()) for p in output.rglob('*.html')}
    errors=[]
    for page,doc in pages.items():
        for link in doc.links:
            parts=urlsplit(link)
            if parts.scheme or parts.netloc:continue
            target=(page.parent/unquote(parts.path)).resolve() if parts.path else page
            if not target.is_relative_to(output.resolve()) or not target.exists():errors.append((page,link,'file'))
            elif parts.fragment and target in pages and unquote(parts.fragment) not in pages[target].ids:
                errors.append((page,link,'fragment'))
    return errors


class SiteTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='english site spaces ')
        self.root=Path(self.temp.name)
        self.notes=self.root/'content/Obsidian English';self.notes.mkdir(parents=True)
        self.pdfs=self.root/'content/PDFs/Grammar';self.pdfs.mkdir(parents=True)
        (self.pdfs/'Lesson source.pdf').write_bytes(b'%PDF-1.4\nfixture, not rendered\n')
        (self.notes/'Grammar.md').write_text('# Grammar\n\n## Use it\n\nA useful pattern.\n\n## Examples\n\nAn example.\n')
        (self.notes/'Practice.md').write_text('''---
tags: [english]
---
# Practice

[[Grammar#Use it|Review grammar]]. [[PDFs/Grammar/Lesson source.pdf#page=1|PDF]].

| Topic | Lesson |
| --- | --- |
| Test | [[Grammar|Study this]] |

## Questions

Complete the sentence: ______.

## Answers

Use the past form.
''')
        self.cfg={'title':'Test notebook','tagline':'Practise English.','notes':'content/Obsidian English',
                  'pdfs':'content/PDFs','output':'dist','compress_pdfs':False,'jpeg_quality':90}

    def tearDown(self):self.temp.cleanup()

    def run_build(self):
        with redirect_stdout(io.StringIO()):return build(self.root,self.cfg)

    def test_real_build_resolves_note_pdf_and_heading_links(self):
        result=self.run_build();self.assertEqual(broken_links(result['output']),[])
        self.assertEqual(len(list(result['output'].rglob('*.html'))),4)

    def test_every_pdf_anchor_downloads_from_same_origin_without_fragment(self):
        result=self.run_build();count=0
        for page in result['output'].rglob('*.html'):
            for anchor in Document(page.read_text()).anchors:
                href=anchor.get('href','')
                if urlsplit(href).path.endswith('.pdf'):
                    count+=1;self.assertIn('download',anchor);self.assertNotIn('#',href)
                    self.assertFalse(urlsplit(href).scheme)
        self.assertGreaterEqual(count,2)

    def test_answers_are_in_collapsible_final_section(self):
        result=self.run_build();note=next(n for n in result['notes'] if n['title']=='Practice')
        text=(result['output']/note['route']).read_text()
        before,answers=text.split('<details class="answer-key">')
        self.assertNotIn('Use the past form.',before);self.assertIn('Use the past form.',answers)
        self.assertIn('<summary>Show answers and explanations</summary>',answers)

    def test_tables_preserve_obsidian_aliases(self):
        result=self.run_build();note=next(n for n in result['notes'] if n['title']=='Practice')
        text=(result['output']/note['route']).read_text()
        self.assertIn('>Study this</a>',text)
        self.assertIn('<div class="table-scroll"><table>',text)
        self.assertNotIn('[[Grammar',text)

    def test_private_and_inbox_content_never_enters_site(self):
        for relative in ['content/Inbox/new.pdf','content/Duplicates/copy.pdf','content/.obsidian/workspace.json',
                         'config/state/secret.txt','content/Obsidian English/.private/hidden.md']:
            path=self.root/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('PRIVATE_SENTINEL')
        result=self.run_build()
        self.assertEqual(len(result['pdfs']),1)
        self.assertFalse(any('PRIVATE_SENTINEL' in p.read_text(errors='ignore') for p in result['output'].rglob('*') if p.is_file()))

    def test_broken_link_fails_before_replacing_last_good_site(self):
        result=self.run_build();original=(result['output']/'index.html').read_bytes()
        (self.notes/'Grammar.md').write_text('# Grammar\n\n[[Missing Topic]]')
        with self.assertRaisesRegex(ValueError,'Broken or ambiguous'):self.run_build()
        self.assertEqual((result['output']/'index.html').read_bytes(),original)

    def test_does_not_delete_non_generated_output_directory(self):
        output=self.root/'dist';output.mkdir();(output/'personal.txt').write_text('keep me')
        with self.assertRaisesRegex(ValueError,'Refusing'):self.run_build()
        self.assertEqual((output/'personal.txt').read_text(),'keep me')

    def test_refuses_content_as_output(self):
        self.cfg['output']='content'
        with self.assertRaisesRegex(ValueError,'separate build'):self.run_build()

    def test_code_examples_do_not_resolve_wiki_syntax(self):
        (self.notes/'Grammar.md').write_text('# Grammar\n\n## Use it\n\n`[[Not a note]]`\n\n```text\n| [[Not a note|alias]] |\n```')
        result=self.run_build();note=next(n for n in result['notes'] if n['title']=='Grammar')
        text=(result['output']/note['route']).read_text()
        self.assertIn('[[Not a note|alias]]',text)

    def test_raw_html_is_escaped(self):
        (self.notes/'Grammar.md').write_text('# Grammar\n\n## Use it\n\n<script>alert("unsafe")</script>')
        result=self.run_build();note=next(n for n in result['notes'] if n['title']=='Grammar')
        text=(result['output']/note['route']).read_text()
        self.assertNotIn('<script>alert',text);self.assertIn('&lt;script&gt;',text)

    def test_ambiguous_imported_titles_need_explicit_paths(self):
        for folder in ('one','two'):
            path=self.notes/'Imported'/folder/'Lesson.md';path.parent.mkdir(parents=True);path.write_text('# Lesson\n')
        (self.notes/'Grammar.md').write_text('# Grammar\n\n[[Lesson]]')
        with self.assertRaisesRegex(ValueError,'ambiguous'):self.run_build()

    def test_compression_fallback_preserves_source_bytes(self):
        source=self.pdfs/'Lesson source.pdf';before=source.read_bytes();target=self.root/'copy.pdf'
        with patch('compress_pdfs.ghostscript',return_value=None):report=compress_pdf(source,target)
        self.assertEqual(target.read_bytes(),before);self.assertEqual(source.read_bytes(),before)
        self.assertEqual(report['status'],'kept-original-tools-unavailable')

    def test_compression_rejects_in_place_rewrite(self):
        source=self.pdfs/'Lesson source.pdf'
        with self.assertRaises(ValueError):compress_pdf(source,source)

    def test_compression_rejects_changed_text_or_geometry(self):
        source=self.pdfs/'Lesson source.pdf';source.write_bytes(b'x'*1000);target=self.root/'copy.pdf'
        def fake_gs(args,**kwargs):
            output=next(x.split('=',1)[1] for x in args if x.startswith('-sOutputFile='))
            Path(output).write_bytes(b'y'*100)
        with patch('compress_pdfs.ghostscript',return_value='gs'),patch('compress_pdfs.shutil.which',return_value='tool'),patch('compress_pdfs.subprocess.run',side_effect=fake_gs),patch('compress_pdfs.pdf_info',side_effect=[(1,[],b'original'),(1,[],b'changed')]):
            report=compress_pdf(source,target)
        self.assertEqual(target.read_bytes(),source.read_bytes())
        self.assertEqual(report['status'],'kept-original-validation-or-compression-failed')


if __name__=='__main__':unittest.main()
