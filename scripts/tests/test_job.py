"""Behavior tests: fake provider responses, real filesystem, optional real PDF tools."""
from __future__ import annotations
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch, Mock
import zlib
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import watch_pdfs as watcher
from lesson_output import render,sha256,validate
from pdf_input import backend,prepare
from providers import run_agent

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT/'config/skills/english-pdf-notes/schema.json'
SCHEMA = json.loads(SCHEMA_PATH.read_text())
RESULT = {
    'title':'Second Conditional','slug':'second-conditional','category':'Grammar','source_pages':[1],
    'grammar_markdown':'## Usage\n\nUse this pattern for imagined situations (p. 1).\n\n## Examples\n\nNew example: If I had time, I would study.',
    'related_notes':[], 'limitations':[],
    'exercises':[{'kind':'choice','origin':'added','source_pages':[1],
                  'prompt':'If I had time, I ___ study.','options':['would','will'],
                  'answer':'1. would','explanation':'Use would for the imagined result.'},
                 {'kind':'completion','origin':'added','source_pages':[],
                  'prompt':'If I ___ time, I would study.','options':[],
                  'answer':'had','explanation':'Past form in the condition.'}]}


def make_pdf(path, image=False):
    # Minimal valid PDF: real rendering tests do not need another Python library.
    if image:
        pixels=zlib.compress(bytes([100,180,220,255])*100)
        objects=[b'<< /Type /Catalog /Pages 2 0 R >>',
                 b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
                 b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 400 1800] /Resources << /XObject << /Im0 5 0 R >> >> /Contents 4 0 R >>',
                 b'<< /Length 32 >>\nstream\nq 400 0 0 1800 0 0 cm /Im0 Do Q\nendstream',
                 b'<< /Type /XObject /Subtype /Image /Width 20 /Height 20 /ColorSpace /DeviceGray /BitsPerComponent 8 /Filter /FlateDecode /Length '+str(len(pixels)).encode()+b' >>\nstream\n'+pixels+b'\nendstream']
    else:
        text=b'BT /F1 12 Tf 30 700 Td (English grammar usage and examples for a new lesson. If I had time I would study more every day.) Tj ET'
        objects=[b'<< /Type /Catalog /Pages 2 0 R >>',
                 b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
                 b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>',
                 b'<< /Length '+str(len(text)).encode()+b' >>\nstream\n'+text+b'\nendstream',
                 b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
    data=b'%PDF-1.4\n';offsets=[0]
    for i,obj in enumerate(objects,1):
        offsets.append(len(data));data+=f'{i} 0 obj\n'.encode()+obj+b'\nendobj\n'
    start=len(data);data+=f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode()
    for offset in offsets[1:]:data+=f'{offset:010d} 00000 n \n'.encode()
    data+=f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n'.encode()
    path.write_bytes(data)


class JobTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='english job spaces ')
        self.root=Path(self.temp.name)
        self.cfg=watcher.load_config(ROOT/'config/job.toml')
        self.cfg.update(content=self.root/'content',inbox=self.root/'content/Inbox',
                        state=self.root/'config/state',stable_seconds=1,retry_seconds=1,
                        image_width=600,image_tile_height=900,image_overlap=100,text_threshold=50)
        self.cfg['inbox'].mkdir(parents=True)
        self.source=self.cfg['inbox']/'screen capture.PDF'
        make_pdf(self.source)

    def tearDown(self):
        self.temp.cleanup()

    def fake_prepare(self,*args):
        return {'page_count':1,'pages':[{'page':1,'text':'Source','images':[]}], 'images':[], 'backend':'fake'}

    def run_job(self,result=None):
        with patch.object(watcher,'prepare',side_effect=self.fake_prepare),patch.object(watcher,'run_agent',return_value=copy.deepcopy(result or RESULT)) as agent:
            job=watcher.Job(self.cfg)
            status=job.process(self.source)
            return job,status,agent.call_count

    def test_success_publishes_notes_answers_at_end_and_moves_original(self):
        expected=sha256(self.source)
        job,success,calls=self.run_job()
        self.assertTrue(success);self.assertEqual(calls,1);self.assertFalse(self.source.exists())
        record=job.history[expected]
        self.assertEqual(record['status'],'completed')
        self.assertEqual(sha256(self.cfg['content']/record['pdf']),expected)
        exercises=(self.cfg['content']/record['bundle']/'Exercises.md').read_text()
        questions,answers=exercises.split('\n## Answers\n')
        self.assertNotIn('1. would',questions);self.assertIn('1. would',answers)
        self.assertNotIn('## Question',answers)
        self.assertTrue((self.cfg['content']/'Obsidian English/Imported Lessons.md').exists())

    def test_agent_failure_keeps_original_and_retries_are_bounded(self):
        digest=sha256(self.source)
        with patch.object(watcher,'prepare',side_effect=self.fake_prepare),patch.object(watcher,'run_agent',side_effect=RuntimeError('no authentication')) as agent:
            job=watcher.Job(self.cfg)
            self.assertFalse(job.process(self.source));self.assertTrue(self.source.exists())
            self.assertFalse(job.process(self.source));self.assertEqual(agent.call_count,1)
            job.history[digest]['next_retry']=0
            self.assertFalse(job.process(self.source));self.assertEqual(agent.call_count,2)
            job.history[digest]['next_retry']=0
            self.assertFalse(job.process(self.source));self.assertEqual(agent.call_count,2)
            self.assertFalse(list((self.cfg['content']/'PDFs').rglob('*.pdf')))

    def test_invalid_agent_slug_cannot_escape_content(self):
        result=copy.deepcopy(RESULT);result['slug']='../../overwrite'
        job,success,_=self.run_job(result)
        self.assertFalse(success);self.assertTrue(self.source.exists())
        self.assertIn('slug',next(iter(job.history.values()))['error'])

    def test_duplicate_retained_without_new_agent_call(self):
        payload=self.source.read_bytes();self.run_job()
        duplicate=self.cfg['inbox']/'another-name.pdf';duplicate.write_bytes(payload)
        with patch.object(watcher,'run_agent') as agent:
            self.assertTrue(watcher.Job(self.cfg).process(duplicate));agent.assert_not_called()
        self.assertFalse(duplicate.exists())
        copies=list((self.cfg['content']/'Duplicates').glob('*.pdf'))
        self.assertEqual(len(copies),1);self.assertEqual(copies[0].read_bytes(),payload)

    def test_archive_collision_never_overwrites_or_removes_original(self):
        digest=sha256(self.source);plan=render(RESULT,digest,self.source.name,'codex')
        collision=self.cfg['content']/plan['pdf'];collision.parent.mkdir(parents=True);collision.write_bytes(b'user file')
        _,success,_=self.run_job()
        self.assertFalse(success);self.assertTrue(self.source.exists());self.assertEqual(collision.read_bytes(),b'user file')

    def test_restart_finishes_publish_without_another_analysis(self):
        digest=sha256(self.source)
        with patch.object(watcher,'prepare',side_effect=self.fake_prepare),patch.object(watcher,'run_agent',return_value=copy.deepcopy(RESULT)) as agent:
            with patch.object(watcher,'publish',side_effect=RuntimeError('interrupted')):
                job=watcher.Job(self.cfg);self.assertFalse(job.process(self.source))
            job.history[digest]['next_retry']=0;job.save()
            restarted=watcher.Job(self.cfg)
            self.assertTrue(restarted.process(self.source));self.assertEqual(agent.call_count,1)

    def test_restart_recovers_after_move_before_state_update(self):
        digest=sha256(self.source);job,_,_=self.run_job()
        job.history[digest]['status']='running';job.save()
        restarted=watcher.Job(self.cfg);restarted.recover()
        self.assertEqual(restarted.history[digest]['status'],'completed')

    def test_user_edited_published_note_is_preserved_on_retry(self):
        digest=sha256(self.source)
        with patch.object(watcher,'prepare',side_effect=self.fake_prepare),patch.object(watcher,'run_agent',return_value=copy.deepcopy(RESULT)):
            original=watcher.copy_exclusive
            with patch.object(watcher,'copy_exclusive',wraps=original) as copier:
                def fail_archive(src,dst,expected):
                    if 'PDFs' in dst.parts:raise RuntimeError('archive interrupted')
                    return original(src,dst,expected)
                copier.side_effect=fail_archive
                job=watcher.Job(self.cfg);self.assertFalse(job.process(self.source))
        plan=json.loads((self.cfg['state']/'jobs'/digest/'plan.json').read_text())
        edited=self.cfg['content']/plan['bundle']/'Lesson.md';edited.write_text('my edit')
        job.history[digest]['next_retry']=0;job.save()
        self.assertFalse(watcher.Job(self.cfg).process(self.source))
        self.assertEqual(edited.read_text(),'my edit');self.assertTrue(self.source.exists())

    def test_lock_rejects_second_job(self):
        with watcher.job_lock(self.cfg['state']/'job.lock'):
            with self.assertRaises(RuntimeError):
                with watcher.job_lock(self.cfg['state']/'job.lock'):pass

    def test_stability_wait_resets_when_file_changes(self):
        job=watcher.Job(self.cfg)
        with patch.object(watcher.time,'monotonic',return_value=0):self.assertEqual(list(job.ready()),[])
        with patch.object(watcher.time,'monotonic',return_value=2):self.assertEqual(list(job.ready()),[self.source])
        self.source.write_bytes(self.source.read_bytes()+b'\n')
        with patch.object(watcher.time,'monotonic',return_value=3):self.assertEqual(list(job.ready()),[])

    def test_validate_rejects_nonexistent_pages_and_related_notes(self):
        result=copy.deepcopy(RESULT);result['source_pages']=[2]
        with self.assertRaises(ValueError):validate(result,SCHEMA,1,{})
        result=copy.deepcopy(RESULT);result['related_notes']=['invented note']
        with self.assertRaises(ValueError):validate(result,SCHEMA,1,{})

    def test_symlink_inputs_ignored(self):
        link=self.cfg['inbox']/'link.pdf'
        try:link.symlink_to(self.source)
        except (OSError,NotImplementedError):self.skipTest('symlinks unavailable')
        job=watcher.Job(self.cfg)
        with patch.object(watcher.time,'monotonic',return_value=0):list(job.ready())
        with patch.object(watcher.time,'monotonic',return_value=2):self.assertEqual(list(job.ready()),[self.source])

    def test_real_text_extraction(self):
        try:backend()
        except RuntimeError:self.skipTest('No PDF backend installed')
        result=prepare(self.source,self.root/'text output',self.cfg)
        self.assertEqual(result['page_count'],1);self.assertEqual(result['images'],[])
        self.assertIn('English grammar',result['pages'][0]['text'])

    def test_real_tall_screenshot_render_and_image_limit(self):
        try:backend()
        except RuntimeError:self.skipTest('No PDF backend installed')
        make_pdf(self.source,image=True)
        result=prepare(self.source,self.root/'image output',self.cfg)
        self.assertGreaterEqual(len(result['images']),3)
        self.assertTrue(all(p.read_bytes().startswith(b'\x89PNG') for p in result['images']))
        limited={**self.cfg,'max_images':1}
        with self.assertRaisesRegex(ValueError,'max_images'):
            prepare(self.source,self.root/'limited',limited)

    def test_codex_adapter_reads_schema_output_and_passes_images(self):
        job=self.root/'provider';(job/'work').mkdir(parents=True)
        process=Mock(returncode=0)
        def communicate(*args,**kwargs):(job/'raw-response.json').write_text(json.dumps(RESULT))
        process.communicate.side_effect=communicate
        image=job/'work/page-001.png'
        with patch('providers.subprocess.Popen',return_value=process) as popen:
            actual=run_agent('codex',self.cfg,'prompt',[image],job,SCHEMA_PATH)
        self.assertEqual(actual,RESULT)
        argv=popen.call_args.args[0]
        self.assertIn('--image',argv);self.assertIn(str(image),argv)
        self.assertIn('read-only',argv);self.assertNotIn('shell',popen.call_args.kwargs)

    def test_claude_adapter_parses_structured_output_and_limits_tools(self):
        job=self.root/'provider';(job/'work').mkdir(parents=True)
        process=Mock(returncode=0)
        def factory(*args,**kwargs):
            kwargs['stdout'].write(json.dumps({'structured_output':RESULT}).encode());kwargs['stdout'].flush()
            return process
        with patch('providers.subprocess.Popen',side_effect=factory) as popen:
            actual=run_agent('claude',self.cfg,'prompt',[],job,SCHEMA_PATH)
        self.assertEqual(actual,RESULT)
        argv=popen.call_args.args[0]
        self.assertEqual(argv[argv.index('--tools')+1],'Read')
        self.assertNotIn('--dangerously-skip-permissions',argv)

    def test_claude_success_exit_without_structured_output_is_failure(self):
        job=self.root/'provider';(job/'work').mkdir(parents=True)
        def factory(*args,**kwargs):
            kwargs['stdout'].write(b'{"result":"authentication failed","is_error":true}')
            kwargs['stdout'].flush();return Mock(returncode=0)
        with patch('providers.subprocess.Popen',side_effect=factory),self.assertRaises(ValueError):
            run_agent('claude',self.cfg,'prompt',[],job,SCHEMA_PATH)


if __name__ == '__main__':unittest.main()
