"""Validate agent data and render deterministic Obsidian documents."""
from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path


def validate(data, schema, page_count, catalog):
    def check(value, rule, path):
        kind = rule['type']
        valid = {'object':lambda: isinstance(value,dict), 'array':lambda: isinstance(value,list),
                 'string':lambda: isinstance(value,str),
                 'integer':lambda: isinstance(value,int) and not isinstance(value,bool)}[kind]()
        if not valid:
            raise ValueError(f'{path}: expected {kind}')
        if 'enum' in rule and value not in rule['enum']:
            raise ValueError(f'{path}: invalid value')
        if kind == 'object':
            if set(rule['required']) - value.keys() or value.keys() - rule['properties'].keys():
                raise ValueError(f'{path}: missing or unknown fields')
            for key, child in value.items():
                check(child, rule['properties'][key], path+'.'+key)
        elif kind == 'array':
            if len(value) < rule.get('minItems',0):
                raise ValueError(f'{path}: too few items')
            for i, child in enumerate(value):
                check(child, rule['items'], f'{path}[{i}]')
        elif kind == 'integer':
            if value < rule.get('minimum',value) or value > page_count:
                raise ValueError(f'{path}: PDF page number out of range')
        elif kind == 'string':
            if len(value.strip()) < rule.get('minLength',0) or len(value) > rule.get('maxLength',2_000_000):
                raise ValueError(f'{path}: invalid string length')
            if 'pattern' in rule and not re.fullmatch(rule['pattern'],value):
                raise ValueError(f'{path}: invalid filename slug')
            if '\x00' in value:
                raise ValueError(f'{path}: NUL character')
    check(data,schema,'result')
    if not {'## Usage','## Examples'}.issubset(set(data['grammar_markdown'].splitlines())):
        raise ValueError('grammar_markdown must contain ## Usage and ## Examples')
    for name in data['related_notes']:
        if name not in catalog:
            raise ValueError(f'Unknown related note: {name}')
    strings = [data['title'], data['grammar_markdown'], *data['limitations']]
    if '\n' in data['title'] or '\r' in data['title']:
        raise ValueError('Title must be a single line')
    for exercise in data['exercises']:
        if exercise['origin'] != 'added' and not exercise['source_pages']:
            raise ValueError('Source/adapted exercises need page references')
        if exercise['kind'] == 'choice' and len(exercise['options']) < 2:
            raise ValueError('Multiple-choice tasks need at least two options')
        strings += [exercise['prompt'], exercise['answer'], exercise['explanation'], *exercise['options']]
    if any('[[' in s or '![' in s for s in strings):
        raise ValueError('Agent text must not contain generated wiki links or image embeds')
    return data


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def render(data, digest, original_name, provider):
    stem = data['slug'] + '--' + digest[:12]
    bundle = 'Obsidian English/Imported/' + stem
    pdf = 'PDFs/' + data['category'] + '/' + stem + '.pdf'
    source = f'[[{pdf}#page=1|Source PDF]]'
    lesson_link = f'[[{bundle}/Lesson|Lesson]]'
    exercises_link = f'[[{bundle}/Exercises|Exercises]]'
    meta = ('---\ntags: [english, imported]\nsource_sha256: '+digest+'\nprovider: '+provider+
            '\noriginal_filename: '+json.dumps(original_name,ensure_ascii=False)+'\n---\n\n')
    limitations = ('\n## Source limitations\n\n' + '\n'.join('- '+x for x in data['limitations'])+'\n') if data['limitations'] else ''
    lesson = meta+'# '+data['title']+'\n\n'+source+' | '+exercises_link+'\n\n'+data['grammar_markdown'].strip()+'\n'
    lesson += '\n## Source pages\n\n'+', '.join(str(x) for x in data['source_pages'])+'\n'
    if data['related_notes']:
        lesson += '\n## Related notes\n\n'+'\n'.join('- [['+x+']]' for x in data['related_notes'])+'\n'
    lesson += limitations
    questions = meta+'# '+data['title']+' - Exercises\n\n'+source+' | '+lesson_link+'\n\n'
    questions += 'Origins: **pdf** = visible source task; **adapted** = changed wording/format; **added** = new practice. Answers are at the end; open responses are samples.\n'
    answers = '\n## Answers\n\nSuggested solutions, not an official publisher key. Check explanations for ambiguity or inference.\n'
    for i, item in enumerate(data['exercises'],1):
        pages = ', '.join(map(str,item['source_pages'])) or 'not applicable'
        questions += f'\n## Question {i}\n\n*{item["kind"]}; {item["origin"]}; PDF pages: {pages}*\n\n'+item['prompt'].strip()+'\n'
        for j, option in enumerate(item['options'],1):
            questions += f'\n- **{j}.** {option}\n'
        questions += '\nYour answer: ______\n'
        answers += f'\n### {i}\n\n'+item['answer'].strip()+'\n\n'+item['explanation'].strip()+'\n'
    # Any limitations appear before the final answer section.
    questions += limitations + answers
    return {'bundle':bundle,'pdf':pdf,'files':{'Lesson.md':lesson,'Exercises.md':questions}}
