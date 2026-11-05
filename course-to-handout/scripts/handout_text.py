"""Typed, once-only normalization; formulas never pass through text escaping."""

TEXT_MATH={'′':r'\ensuremath{{}^{\prime}}','″':r'\ensuremath{{}^{\prime\prime}}','∞':r'\ensuremath{\infty}',
           '≤':r'\ensuremath{\leq}','≥':r'\ensuremath{\geq}','≠':r'\ensuremath{\ne}','∈':r'\ensuremath{\in}',
           '→':r'\ensuremath{\to}','⇒':r'\ensuremath{\Rightarrow}','±':r'\ensuremath{\pm}',
           'λ':r'\ensuremath{\lambda}','μ':r'\ensuremath{\mu}','α':r'\ensuremath{\alpha}','β':r'\ensuremath{\beta}'}
TEXT_MATH.update({c:r'\ensuremath{{}_'+str(i)+'}' for i,c in enumerate('₀₁₂₃₄₅₆₇₈₉')})
TEXT_MATH.update({c:r'\ensuremath{{}^'+str(i)+'}' for i,c in enumerate('⁰¹²³⁴⁵⁶⁷⁸⁹')})
TEXT_MATH.update({c:r'\ensuremath{{}^{'+v+'}}' for c,v in {'⁺':'+','⁻':'-','⁼':'=','⁽':'(','⁾':')','ⁿ':'n','ⁱ':'i'}.items()})
TEXT_MATH.update({c:r'\ensuremath{{}_{'+v+'}}' for c,v in {'ₙ':'n','ᵢ':'i','ₖ':'k','ₘ':'m','₊':'+','₋':'-','₌':'='}.items()})
TEXT_MATH.update({c:'('+str(i)+')' for i,c in enumerate('①②③④⑤⑥⑦⑧⑨⑩',1)})
ESCAPES={'\\':r'\textbackslash{}','{':r'\{','}':r'\}','$':r'\$','&':r'\&','#':r'\#','%':r'\%','_':r'\_','~':r'\textasciitilde{}','^':r'\textasciicircum{}'}
ROMAN={'Ⅰ':'I','Ⅱ':'II','Ⅲ':'III','Ⅳ':'IV','Ⅴ':'V','Ⅵ':'VI','Ⅶ':'VII','Ⅷ':'VIII','Ⅸ':'IX','Ⅹ':'X'}
ACCENTS={'\u0300':'grave','\u0301':'acute','\u0302':'hat','\u0303':'tilde','\u0304':'bar','\u0307':'dot','\u0308':'ddot','\u20d7':'vec'}
TEXT_MATH.update({'µ':r'\ensuremath{\mu}','℃':r'\ensuremath{{}^{\circ}\mathrm{C}}','℉':r'\ensuremath{{}^{\circ}\mathrm{F}}','°':r'\ensuremath{{}^{\circ}}','Å':r'\ensuremath{\mathring{\mathrm{A}}}'})

def math_character(ch):
    cp=ord(ch)
    return (0x1D400<=cp<=0x1D7FF or 0x2100<=cp<=0x214F or 0x2190<=cp<=0x22FF
            or 0x27C0<=cp<=0x27FF or 0x2980<=cp<=0x2AFF
            or ch in 'αβγδεζηθικλμνξοπρςστυφχψωΓΔΘΛΞΠΣΥΦΨΩϑϕϖϱϰϵ')


def text_tex(value):
    out=[];value=str(value);i=0
    while i<len(value):
        ch=value[i]
        if i+1<len(value) and value[i+1] in ACCENTS and (ch.isascii() and ch.isalpha() or math_character(ch)):
            atom=ch;i+=1
            while i<len(value) and value[i] in ACCENTS:
                atom='\\'+ACCENTS[value[i]]+'{'+atom+'}';i+=1
            out.append(r'\ensuremath{'+atom+'}');continue
        if ch in TEXT_MATH:out.append(TEXT_MATH[ch])
        elif ch in ROMAN:out.append(ROMAN[ch])
        elif math_character(ch):out.append(r'\ensuremath{'+ch+'}')
        else:out.append(ESCAPES.get(ch,ch))
        i+=1
    return ''.join(out).replace('\n','\n\n')


def rational_tex(value):
    from handout_math import fraction
    f=fraction(value);sign='-' if f<0 else '';f=abs(f)
    return sign+str(f.numerator) if f.denominator==1 else sign+r'\frac{'+str(f.numerator)+'}{'+str(f.denominator)+'}'


def claim_tex(block):
    from handout_math import fraction
    if block['type']=='sequence':
        v=block.get('variable','p');c,b=(rational_tex(block[x]) for x in ('constant','base'));k=fraction(block['coefficient'])
        index=block.get('index','n');sign='-' if k<0 else '+'
        return v+'_{'+index+'}='+c+sign+rational_tex(str(abs(k)))+r'\left('+b+r'\right)^{'+index+r'-1},\quad '+index+r'\ge2'
    if block['type']=='coin_recurrence':
        terms=[rational_tex(c)+r'p_{n-'+str(i+1)+'}' for i,c in enumerate(block['coefficients'])]
        return 'p_n='+'+'.join(terms)+r',\quad n\ge4'
    direction='开头' if block['direction']=='prefix' else '结尾'
    return r'\text{按'+direction+r'分类：}\quad'+r',\quad'.join(r'\mathrm{'+p+'}' for p in block['patterns'])
