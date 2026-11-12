#!/usr/bin/env python3
"""Build a static GitHub Pages site from explicitly allowed vault notes and PDFs."""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import hashlib
import html
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
import tomllib
import unicodedata
from urllib.parse import quote, unquote, urlsplit

from markdown_it import MarkdownIt
from compress_pdfs import compress_pdf
from site_validation import validate_site

ROOT = Path(__file__).resolve().parents[1]


def escape(value):return html.escape(str(value),quote=True)


def slug(value):
    ascii_text = unicodedata.normalize('NFKD',value).encode('ascii','ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+','-',ascii_text).strip('-') or 'lesson'


def heading_id(value):
    return re.sub(r'\s+','-',re.sub(r'[^\w\s-]','',value.lower())).strip('-')


def split_frontmatter(text):
    if text.startswith('---\n'):
        end = text.find('\n---',4)
        if end != -1:return text[end+4:].lstrip('\r\n')
    return text


def markdown_source(text):
    # Obsidian allows alias pipes inside table cells; CommonMark needs them escaped.
    result=[];fence=None
    for line in text.splitlines():
        marker=re.match(r'^ {0,3}(`{3,}|~{3,})',line)
        if marker:
            if fence is None:fence=marker[1]
            elif marker[1][0]==fence[0] and len(marker[1])>=len(fence):fence=None
            result.append(line);continue
        if fence is None:
            line=re.sub(r'^> \[!(\w+)\](.*)$',lambda m:'> **'+m[1].capitalize()+':'+m[2]+'**',line)
            if re.match(r'^ {0,3}\|',line):
                line=re.sub(r'\[\[[^\]\n]+\]\]',lambda m:m[0].replace('\\|','|').replace('|','\\|'),line)
        result.append(line)
    return '\n'.join(result)


def headings(body):
    tokens = MarkdownIt('commonmark').enable('table').parse(markdown_source(body))
    output,counts = {},Counter()
    for i,token in enumerate(tokens):
        if token.type=='heading_open':
            name=tokens[i+1].content;identifier=heading_id(name)
            suffix=counts[identifier];counts[identifier]+=1
            identifier += f'-{suffix}' if suffix else ''
            output.setdefault(name,identifier)
    return output


def classify(path,title):
    lower=title.lower()
    if 'exercise' in lower or 'practice' in lower:return 'practice'
    if 'ielts' in lower or 'idiom' in lower:return 'ielts'
    if 'rhetorical' in lower or 'presenting' in lower or 'team agreements' in lower:return 'speaking'
    if 'home' in lower or 'sources' in lower or 'imported lessons' in lower or 'connections' in lower:return 'library'
    return 'grammar'


DESCRIPTIONS={
 'Phrasal Verbs':'Get the meaning and word order right: turn it off, go over it, and look forward to joining.',
 'Passive Voice':'Focus on the action. Build passive sentences across tenses and with modal verbs.',
 'Modal Verbs':'Express possibility, expectation, advice, and polite requests with the right degree of confidence.',
 'Gerunds and Infinitives':'Choose work, to work, or working by understanding the pattern before it.',
 'Verb Complements and Cause and Result':'Explain what helps, enables, causes, or prevents an action.',
 'Rhetorical Questions':'Use question forms to express doubt, suggest a change, or make a point.',
 'IELTS Common Expressions':'Study 48 expressions with meanings, grammatical patterns, and fresh examples.',
 'Grammar Practice':'Test your grammar with choices, rewrites, corrections, and explained answers.',
 'English Grammar Home':'Your starting point for the connected English grammar collection.',
 'PDF Exercise Index':'Find the exercises from each lesson, with all answers at the end.'}


def collect(root,cfg):
    vault=root/'content'
    notes_dir=root/cfg['notes'];pdf_dir=root/cfg['pdfs']
    for path in (notes_dir,pdf_dir):
        if not path.resolve().is_relative_to(vault.resolve()) or not path.is_dir():
            raise ValueError('Published input folders must exist inside content/')
    notes=[]
    for path in sorted(notes_dir.rglob('*.md')):
        if path.is_symlink() or any(part.startswith('.') for part in path.relative_to(notes_dir).parts):continue
        body=split_frontmatter(path.read_text(encoding='utf-8'))
        title_match=re.search(r'^# (.+)$',body,re.M)
        title=title_match[1] if title_match else path.stem
        relative=path.relative_to(vault).as_posix()
        route='notes/'+slug(path.stem)+'--'+hashlib.sha256(relative.encode()).hexdigest()[:8]+'.html'
        plain=re.sub(r'\[\[([^\]|]+)(?:\|([^\]]+))?\]\]',lambda m:m[2] or m[1],body)
        plain=re.sub(r'[#*_`>\[\]|]',' ',plain)
        plain=' '.join(plain.split())
        summary=DESCRIPTIONS.get(title,plain[len(title):].strip()[:150].rsplit(' ',1)[0]+'…')
        notes.append({'path':path,'relative':relative,'route':route,'title':title,'body':body,
                      'category':classify(path,title),'summary':summary,'search':(title+' '+plain).lower(),
                      'headings':headings(body),'minutes':max(1,round(len(body.split())/200))})
    pdfs=[]
    for path in sorted(pdf_dir.rglob('*')):
        if path.suffix.lower()!='.pdf' or not path.is_file() or path.is_symlink():continue
        relative=path.relative_to(vault).as_posix()
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        route='downloads/'+slug(path.stem)+'--'+digest[:12]+'.pdf'
        title=re.sub(r'--[a-f0-9]{12}$','',path.stem).replace('-',' ') if re.search(r'--[a-f0-9]{12}$',path.stem) else path.stem
        pdfs.append({'path':path,'relative':relative,'route':route,'title':title,
                     'category':path.relative_to(pdf_dir).parts[0],'download':path.name})
    if not notes:raise ValueError('No Markdown notes found')
    return notes,pdfs


class Links:
    def __init__(self,notes,pdfs):
        self.full={item['relative']:item for item in notes+pdfs}
        self.short=defaultdict(list)
        for item in notes+pdfs:
            path=PurePosixPath(item['relative'])
            self.short[path.name].append(item)
            if path.suffix=='.md':self.short[path.stem].append(item)
        self.notes=notes;self.pdfs=pdfs

    def resolve(self,target,current):
        raw,_,anchor=target.partition('#');raw=unquote(raw)
        item=None
        if not raw:item=current
        else:
            relative=str(PurePosixPath(current['relative']).parent/raw)
            for candidate in (relative,relative+'.md',raw,raw+'.md'):
                if candidate in self.full:item=self.full[candidate];break
            if item is None:
                matches=self.short.get(raw,[])
                if len(matches)==1:item=matches[0]
        if item is None:raise ValueError(f'Broken or ambiguous vault link in {current["relative"]}: {target}')
        url='../'+item['route']
        if item['route'].endswith('.pdf'):
            # A PDF fragment can cause navigation instead of download in some browsers; omit it.
            return {'href':quote(url,safe='/-._~'),'download':item['download'],
                    'class':'pdf-link','aria-label':'Download PDF: '+item['title']}
        if anchor:
            anchor=unquote(anchor)
            identifier=item['headings'].get(anchor)
            if identifier is None and anchor in item['headings'].values():identifier=anchor
            if identifier is None:raise ValueError(f'Unknown heading in {current["relative"]}: {target}')
            url+='#'+identifier
        return {'href':quote(url,safe='/-._~#')}


def render_note(note,links):
    md=MarkdownIt('commonmark',{'html':False,'linkify':False}).enable('table')
    def wiki(state,silent):
        pos=state.pos
        start=pos+1 if state.src.startswith('![[',pos) else pos
        if not state.src.startswith('[[',start):return False
        end=state.src.find(']]',start+2)
        if end<0:return False
        value=state.src[start+2:end]
        target,sep,label=value.partition('|')
        attrs=links.resolve(target,note)
        if not silent:
            token=state.push('link_open','a',1);token.attrs=attrs;token.meta['site_resolved']=True
            text=state.push('text','',0);text.content=label if sep else target.split('#')[0] or target.lstrip('#')
            state.push('link_close','a',-1)
            state.pos=end+2
        return True
    md.inline.ruler.before('link','wikilink',wiki)
    default_link=md.renderer.rules.get('link_open')
    def link_open(tokens,idx,options,env):
        token=tokens[idx]
        if not token.meta.get('site_resolved'):
            href=token.attrGet('href') or ''
            if not urlsplit(href).scheme and not href.startswith('//'):
                for key,value in links.resolve(href,note).items():token.attrSet(key,value)
        if default_link:return default_link(tokens,idx,options,env)
        return md.renderer.renderToken(tokens,idx,options,env)
    md.renderer.rules['link_open']=link_open
    tokens=md.parse(markdown_source(note['body']))
    counts=Counter();toc=[]
    for i,token in enumerate(tokens):
        if token.type=='heading_open':
            name=tokens[i+1].content;identifier=heading_id(name)
            suffix=counts[identifier];counts[identifier]+=1
            identifier+=f'-{suffix}' if suffix else ''
            token.attrSet('id',identifier)
            if token.tag=='h2':toc.append((name,identifier))
        elif token.type=='inline':
            for child in token.children or []:
                if child.type=='image':raise ValueError(f'Image attachments are not in the publishing allowlist: {note["relative"]}')
    rendered=md.renderer.render(tokens,md.options,{})
    rendered=rendered.replace('<table>','<div class="table-scroll"><table>').replace('</table>','</table></div>')
    answer=re.search(r'<h2 id="answers(?:-and-explanations)?">',rendered)
    if answer:
        end=rendered.find('<h2 ',answer.end())
        if end==-1:end=len(rendered)
        rendered=rendered[:answer.start()]+'<details class="answer-key"><summary>Show answers and explanations</summary>'+rendered[answer.start():end]+'</details>'+rendered[end:]
    toc_html='<details class="toc"><summary>On this page</summary><ul>'+''.join(f'<li><a href="#{escape(identifier)}">{escape(name)}</a></li>' for name,identifier in toc)+'</ul></details>' if toc else ''
    # Place the table of contents after the title rather than above it.
    rendered=re.sub(r'(</h1>)',lambda m:m[1]+toc_html,rendered,count=1)
    return rendered


def page(title,main,cfg,prefix=''):
    brand=escape(cfg['title'])
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="English grammar notes, examples, practice, and downloadable lesson PDFs.">
<title>{escape(title)} · {brand}</title><link rel="stylesheet" href="{prefix}assets/site.css"><script src="{prefix}assets/site.js" defer></script></head>
<body><a class="skip" href="#main">Skip to content</a><header class="header"><a class="brand" href="{prefix}index.html"><span class="brand-mark">D</span>{brand.upper()}</a>
<nav class="nav" aria-label="Main"><a href="{prefix}index.html#library">Library</a><a href="{prefix}index.html?category=practice#library">Practice</a><a href="{prefix}downloads.html">PDFs ↓</a></nav></header>
{main}<footer class="footer"><span>{brand} / {escape(cfg['tagline'])}</span><span>Read. Connect. Put it into practice.</span></footer></body></html>'''


def size(value):return f'{value/1_000_000:.2f} MB' if value>=1_000_000 else f'{value/1000:.0f} KB'


def home(notes,pdfs,reports,cfg):
    preferred=['Phrasal Verbs','Passive Voice','Modal Verbs','Gerunds and Infinitives','Verb Complements and Cause and Result','Rhetorical Questions','IELTS Common Expressions']
    ordered=sorted(notes,key=lambda n:(preferred.index(n['title']) if n['title'] in preferred else 100,n['title']))
    cards=''
    for note in ordered:
        cards+=f'''<a class="card" href="{note['route']}" data-card data-category="{note['category']}" data-search="{escape(note['search'])}">
<span class="badge {note['category']}">{note['category']}</span><h3>{escape(note['title'])}</h3><p>{escape(note['summary'])}</p><div class="card-tail"><span>{note['minutes']} min read</span><span class="arrow" aria-hidden="true">↗</span></div></a>'''
    total=sum(r['download_bytes'] for r in reports.values())
    return page('Your English library',f'''<main id="main" class="shell"><section class="hero"><div><p class="eyebrow">Your English notebook</p><h1>A little practice.<br>A <span>clearer sentence.</span></h1><p>Grammar you can use, examples that make it click, and connections that help it stay with you.</p></div>
<aside class="hero-aside" aria-label="Grammar example"><p class="eyebrow">A pattern worth keeping</p><div class="sample-label">PHRASAL VERBS / WORD ORDER</div><div class="sample-sentence">Turn <mark>the notifications</mark> off.<br>Turn <mark>them</mark> off.</div><p class="sample-caption">A small change in wording.<br>The same idea, made natural.</p></aside></section>
<div class="stats"><div><strong>{len(notes):02d}</strong>connected notes</div><div><strong>{len(pdfs):02d}</strong>lesson PDFs</div><div><strong>{sum(n['category']=='practice' for n in notes):02d}</strong>practice notes</div></div>
<section id="library"><div class="section-head"><div><h2>Find your next clear idea.</h2><p>Explore a topic, or practise what you already know.</p></div><label><span class="sr-only">Search notes</span><input class="search" type="search" placeholder="Search your English notes…" data-search aria-label="Search notes"></label></div>
<div class="filters" role="group" aria-label="Filter notes">'''+''.join(f'<button class="filter" type="button" data-filter="{cat}" aria-pressed="{str(cat=="all").lower()}">{label}</button>' for cat,label in [('all','All notes'),('grammar','Grammar'),('practice','Practice'),('ielts','IELTS'),('speaking','Speaking'),('library','Guides')])+f'''</div>
<p data-results aria-live="polite" class="results-label">{len(notes)} notes</p><div class="grid">{cards}</div><p class="empty" data-empty hidden>No matching notes. Try another topic or clear your search.</p></section>
<section class="downloads-panel"><div><h2>Keep the original lesson close.</h2><p>{len(pdfs)} PDF lessons, ready to download. {size(total)} in total.</p></div><a class="button-link" href="downloads.html">Browse PDF downloads <span aria-hidden="true">↓</span></a></section></main>''',cfg)


def downloads(pdfs,reports,cfg):
    rows=''
    for pdf in pdfs:
        report=reports[pdf['relative']]
        saved=round((1-report['download_bytes']/report['original_bytes'])*100)
        detail=size(report['download_bytes'])+(f' · {saved}% smaller' if saved>0 else '')
        rows+=f'''<a class="download-row" href="{pdf['route']}" download="{escape(pdf['download'])}" aria-label="Download {escape(pdf['title'])} PDF"><div><h2>{escape(pdf['title'])}</h2><p>{escape(pdf['category'])} · PDF · {detail}</p></div><span class="download-action">Download ↓</span></a>'''
    return page('PDF downloads',f'''<main id="main" class="shell"><div class="page-heading"><p class="eyebrow">The source material</p><h1>Your PDF bookshelf.</h1><p>Click a lesson to download its PDF. Read it alongside your notes, or keep a copy for later.</p></div><div class="download-list">{rows}</div></main>''',cfg)


def build(root,cfg,compress=None):
    root=root.resolve()
    output=(root/cfg['output']).resolve()
    forbidden=[root/name for name in ('content','scripts','config','.github','.git','.venv')]
    if output==root or not output.is_relative_to(root) or any(output.is_relative_to(p) or p.is_relative_to(output) for p in forbidden):
        raise ValueError('Output must be a separate build directory inside the project')
    if output.exists() and any(output.iterdir()) and not (output/'.darwinglish-site').exists():
        raise ValueError('Refusing to replace a nonempty output directory not created by this builder')
    notes,pdfs=collect(root,cfg)
    links=Links(notes,pdfs)
    rendered={n['relative']:render_note(n,links) for n in notes}
    compress=cfg['compress_pdfs'] if compress is None else compress
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.site-build-',dir=output.parent) as directory:
        stage=Path(directory)
        shutil.copytree(ROOT/'scripts/site_assets',stage/'assets')
        reports={}
        for pdf in pdfs:
            target=stage/pdf['route'];target.parent.mkdir(parents=True,exist_ok=True)
            if compress:report=compress_pdf(pdf['path'],target,cfg['jpeg_quality'],cfg.get('image_dpi',220))
            else:
                shutil.copyfile(pdf['path'],target)
                report={'original_bytes':target.stat().st_size,'download_bytes':target.stat().st_size,'status':'compression-disabled'}
            # Do not publish diagnostic exceptions/local paths.
            report.pop('detail',None);reports[pdf['relative']]=report
            print(f'{pdf["title"]}: {size(report["original_bytes"])} → {size(report["download_bytes"])} ({report["status"]})',flush=True)
        (stage/'notes').mkdir()
        for note in notes:
            sidebar='<aside class="sidebar"><p class="sidebar-label">In your notebook</p>'+''.join(f'<a href="../{n["route"]}"'+(' aria-current="page"' if n==note else '')+'>'+escape(n['title'])+'</a>' for n in notes)+'</aside>'
            main='<main class="reading-layout" id="main">'+sidebar+'<article class="article"><div class="breadcrumbs"><a href="../index.html#library">Library</a> / '+escape(note['category'].capitalize())+'</div>'+rendered[note['relative']]+'<a class="article-back" href="../index.html#library">← Back to the library</a></article></main>'
            (stage/note['route']).write_text(page(note['title'],main,cfg,'../'),encoding='utf-8')
        (stage/'index.html').write_text(home(notes,pdfs,reports,cfg),encoding='utf-8')
        (stage/'downloads.html').write_text(downloads(pdfs,reports,cfg),encoding='utf-8')
        (stage/'compression-report.json').write_text(json.dumps(reports,indent=2)+'\n',encoding='utf-8')
        (stage/'.nojekyll').touch();(stage/'.darwinglish-site').touch()
        checks=validate_site(stage)
        print(f'Checked {checks["local_links"]} local links, including {checks["pdf_download_links"]} PDF download links.',flush=True)
        if output.exists():shutil.rmtree(output)
        stage.rename(output)
    print(f'Built {len(notes)} notes and {len(pdfs)} PDF downloads in {output}')
    return {'notes':notes,'pdfs':pdfs,'reports':reports,'output':output}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,default=ROOT/'config/site.toml')
    parser.add_argument('--no-compress',action='store_true',help='Copy PDF originals into the site without recompression')
    args=parser.parse_args()
    cfg=tomllib.loads(args.config.read_text(encoding='utf-8'))
    build(ROOT,cfg,False if args.no_compress else None)


if __name__=='__main__':main()
