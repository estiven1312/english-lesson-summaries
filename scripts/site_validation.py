"""Check built-site navigation, anchors, assets, and local PDF download links."""
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


class HTMLDocument(HTMLParser):
    def __init__(self,text):
        super().__init__();self.ids=set();self.links=[]
        self.feed(text)

    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if 'id' in attrs:self.ids.add(attrs['id'])
        for name in ('href','src'):
            if name in attrs:self.links.append((attrs[name],tag,attrs))


def validate_site(output: Path):
    output=output.resolve()
    documents={p.resolve():HTMLDocument(p.read_text(encoding='utf-8')) for p in output.rglob('*.html')}
    errors=[];checked=0;downloads=0
    for page,document in documents.items():
        for url,tag,attrs in document.links:
            parts=urlsplit(url)
            if parts.scheme or parts.netloc:continue
            checked+=1
            if parts.path.startswith('/'):
                errors.append(f'{page.name}: root-relative URL breaks project sites: {url}');continue
            target=(page.parent/unquote(parts.path)).resolve() if parts.path else page
            if not target.is_relative_to(output) or not target.is_file():
                errors.append(f'{page.name}: missing published file: {url}');continue
            if parts.fragment and target in documents and unquote(parts.fragment) not in documents[target].ids:
                errors.append(f'{page.name}: missing heading: {url}')
            if target.suffix.lower()=='.pdf' and tag=='a':
                downloads+=1
                if 'download' not in attrs or parts.fragment:
                    errors.append(f'{page.name}: PDF must have download attribute and no fragment: {url}')
    if errors:raise ValueError('Website link validation failed:\n'+'\n'.join(errors))
    return {'html_pages':len(documents),'local_links':checked,'pdf_download_links':downloads}
