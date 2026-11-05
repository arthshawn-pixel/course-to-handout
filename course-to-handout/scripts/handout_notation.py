"""Portable academic notation and an executable, self-authored font specimen."""
from pathlib import Path
import re
from handout_core import HandoutError,validate_math,file_hash,write_json

FONT_FILES=('SourceHanSerifSC-Regular.otf','texgyretermes-regular.otf','texgyretermes-bold.otf',
 'texgyretermes-italic.otf','texgyretermes-bolditalic.otf','texgyretermes-math.otf','STIXTwoMath-Regular.otf')

def font_inventory(root):
    paths={n:Path(root)/'assets/fonts'/n for n in FONT_FILES}
    return {'required':list(FONT_FILES),'missing':[n for n,p in paths.items() if not p.is_file()],
            'sha256':{n:file_hash(p) for n,p in paths.items() if p.is_file()},'default_math':'stix2','profiles':['stix2','termes']}

def notation_tex(block):
    if block['type']=='chem':
        formula=block.get('formula');validate_math(formula)
        return r'\ce{'+formula+'}'
    if block['type']=='quantity':
        value,unit=block.get('value'),block.get('unit');validate_math(value);validate_math(unit)
        if not re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:\(\d+\))?(?:[eE][+-]?\d+)?',value):
            raise HandoutError('quantity.value 使用数字、科学计数或括号不确定度；代数表达式用 math 块')
        return r'\qty{'+value+'}{'+unit+'}'
    raise HandoutError('Unsupported notation block')

def specimen(job,math_font='stix2'):
    from handout_v2 import minimal_unit
    from handout_render import render
    job=Path(job).resolve()
    if job.exists() and any(job.iterdir()):raise HandoutError('符号样例需使用新的空任务目录')
    if math_font not in ('stix2','termes'):raise HandoutError('Unknown math font profile')
    job.mkdir(parents=True,exist_ok=True)
    def t(text):return {'type':'text','text':text}
    def m(latex):return {'type':'math','latex':latex}
    subjects=[
     ('calculus','微积分与微分方程',[
       t('保留微分、偏导、多重积分、梯度及上下标：∂ ∇ ∫ ∬ ∭ ∮ ∯ ∰；x̄、x̂、x⃗、xₙ₊₁、x⁻²。'),
       m(r'\frac{d}{dx}\int_0^x f(t)\,dt=f(x),\qquad \frac{\partial^2 u}{\partial x^2}+\frac{\partial^2 u}{\partial y^2}=0.'),
       m(r'\iiint_{\Omega}f\,dV=\int_a^b\int_c^d\int_e^g f(x,y,z)\,dz\,dy\,dx.\quad\oint_C\mathbf{F}\cdot d\mathbf{r}'),
       m(r'\lim_{h\to0}\frac{f(x+h)-f(x)}h=f^{\prime}(x),\quad \sum_{n=0}^{\infty}\frac{x^n}{n!}=e^x.')]),
     ('linear','线性代数、概率与优化',[
       t('数集与字体承载含义，不能把𝐀、𝑨、𝔄、𝒜、ℝ、ℂ、ℤ都改成普通字母。'),
       m(r'A=\begin{pmatrix}1&2\\3&4\end{pmatrix},\quad \det A=-2,\quad A^{\mathsf{T}}A\succeq0,\quad x\in\mathbb{R}^n.'),
       m(r'\langle x,y\rangle=x^{\mathsf{T}}y,\quad\|x\|_2=\sqrt{x^{\mathsf{T}}x},\quad A\otimes B,\quad\mathcal{L}\{f\}.'),
       m(r'\mathbb{E}[X]=\int x f_X(x)\,dx,\quad\operatorname{Var}(X)=\mathbb{E}[X^2]-\mathbb{E}[X]^2,\quad\arg\min_{x\in\mathbb{R}^n}f(x).')]),
     ('physics','物理与测量',[
       t('希腊字母、约化普朗克常数、量子态与电磁场：ε μ Ω ℏ ψ；变量与单位区分。'),
       m(r'\nabla\cdot\mathbf{E}=\frac{\rho}{\varepsilon_0},\quad\nabla\times\mathbf{E}=-\frac{\partial\mathbf{B}}{\partial t}.'),
       m(r'i\hbar\frac{\partial\psi}{\partial t}=\hat H\psi,\quad\langle\psi|\hat A|\psi\rangle,\quad E=mc^2.'),
       {'type':'quantity','value':'9.81','unit':r'\metre\per\second\squared'},
       {'type':'quantity','value':'25','unit':r'\degreeCelsius'}]),
     ('chemistry','化学与物理化学',[
       t('元素用正体，分子下标、电荷上标、同位素和反应箭头分别处理。'),
       {'type':'chem','formula':'2 H2(g) + O2(g) -> 2 H2O(l)'},
       {'type':'chem','formula':'Fe^3+ + 3 OH- -> Fe(OH)3 v'},
       m(r'\ce{^{14}_{6}C} \to \ce{^{14}_{7}N}+e^{-}+\bar\nu_e'),
       {'type':'chem','formula':'N2 + 3 H2 <=> 2 NH3'},
       m(r'\Delta G=\Delta H-T\Delta S,\quad E=E^{\circ}-\frac{RT}{nF}\ln Q.'),
       {'type':'quantity','value':'8.314','unit':r'\joule\per\mole\per\kelvin'}]),
     ('finance','经济、管理与金融',[
       t('收益率、贴现、条件期望、协方差与货币：5%、25 bp、USD $、EUR €、GBP £、CNY ¥。'),
       m(r'\operatorname{NPV}=\sum_{t=0}^{T}\frac{CF_t}{(1+r)^t},\quad\beta_i=\frac{\operatorname{Cov}(R_i,R_m)}{\operatorname{Var}(R_m)}.'),
       m(r'dS_t=\mu S_t\,dt+\sigma S_t\,dW_t,\quad \mathbb{E}[X\mid\mathcal{F}_t],\quad\widehat\beta=(X^{\mathsf T}X)^{-1}X^{\mathsf T}y.'),
       m(r'\max_{x,y\ge0}U(x,y)\quad\text{subject to}\quad p_xx+p_yy\le M.'),
       {'type':'quantity','value':'5','unit':r'\percent'}]),
     ('engineering','工程、电路与控制',[
       t('复数阻抗、传递函数、应力张量、角度与工程单位。'),
       m(r'Z=R+j\omega L+\frac1{j\omega C},\quad G(s)=\frac{\omega_n^2}{s^2+2\zeta\omega_ns+\omega_n^2}.'),
       m(r'\sigma_{ij}=C_{ijkl}\varepsilon_{kl},\quad\mathbf{q}=-k\nabla T,\quad\lceil x\rceil,\quad\lfloor x\rfloor,\quad\angle H(j\omega).'),
       {'type':'quantity','value':'220','unit':r'\volt'},
       {'type':'quantity','value':'2.4e3','unit':r'\newton\metre'},
       m(r'\ang{30},\quad\qty{1.2e-3}{\ohm},\quad\qty{5}{\mega\pascal}.')])]
    doc={'schema_version':2,'title':'跨学科符号与字体兼容样例','short_title':'理工与经管 / 字体兼容',
         'level':'通用学术排版','prerequisites':[],'learning_goal':'自制记号样例；只验证排版与符号保真，不是课程内容核验。',
         'typography':{'math_font':math_font},'coverage':{'included':[s[1] for s in subjects],'omitted':[]},
         'sections':[],'units':[],'figures':[]}
    for i,(ident,title,body) in enumerate(subjects):
        sid='s'+str(i+1);doc['sections'].append({'id':sid,'title':title,'start':i,'end':i+1})
        u=minimal_unit(ident,sid);u.update(title=title,type='note',origin='generated',answer_origin='generated',body=body,
             review={'status':'pending','reason':'自制符号样例，不对应原始课程'})
        doc['units'].append(u)
    for name,value in [('source.json',{'title':'自制跨学科符号测试','duration':6,'video_id':'notation-fixture','part':1,'url':'','fixture':True}),
      ('state.json',{'stages':{},'access':{'status':'ready'}}),('materials/frames.json',[]),('materials/subtitles.json',[]),('handout.json',doc)]:write_json(job/name,value)
    result=render(job,draft=True,engine='tectonic')
    from handout_core import read_json
    audit=read_json(job/'build/student-reading/layout-report.json')
    if audit['warnings']:raise HandoutError('NOTATION_AUDIT_FAILED: 查看 build/student-reading/layout-report.json 中缺字或溢出诊断')
    return result
