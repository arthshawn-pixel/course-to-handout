"""Independent exact-state path checks and executable coin partition regressions."""
from __future__ import annotations

import itertools
from fractions import Fraction as F
from pathlib import Path

from handout_core import HandoutError, read_json, write_json, file_hash, digest


def fraction(value):
    if not isinstance(value,(str,int)) or isinstance(value,bool):raise HandoutError('精确数必须用整数或分数字符串')
    return F(value)


def all_blocks(unit):
    for group in [unit.get('body',[]),*[s.get('content',[]) for s in unit.get('steps',[])],unit.get('conclusion',[])]:
        yield from group


def validate_claim(b):
    kind=b['type']
    if kind=='sequence':
        for key in ('constant','coefficient','base'):fraction(b[key])
        if not isinstance(b.get('variable','p'),str) or not b.get('variable','p').isalpha():raise HandoutError('通项变量使用字母')
        if b.get('index','n') not in ('n','i','k'):raise HandoutError('通项下标使用 n/i/k')
    elif kind=='coin_recurrence':
        if len(b.get('coefficients',[]))!=3:raise HandoutError('连续三次正面模型需要三个系数')
        for x in b['coefficients']:fraction(x)
    elif kind=='partition':
        if b.get('direction') not in ('prefix','suffix') or not isinstance(b.get('patterns'),list) or not all(isinstance(x,str) and x and set(x)<={'H','T'} for x in b['patterns']):raise HandoutError('分类须给出 prefix/suffix 和 H/T 模式')


def enumerate_paths(matrix,initial,targets,n):
    """Enumerate weighted physical-state paths; never derive the oracle from the claim."""
    matrix=[[fraction(x) for x in row] for row in matrix];initial=[fraction(x) for x in initial];size=len(initial)
    if len(matrix)!=size or any(len(row)!=size or sum(row)!=1 or min(row)<0 for row in matrix) or sum(initial)!=1 or min(initial)<0:raise HandoutError('转移矩阵和初始分布必须为概率分布')
    def visit(state,depth,weight):
        if depth==n-1:return weight if state in targets else F(0)
        return sum((visit(j,depth+1,weight*p) for j,p in enumerate(matrix[state]) if p),F(0))
    return sum((visit(i,0,p) for i,p in enumerate(initial) if p),F(0))


def legal_words(n):return [''.join(w) for w in itertools.product('HT',repeat=n) if 'HHH' not in ''.join(w)]


def partition_check(direction,patterns,max_n=12):
    failures=[]
    for n in range(4,max_n+1):
        for word in legal_words(n):
            hits=[p for p in patterns if (word.startswith(p) if direction=='prefix' else word.endswith(p))]
            if len(hits)!=1:
                failures.append({'n':n,'word':word,'matches':hits});
                if len(failures)>=5:break
        if len(failures)>=5:break
    certificate=(direction=='prefix' and sorted(patterns)==sorted(['T','HT','HHT'])) or (direction=='suffix' and sorted(patterns)==sorted(['T','TH','THH']))
    return {'passed':not failures and certificate,'counterexamples':failures,'checked_n':[4,max_n],
            'general_certificate':certificate,'coverage':'形式化分类块：首次反面位置/末尾正面段互斥穷尽，T分隔保证拼接边界不出现HHH；不代替对任意正文的人工复核。'}


def verify_unit(job,ident,dimension='calculation'):
    from handout_v2 import content_digest
    job=Path(job);doc=read_json(job/'handout.json');unit=next((u for u in doc['units'] if u['id']==ident),None)
    if unit is None:raise HandoutError('不存在的教学单元')
    blocks=list(all_blocks(unit));checks=[];passed=True
    if dimension=='calculation':
        claims=[b for b in blocks if b.get('type')=='sequence'];model=unit.get('verification_model')
        if claims and model:
            for claim in claims:
                validate_claim(claim);values=[]
                for n in range(1,11):
                    actual=enumerate_paths(model['matrix'],model['initial'],model.get('targets',[0]),n)
                    expected=fraction(claim['constant'])+fraction(claim['coefficient']) if n==1 else fraction(claim['constant'])+fraction(claim['coefficient'])*fraction(claim['base'])**(n-1)
                    values.append({'n':n,'path_enumeration':str(actual),'written_claim':str(expected),'equal':actual==expected})
                ok=all(v['equal'] for v in values);passed &= ok
                checks.append({'method':'exact_weighted_state_paths','values':values,'passed':ok,'coverage':'初始分布与转移模型下第1—10步；题干参数忠实性另行检查'})
        for claim in [b for b in blocks if b.get('type')=='coin_recurrence']:
            values={n:F(len(legal_words(n)),2**n) for n in range(1,13)};coeff=[fraction(x) for x in claim['coefficients']]
            ok=values[3]==F(7,8) and values[4]==F(13,16) and all(values[n]==sum((coeff[j]*values[n-j-1] for j in range(3)),F(0)) for n in range(4,13))
            passed &= ok;checks.append({'method':'binary_word_enumeration','values':{str(n):str(v) for n,v in values.items()},'strict_decrease_from_2':all(values[n+1]<values[n] for n in range(2,12)),'passed':ok,'coverage':'n=1—12；一般性由正文证明'})
    elif dimension=='proof':
        for claim in [b for b in blocks if b.get('type')=='partition']:
            result=partition_check(claim['direction'],claim['patterns']);passed &= result['passed'];checks.append({'method':'partition_enumeration_and_boundary_certificate',**result})
    else: raise HandoutError('自动核验只支持 calculation/proof；来源与一般证明用 review-unit 记录实际复核产物')
    status='passed' if checks and passed else 'failed' if checks else 'needs_review'
    evidence={'dimension':dimension,'target_digest':content_digest(unit,doc.get('figures')),'checker_version':file_hash(__file__),
              'status':status,'checks':checks,'notice':'只覆盖所列对象，不构成整份讲义正确性认证。'}
    path=job/'checks'/f'{ident}-{dimension}.json';write_json(path,evidence)
    unit.setdefault('checks',{})[dimension]={'artifact':path.relative_to(job).as_posix(),'sha256':file_hash(path),'digest':content_digest(unit,doc.get('figures'))}
    write_json(job/'handout.json',doc)
    return evidence


def record_review(job,ident,dimension,record_file):
    from handout_v2 import content_digest,code_digest
    job=Path(job);doc=read_json(job/'handout.json');u=next((u for u in doc['units'] if u['id']==ident),None)
    if u is None or dimension not in ('fidelity','calculation','proof'):raise HandoutError('单元或核验层无效')
    record=read_json(record_file)
    if record.get('target_digest')!=content_digest(u,doc.get('figures')):raise HandoutError('核对记录不对应当前单元内容版本')
    if record.get('status') not in ('passed','failed') or not all(record.get(k) for k in ('method','reviewer','coverage','evidence_files')):raise HandoutError('核对记录须列方法、核对者、范围、证据文件和实际结果')
    for evidence in record['evidence_files']:
        from handout_core import within
        path=within(job,evidence['path'])
        if not path.is_file() or file_hash(path)!=evidence.get('sha256'):raise HandoutError('核对所用实际证据不存在或已更改')
    if record['method'] not in ('source_comparison','mathematical_review','counterexample_review'):
        raise HandoutError('人工复核仅接受明确的来源/数学/反例复核；程序核验必须由 verify-unit 实际执行')
    record.update(dimension=dimension,checker_version=file_hash(__file__))
    path=job/'checks'/f'{ident}-{dimension}-review.json';write_json(path,record)
    u.setdefault('checks',{})[dimension]={'artifact':path.relative_to(job).as_posix(),'sha256':file_hash(path),'digest':content_digest(u,doc.get('figures'))}
    write_json(job/'handout.json',doc);return {'recorded':True,'unit_id':ident,'dimension':dimension,'status':record['status']}
