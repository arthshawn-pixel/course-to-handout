# 跨学科字体与记号

## 选择数据类型

正文用text块，完整公式用math块。复杂行内公式可单独列为math块，不把任意LaTeX塞进text。普通文字会由程序转义一次；math的latex字段不再转义。

```yaml
- type: text
  text: "在ℝⁿ上讨论梯度∇f，向量𝐱与标量x含义不同。"
- type: math
  latex: |
    \frac{\partial u}{\partial t}=\kappa\nabla^2u,\qquad x\in\mathbb{R}^n.
- type: chem
  formula: "Fe^3+ + 3 OH- -> Fe(OH)3 v"
- type: quantity
  value: "9.81"
  unit: '\metre\per\second\squared'
```

chem使用mhchem v4记号；quantity使用siunitx，value接受数字、科学计数和括号不确定度，如1.2e-3、1.23(4)。代数表达式用math。math中也可显式使用\ce、\qty、\unit、\ang；仍受公式命令白名单约束。不能用宏包安装、文件读写、\input或任意TeX文档替代公式。

## 字体与保真

包内assets/fonts包含思源宋体Regular、Termes正文四种字形、Termes Math、STIX Two Math及来源/哈希/许可。默认直接按包内相对路径加载，无需把字体安装到系统。数学默认STIX Two；要沿用Termes，文档根设置：

```json
{"typography":{"math_font":"termes"}}
```

正文fontspec与数学unicode-math分别配置。STIX Two侧重科学技术符号覆盖；它和Termes都只对实际检查过的样例给出兼容结果，不宣称包含全部Unicode字符。更多字符出现缺字时看layout-report.json和compiler.log，使用已核实语义的标准LaTeX写法或保留原图。

文字中的常见数学运算符、希腊变量、数集、上下标和组合重音转入数学字体。Plane1数学字母保留原有粗体、斜体、花体、Fraktur与黑板体，不做丢失样式的NFKC转换。罗马卷号Ⅰ/Ⅱ等单独按文本处理。文本5%与货币符号按文本转义；金融推导推荐用USD/CNY等货币代码明确币种。

不要用字体修复替代符号识别：ν与v、ρ与p、l与1、O与0、负号、上下标位置不确定时，应对照画面/字幕。原始内容保留，不按字形相近自动改数学语义。

## 各学科推荐写法

| 场景 | 受支持的常见表达 |
|---|---|
| 微积分/微分方程 | \frac{d}{dx}、\partial、\nabla、\int/\iint/\iiint/\oint/\oiint/\oiiint、\lim、\sum、\prod |
| 线代/概率/优化 | matrix/pmatrix/bmatrix、\det、\mathbf/\symbf、\mathbb、\mathcal、\mathfrak、转置、内积、范数、\otimes、\operatorname{Var}/Cov |
| 物理 | 希腊字母、\hbar、\vec、\hat、\dot、\ddot、场算符、bra/ket用\langle与\rangle显式写 |
| 化学/物化 | \ce{H2O}、电荷Fe^3+、同位素^{14}_{6}C、反应箭头->/<=>、沉淀v、物态(g)/(l) |
| 金融/经济/管理 | 贴现求和、条件期望、协方差、随机微分、估计量\widehat、约束优化、百分数/基点 |
| 工程 | 复数阻抗、传递函数、应力张量、角度、SI单位、前缀、科学计数 |

变量通常斜体；化学元素/运算符/单位用正体。不要加载physics宏包后复用其\qty：本模板的\qty属于siunitx。普通反应式可使用chem；有机结构式、复杂电路、机械图和过程图不靠字体重建，保留清晰原图或使用宿主确实可用且已核对的绘图工具。

## 内容核验与排版核验

字体检查不是内容正确性检查。微积分复核极限/可微与积分条件；线代复核矩阵维数和可逆性；物理/工程复核量纲、符号约定与边界；化学复核元素、电荷守恒、物态和反应条件；经管复核单位、时期、百分比/基点、贴现时点及假设。已实现自动枚举仅限handout_math.py支持的模型；其他内容用实际专业复查记录覆盖范围，不伪造自动程序结果。

## 可执行检查

```text
python scripts/lecture.py doctor --engine tectonic
python scripts/lecture.py notation-sample NEW_JOB --math-font stix2
python scripts/lecture.py notation-sample ANOTHER_NEW_JOB --math-font termes
```

notation-sample创建自制跨学科符号文档并用正式渲染器编译，缺字/溢出等审计异常时返回错误。随后渲染PNG实际检查上下标、字体区别、长公式、化学式、单位及分页。改变字体、字符转换器或模板会使渲染缓存失效。

依据：[STIX官方](https://github.com/stipub/stixfonts)、[TeX Gyre](https://ctan.org/pkg/tex-gyre)、[unicode-math](https://ctan.org/pkg/unicode-math)、[mhchem](https://ctan.org/pkg/mhchem)、[siunitx](https://ctan.org/pkg/siunitx)。实际编译用随运行环境缓存的TeX bundle；不能把官网最新版本号冒充本机已安装版本。
