"""Reusable reference content derived from the user-approved v0.2 teaching sample.

The serializer is development fixture code; normal agents use scaffold/unit-put.
Times are inherited from the supplied revision, not claimed as a new audio audit.
"""
from fractions import Fraction as F


def T(text):return {'type':'text','text':text}
def M(latex):return {'type':'math','latex':latex}
def S(c,k,b,v='p'):return {'type':'sequence','constant':c,'coefficient':k,'base':b,'variable':v}
def table(cols,rows):return {'type':'table','columns':cols,'rows':rows}
def Q(latex):return {'math':latex}


def course(source):
    def step(heading,*content):return {'heading':heading,'content':list(content),'origin':'course'}
    def unit(ident,section,title,kind='example',origin='course',times=None,frame=None):
        return {'id':ident,'section_id':section,'title':title,'type':kind,'origin':origin,'answer_origin':origin,
                'conditions':[],'body':[],'motivation':'','steps':[],'conclusion':[],'pitfalls':[],'related_units':[],
                'sources':[{'video_id':source['video_id'],'part':1,'start':times[0],'end':times[1]}] if times else [],
                'evidence':[{'kind':'frame','id':frame,'relation':'same_board','reason':'对照该教学单元的原板书'}] if frame else [],
                'review':{'status':'pending','reason':'按用户修订稿核对内容；视频时间沿用参考区间，尚未逐秒复核'},'checks':{}}
    intro=unit('intro','s1','给定当前状态以后，才谈下一步','definition','ai_supplement',(0,74),'f000060000')
    intro.update(related_units=['food'],body=[T('马尔科夫性：给定当前状态后，下一步状态的条件分布不再依赖更早的历史。本讲进一步限定为两状态、固定转移概率。相邻状态不必相关，独立随机序列也可以满足这一性质。'),
        T('若目标状态是A，记第n步在A的概率为pₙ。由当前在A与不在A这两条互斥、穷尽的路径分类：'),
        M(r'p_{n+1}=\alpha p_n+\beta(1-p_n)=(\alpha-\beta)p_n+\beta.'),
        T('先说清状态、一次转移和初值的时刻，再列条件概率。仅在题目中看到“概率＋数列”，不足以套用模型。')])
    food=unit('food','s2','例1：每天选择臭豆腐还是螺蛳粉',times=(18,602),frame='f000300000')
    food.update(conditions=['n为正整数；概率转移只依赖前一天；最大值讨论范围为n≥2'],
      body=[T('小帅每天中午在臭豆腐和螺蛳粉中选一种。第一天选臭豆腐的概率为2/3。若前一天选臭豆腐，后一天继续选臭豆腐的概率为1/4；若前一天选螺蛳粉，后一天继续选螺蛳粉的概率为1/2。'),
            T('记第n天选择臭豆腐的概率为pₙ。证明数列{pₙ−2/5}为等比数列，并证明n≥2时pₙ≤5/12。')],
      motivation='围绕目标“今天选臭豆腐”分两条路径。题目已给出平移常数2/5，应先按提示构造，再利用负公比讨论奇偶。',
      steps=[step('建模：两条路径汇合',{'type':'image','figure_id':'food-paths','caption':'原课板书局部：到达目标状态的两条路径'},
          T('从螺蛳粉改选臭豆腐的概率是补事件1−1/2=1/2。全概率公式给出'),M(r'p_n=\frac14p_{n-1}+\frac12(1-p_{n-1})=\frac12-\frac14p_{n-1},\quad p_1=\frac23.')),
        step('构造：将平衡点移到零',M(r'p_n-\frac25=-\frac14\left(p_{n-1}-\frac25\right),\qquad p_1-\frac25=\frac4{15}.'),T('因此平移后的数列是首项4/15、公比−1/4的等比数列。'),S('2/5','4/15','-1/4')),
        step('讨论：奇偶子列分别比较',T('偶数n对应负修正项，因而pₙ<2/5<5/12。奇数n在限定范围内至少为3，修正项随指数增大而减小：'),
          M(r'p_n=\frac25+\frac4{15}\left(\frac14\right)^{n-1}\le\frac25+\frac4{15}\left(\frac14\right)^2=\frac5{12}.'),T('只有n=3时等号成立。'))],
      conclusion=[T('在n≥2的范围内，最大值为5/12，且仅在n=3取得。')],pitfalls=['p₁=2/3不在最值讨论范围内；不能把整个交替数列当作单调数列。'],
      verification_model={'matrix':[['1/4','3/4'],['1/2','1/2']],'initial':['2/3','1/3'],'targets':[0]})
    method=unit('method','s3','一阶线性递推：通法只整理一次','theorem','course',(603,721),'f000650000')
    method.update(conditions=['λ≠1时使用不动点构造；λ=1另行处理'],body=[T('递推aₙ₊₁=λaₙ+μ中，寻找保持不变的常数s。若λ≠1，解s=λs+μ得s=μ/(1−λ)。'),
       M(r'a_{n+1}-s=\lambda(a_n-s),\qquad a_n=s+(a_1-s)\lambda^{n-1}\quad(n\ge2).'),
       T('构造成立，是因为μ−s=−λs。n=1直接取初值；λ=0时从第2项起恒为μ，不必在n=1写0⁰。'),
       M(r'\lambda=1:\qquad a_n=a_1+(n-1)\mu.'),
       T('寻找不动点的探索过程可以保留在草稿或必要的解答中；卷面简洁是一种呈现选择，并非数学上的禁令。')],conclusion=[])
    ball=unit('ball4','s4','例2：四人传球后的回甲概率',times=(764,1078),frame='f001020000')
    ball.update(conditions=['每次等可能传给另外三人；pₙ表示传球后'],
       body=[T('甲、乙、丙、丁四人相互传球，第1次由甲将球传出。每次等可能传给另外三人中的任意一人。记n次传球后球在甲手中的概率为pₙ，求p₃与pₙ。'),T('课件标注：2024·枣庄期末。')],
       motivation='所求只区分“在甲”和“不在甲”。乙、丙、丁传回甲的概率都为1/3，所以可以聚合；四状态建模同样可行。',
       steps=[step('状态与节点',table(['当前状态','下一次在甲','下一次不在甲'],[['在甲','0','1'],['不在甲',Q(r'\frac13'),Q(r'\frac23')]]),T('第1次传球后球不在甲，因此p₁=0。')),
          step('递推与平移',M(r'p_n=\frac13(1-p_{n-1}),\quad p_n-\frac14=-\frac13\left(p_{n-1}-\frac14\right).'),S('1/4','-1/4','-1/3')),
          step('回代检查初始几步',M(r'p_2=\frac13,\qquad p_3=\frac13\left(1-\frac13\right)=\frac29.'))],
       conclusion=[M(r'p_3=\frac29.')],pitfalls=['若改用传球前的第0步，可以写p₀=1；不能误写p₁=1。'],related_units=['method'],
       verification_model={'matrix':[[str(F(int(i!=j),3)) for j in range(4)] for i in range(4)],'initial':['0','1/3','1/3','1/3'],'targets':[0]})
    shooting=unit('shooting','s5','例3：命中继续，未中换人',times=(1078,1386),frame='f001380000')
    shooting.update(conditions=['甲命中率0.6，乙命中率0.8；首位各以0.5选出；i≥1'],
       body=[T('甲、乙两人投篮，每次由其中一人投。若命中，此人继续；若未命中，换对方投。无论之前情况如何，甲每次命中率均为0.6，乙为0.8。第1次由抽签决定，甲、乙的概率各0.5。求第i次由甲投篮的概率。'),T('课件标注：2023·新高考Ⅰ卷。')],
       motivation='把“当前投篮者”作为状态，下一次由甲投既可能源于甲命中，也可能源于乙未命中。',
       steps=[step('先写对两条条件概率',table(['当前投篮者','下一次甲投','下一次乙投'],[['甲','0.6（命中）','0.4（未中）'],['乙','0.2（未中）','0.8（命中）']]),
          M(r'p_{i+1}=0.6p_i+0.2(1-p_i)=\frac25p_i+\frac15,\quad p_1=\frac12.')),
          step('应用通法',M(r's=\frac13,\qquad p_{i+1}-\frac13=\frac25\left(p_i-\frac13\right).'),{**S('1/3','1/6','2/5'),'index':'i'}),
          step('解释变化趋势',T('公比2/5位于0与1之间，且初值大于1/3，所以概率单调递减并趋于1/3。直接分类得到p₂=0.4，与通项一致。'))],
       conclusion=[M(r'p_i=\frac13+\frac16\left(\frac25\right)^{i-1},\quad i\ge1.')],
       pitfalls=['乙转为甲使用的是未命中概率0.2，而不是0.8；长期投篮者概率不必各半。'],related_units=['method'],
       verification_model={'matrix':[['3/5','2/5'],['1/5','4/5']],'initial':['1/2','1/2'],'targets':[0]})
    shooting['evidence'][0].update(relation='residual',reason='23:00采集的画面仍是例3完整板书；其画面归属与同期口述的总结可以分开记录')
    boxes=unit('boxes','s6','例4：颜色状态在盒间传递',times=(1386,1604),frame='f001600000')
    boxes.update(conditions=['第1盒2红1白，其余各1红1白；每盒只取1球传入下一盒'],
       body=[T('盒子编号为1，2，…，n。第1盒有2红1白，其余各有1红1白。从第1盒任取一球放入第2盒，再从第2盒任取一球放入第3盒，依次进行。求从第2盒取到红球的概率，以及从第n盒取到红球的概率。'),T('课件标注：2025·山东青岛模拟。')],
       motivation='前一盒取出的颜色决定下一盒取球前的构成。状态不必是固定的人，也可以是传递的颜色。',
       steps=[step('以红、白区分状态',table(['传入的球','当前盒构成','取到红球概率'],[['红','2红1白',Q(r'\frac23')],['白','1红2白',Q(r'\frac13')]]),
           M(r'p_n=\frac23p_{n-1}+\frac13(1-p_{n-1})=\frac13p_{n-1}+\frac13,\quad p_1=\frac23.')),
           step('平移得到通项',M(r'p_n-\frac12=\frac13\left(p_{n-1}-\frac12\right).'),S('1/2','1/6','1/3')),
           step('独立求第一空',M(r'p_2=\frac23\cdot\frac23+\frac13\cdot\frac13=\frac59.'),T('直接分类和代入正确通项都成立；第一空可以用来交叉核对。'))],
       conclusion=[M(r'p_2=\frac59.')],pitfalls=['递推系数是1/3，不是2/3；每次取球前接收盒中共有3球。'],related_units=['method'],
       verification_model={'matrix':[['2/3','1/3'],['1/3','2/3']],'initial':['2/3','1/3'],'targets':[0]})
    concept=unit('concept','s7','自测1：概念辨析','exercise','generated')
    concept.update(conditions=['判断并说明理由'],body=[T('判断：①同时出现概率与数列就能直接使用本讲模型；②马尔科夫链要求相邻状态必须相关；③四人传球可聚合“不在甲”，是因为乙丙丁下一步回甲概率相同。')],
       motivation='从模型的结构条件而非关键词判断能否建模。',steps=[step('反例与聚合条件',T('①错，还需核对状态、转移概率和历史依赖。②错，独立随机序列的下一步连当前状态也不依赖，自然满足马尔科夫性。③对，三种状态到甲的转移概率相同；若不同，不能直接套同一个聚合系数。'))],
       conclusion=[T('答案：错、错、对。')],related_units=['intro','ball4'])
    ball3=unit('ball3','s7','自测2：三人传球变式','exercise','generated')
    ball3.update(conditions=['每次等可能传给另外两人；n≥1'],body=[T('甲、乙、丙三人传球，第1次由甲传出，每次等可能传给另外两人。求n次传球后球在甲手中的概率pₙ及p₃。')],motivation='沿用在甲/不在甲分类，但将返回甲的条件概率改为1/2。',
       steps=[step('改变转移概率',M(r'p_n=\frac12(1-p_{n-1}),\quad p_1=0,\quad s=\frac13.'),S('1/3','-1/3','-1/2'))],
       conclusion=[M(r'p_3=\frac14.')],related_units=['ball4','method'],
       verification_model={'matrix':[[str(F(int(i!=j),2)) for j in range(3)] for i in range(3)],'initial':['0','1/2','1/2'],'targets':[0]})
    weather=unit('weather','s7','自测3：天气模型','exercise','generated')
    weather.update(conditions=['固定转移概率且仅依赖前一天；n≥1'],body=[T('第1天晴天概率为1/2。前一天晴天，后一天仍晴的概率为2/3；前一天雨天，后一天仍雨的概率为1/2。假设转移只依赖前一天天气。求第n天晴天概率pₙ及变化趋势。')],
       motivation='雨转晴使用补事件概率1/2，随后判断通项修正项的符号。',steps=[step('列出递推并使用通法',M(r'p_n=\frac23p_{n-1}+\frac12(1-p_{n-1})=\frac16p_{n-1}+\frac12,\quad p_1=\frac12.'),S('3/5','-1/10','1/6')),
          step('比较连续两项',T('被减去的正修正项随n增大而减小，所以pₙ从1/2单调递增，趋于3/5。'))],conclusion=[T('极限为3/5，且每一项均小于3/5。')],related_units=['method'],
       verification_model={'matrix':[['2/3','1/3'],['1/2','1/2']],'initial':['1/2','1/2'],'targets':[0]})
    coin=unit('coin','s7','自测4：不出现连续三个正面','exercise','course',(1605,1627),'f001620000')
    coin.update(answer_origin='ai_supplement',conditions=['均匀硬币独立抛掷；n≥1'],
       body=[T('均匀硬币独立抛掷n次，记没有连续三次正面的概率为pₙ。判断：①p₃=7/8；②p₄=15/16；③n≥2时pₙ₊₁<pₙ；④n≥4时满足下面的递推。写出所有正确序号并说明理由。'),{'type':'coin_recurrence','coefficients':['1/2','1/4','1/8']}],
       motivation='数值只是检查起点。递推证明必须将合法序列分成互斥、穷尽且不会跨拼接边界形成HHH的类别。',
       steps=[step('小规模：先识别初值',T('不足3次时不可能出现HHH，故p₁=p₂=1。3次仅HHH违规；4次违规者为HHHH、HHHT、THHH。'),M(r'p_3=\frac78,\qquad p_4=\frac{13}{16}.')),
          step('按开头首次出现反面的位置分类',{'type':'partition','direction':'prefix','patterns':['T','HT','HHT']},
            T('n≥4时合法序列不可能以HHH开头，所以必有以上三种前缀之一。首次T的位置唯一，故互斥且穷尽。每个前缀以T结束，与其后的合法段拼接也不会跨边界形成HHH。'),
            T('利用独立性，各项贡献分别为1/2、1/4、1/8乘以相应长度的合法概率，得到题设递推。按结尾分类也可以，但应取T、TH、THH；T、HT、HHT作为后缀会重叠并遗漏。')),
          step('严格递减：按可追加的结果计数',T('设合法长n序列有aₙ个，其中以HH结尾者有bₙ个。后者只能追加T，其余可追加H或T，因此'),
            M(r'a_{n+1}=2a_n-b_n,\qquad p_{n+1}=p_n-\frac{b_n}{2^{n+1}}.'),
            T('当n≥2时，n−2个T后接HH给出了一个合法序列，故bₙ≥1，从而严格递减。n=1到2则相等，不能忽略这个边界。'))],
       conclusion=[T('正确序号：①③④。')],pitfalls=['数值递推正确不能保证分类证明正确；前缀与后缀不能混用。'],related_units=['intro'])
    units=[intro,food,method,ball,shooting,boxes,concept,ball3,weather,coin]
    return {'schema_version':2,'title':'马尔科夫链：从状态转移到数列通项','short_title':'概率与数列 / 马尔科夫链','level':'高中数学',
       'prerequisites':['全概率公式','等比数列','一阶递推'], 'learning_goal':'保留建模、递推、构造和完整证明，理解同一方法在不同状态中的应用。',
       'coverage':{'included':['四道原例题','一个合并通法','四组配套自测及解答'],
          'omitted':[{'content':'与数学主线无关的AI底层逻辑或泛化延伸','reason':'按改版要求省略非核心内容'},
                     {'content':'末尾舱室粒子留练','reason':'不属于用户修订稿的四组自测，原视频未展开；原帧保留在原始材料中'}],
          'basis':'内容依据用户修订稿；原视频时间继承参考区间，未重新逐秒校准；课件题源标注未外部检索'},
       'sections':[{'id':f's{i+1}','title':title,'start':a,'end':b,'origin':'human'} for i,(title,a,b) in enumerate([
          ('01 识别状态与转移',0,74),('02 食物选择与奇偶最值',18,602),('03 没有提示时：寻找不动点',603,721),
          ('04 传球中的状态聚合',764,1078),('05 投篮者的概率',1078,1386),('06 盒间颜色的传递',1386,1604),('07 迁移与自测',0,1627)])],
       'units':units,'figures':[{'id':'food-paths','unit_id':'food','frame_id':'f000300000','decision':'embed',
          'reason':'状态路径图保留互斥穷尽的两条路径及概率标签，正文公式难以替代这一视觉结构','crop':[65,445,595,435]}]}
