# 文章图片获取问题处理建议

> 来自[飞书知识问答](https://ask.feishu.cn/topic?referrer=doc_qa)，AI 基于相关知识生成

**QCon AI驱动UI自动化测试分享完整图文版**
本文档由 [飞书 aily](https://aily.feishu.cn/?&open-from=feishu_doc) 创建，汇总了2026年QCon全球软件开发大会上，来自小红书、淘宝等公司的 **AI驱动UI自动化测试** 工程实践。

---

**一、小红书\-GUI Agent 在智能化测试中的工程落地实践** **业务背景与痛点**
传统UI自动化测试面临四大困境：

1. **维护成本极高** ：元素定位\(XPath\)随版本频繁变更，小红书每周一版，结构性矛盾

2. **跨端成本×3** ：iOS/Android/鸿蒙控件和坐标完全不一致，同一功能三端三套脚本

3. **断言能力弱** ：传统断言只能做简单的元素存在性判断，无法理解语义和视觉内容

4. **执行只占50%** ：测试投入时间分布中，执行用例占50%，测试方案和用例生成占35%

**自动化测试全流程工作流**
（图 1） 从需求输入（PRD/Figma/提测文档）开始，经生成测试方案、生成测试用例、文档分析、风险评估、造数\&amp;环境准备、执行引擎等步骤，最终完成数据汇总、commit人工审核、知识沉淀反馈。其中，生成测试方案环节下分生成测试用例、文档分析、风险评估、造数\&amp;环境准备、执行引擎等子步骤，执行引擎又包含读取自然语言用例、识别\+调度调用、调用RDC Skills、LLM视觉断言等操作。

![Image](https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/authcode/?code=ZTI4NDZjMWZkN2Y2Y2ZlNmQ5OTgzYWM5YjgzNTVlMDBfN2U5YjQ3YzhkNjdjZmQ2NmEwNjJmNzhiNTEwOTI2ODJfSUQ6NzY0NTE5NTQzMjIzMjE2MDQ0OV8xNzgwMDM2OTY3OjE3ODAxMjMzNjdfVjM)

**执行引擎架构**
三层架构分离关注点：

1. **顶层：执行引擎Agent（Coding Agent）** ：基于GPT 5\.4/Sonnet 4\.6，负责全局调度、核心逻辑生成

2. **中层：质效Skill仓库** ：封装可复用能力单元（计划生成skill、环境准备skill、用例生成skill、错误检测skill、报告生成）

3. **底层：视觉理解Agent** ：基于gemini\-flash\-9\.1，提供低成本确定性的视觉原子操作
（图 2） 执行引擎Agent（Coding Agent）基于GPT 5\.4和Sonnet 4\.6，负责用例生成/编辑、计划生成/编辑、知识库\&amp;记忆沉淀、路径图谱等。质效Skill仓库包含计划生成skill、环境准备skill、用例生成skill、错误检测skill、报告生成等，开发时先放repo，后续再抽离为独立Skill包。视觉理解Agent基于gemini\-flash\-3\.1，提供低成本确定性视觉原子操作，包括视觉断言和视觉定位。该架构还涉及执行异常反馈、任务管理平台等内容。

![Image](https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/authcode/?code=ODQ5Y2NjYjg4OWYyMTczMjViZDgwNDU1NmI5NmUxMzRfZjZjNjhlODFjODQ5ZDM1NDdkYzhmMDJhNjA1N2U3MjdfSUQ6NzY0NTE5NTQzMDAxNjA0NDIyNV8xNzgwMDM2OTY3OjE3ODAxMjMzNjdfVjM)

**知识库分级上下文**
（图 3） 从PRD/代码Diff/接口协议/设计稿等输入，经需求级、产品级、经验级三层处理，最终与主动学习长期记忆OpenViking交互。需求级处理单次测试输入，产品级理解业务，经验级提供基础认知。各层间有虚线箭头连接，体现信息流转关系，与上下文介绍的OpenViking数据库功能相呼应。

![Image](https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/authcode/?code=NzNhMjk5YjgzMzBkNzc3N2M4ZWI3OWE1NWZmOWE1MjBfNTdhNmYzZDk5NTk3YTRmN2JkYmMzZmY1ODE3NmE0YmZfSUQ6NzY0NTE5NTQzMDU4NjUzNTEwMV8xNzgwMDM2OTY3OjE3ODAxMjMzNjdfVjM)

**OpenViking** 是字节跳动火山引擎 Viking 团队于 2026 年 1 月开源的 **上下文数据库（Context Database）** ，专为 AI 智能体（Agent）打造的数据库，主要适用于多 Agent 协同、长期记忆管理、复杂任务执行等场景。该数据库采用 viking://文件系统范式，将智能体的 **记忆、资源与技能** 进行统一组织管理，依托分层加载机制按需供给上下文，在减少 Token 消耗的同时提升运行效率，结合目录式检索优化信息召回效果。功能上，OpenViking 支持 **多租户、多用户及多 Agent 隔离** ，且能在会话结束后自动沉淀长期记忆，实现智能体能力的持续积累与自我优化，既有效降低开发者的上下文管理成本，也能显著提升 OpenClaw 等智能体的整体运行表现。 **它的核心主张是：Everything is a File**

[OpenViking官方文档](https://www.volcengine.com/docs/82379/2288685?lang=zh) [OpenViking GitHub仓库](https://github.com/volcengine/OpenViking/blob/main/README_CN.md)

**实战验证成果**
春节大促期间规模化落地：

- **自动化率** ：75%

- **设备×场景组合** ：106 × 428

- **兼容性Bug自动召回率** ：68%

- **累计自动化执行用例次** ：12\.3w\+

- **用例采纳率** ：92%

- **需求覆盖率** ：66%

- **用例渗透率** ：63%

---

**二、其他自动化测试Topic** **1、58\-基于业务流程管理的客户端AI Agent智能化测试实践** **客户端智能化测试技术架构**
（图 4） 用户输入层包括自然语言任务描述、Web管理平台等。智能规划执行引擎有规划节点、执行节点等。多模态分析引擎包含截图获取、XML解析等步骤。跨平台设备控制器层有Android、iOS等控制器。执行结果输出层有测试报告生成等。右侧是反馈与自愈系统，有实时反馈、失败原因分析等。该图与文档中介绍的客户端智能化测试技术架构内容相关，直观呈现了架构各部分及流程。

![Image](https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/authcode/?code=ZjEwYTk2N2IyMTYwNGFmYmYzNTA5YzUxZDA0NDgxMTJfNDVjOTNiY2ZhY2M3N2Y4YmQ5YzVmMGU2YjlmMWQyZGRfSUQ6NzY0NTE5NTQzMDU5MDY2Mzg5M18xNzgwMDM2OTY3OjE3ODAxMjMzNjdfVjM)

**三层架构协同体系**
（图 5） 架构呈现为三层，最上层是业务流程管理层，包含统一业务流程定义、模板库管理、参数配置中心；中间是Agent决策层，有模板智能匹配、多平台适配决策等环节，还涉及异常自愈调度和执行策略优化；最下层是Skills执行层，涵盖iOS、Android、通用、Harmony Skills，对应iOS、Android、鸿蒙设备执行平台。此图与上下文阐述的智能化测试技术架构相关。

![Image](https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/authcode/?code=Y2U1MjExNWYyZTJiYzc5OWQ2YTNkNDYxMGM1YjFiZWZfNzVmNjFlNzZiNTRmODVhZGVmZmQ1YjI5ZWYzOGI0OWVfSUQ6NzY0NTE5NTQyOTgxNTU4NjAwNV8xNzgwMDM2OTY3OjE3ODAxMjMzNjdfVjM)

**亮点1：Agent Skills能力矩阵**

|设备控制|应用操作|交互操作|验证断言|
|---|---|---|---|
|connect\_device|launch\_app|tap|assert\_text|
|take\_screenshot|close\_app|long\_press|assert\_image|
|get\_device\_info|get\_packages\_info|swipe|assert\_element|
|install\_app|clear\_data|input\_text|assert\_data|
|system\_settings|permission\_control|gesture|generate\_report|

**亮点2：自愈能力\-四层防护体系**
（图 6） 从智能弹窗处理开始，依次是点击位置验证、上下文记忆决策、 addCriterion\&gt;

![Image](https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/authcode/?code=MjE4MTZkN2RiYTFiY2M1YWVhYTY3MjE3N2I1NzQ2YTVfODRkYjIwYjBhYzIwZDZjODkxNmU4ZTYyYjZkNmY4MmFfSUQ6NzY0NTE5NTQzMDAxNjMwNjM2OV8xNzgwMDM2OTY3OjE3ODAxMjMzNjdfVjM)

**2、Ubiquiti\-从单点辅助到 Agent 闭环** **核心技术架构（Skills \+ MCP）**
（图 7） 图片展示了Ubiquiti从单点点

![Image](https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/authcode/?code=N2MxZjg1OWJlOTNmMjIxNWM5OTE5YmMzMzQxYzVhMzJfOTk4YzUyNzY2YjcxZDEyZmM5ZjliNmU5MDMwYTRkOTFfSUQ6NzY0NTE5NTQyOTYxNzczMjgyNV8xNzgwMDM2OTY3OjE3ODAxMjMzNjdfVjM)

**亮点：基础测试设计能力的封装**
利用微软 PICT 算法封装为 Agent Skills，给用例设计做减法。如8 参数系统，PICT 能将 19,440 个穷举用例压缩至仅 30 个（减少 99\.88%），同时完成覆盖所有参数的正交。
（图 8） 左侧是PIN Unlock功能的测试参数设置，包括PIN长度、键盘布局、PIN分配、读卡器类型等。右侧是生成的4个测试用例，涵盖不同PIN长度、键盘布局、PIN分配及读卡器类型组合，预期输出均为正常解锁。该图片与上文提到的Agent Skills能力矩阵中验证断言相关，直观呈现了Agent Skills在测试用例生成方面的应用。

![Image](https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/authcode/?code=ZmNhYjkzYmQ0ZmUzMmQyNDFiYmU0NWFiM2YzZGU0YmZfZTdiMTFlNDM4ZDZhZDY4OTU4ODQwNGUxMzA4ZjVkMjFfSUQ6NzY0NTE5NTQyOTE0MzY2MTc0N18xNzgwMDM2OTY3OjE3ODAxMjMzNjdfVjM)

**3、淘宝闪购\-AI驱动UI自动化提效实践** **技术架构**
（图 9） 左侧为人工编写部分，用例来源有蓝精灵 \- 新建用例、Chrome插件 \- 新建用例；右侧是AI智能生成部分，用例来源为蓝精灵 \- AI生成文本用例、蓝精灵 \- AI生成UI用例。中间从用例平台、AI AGENT、执行框架到执行环境多个层次进行架构呈现，其中AI AGENT包含元素识别与动作规划等功能。此图与上下文紧密相关，直观呈现自动化测试技术架构，辅助理解相关内容。

![Image](https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/authcode/?code=YjIzODE1NjcxYzQ1NDFkOWZmODdiYTllMTYzYTI5MjlfZWYwZTY3ZjcwMjdhNzQwZjFjYzkyMDA3MDllMTU3YTNfSUQ6NzY0NTE5NTQzMjc3OTQxODg0MV8xNzgwMDM2OTY3OjE3ODAxMjMzNjdfVjM)

**UI自动化核心执行流程**
（图 10） 用户输入自然语言后，经AI AGENT处理，进行元素识别和动作规划，再由AI断言。AI AGENT层包含多模态理解、意图识别、坐标生成等。执行框架层有Playwright PC端、Totoro APP端，对应PC运行环境和云真机/手机云。该图与上下文紧密相关，直观呈现了UI自动化核心执行流程及各环节技术支撑。

![Image](https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/authcode/?code=MGU2ZjYyNzdmYWFkNTZhOTMxODBjNjMyYzU5MGE4NzFfODEzYjE2Yjc5YjBkMDc3MTJmMzIxOGFmODkzYjEwNWVfSUQ6NzY0NTE5NTQzMjk1OTgyMzA0MV8xNzgwMDM2OTY3OjE3ODAxMjMzNjdfVjM)

**亮点1：原子ACTION封装**

|ACTION|动作描述|
|---|---|
|OPEN\.APP|打开网页|
|NAVIGATE|页面跳转|
|LEFT\.CLICK|点击坐标|
|TYPE|输入|
|SCROLL\_DOWN|向下滚动|
|SCROLL\_UP|向上滚动|
|SCREENSHOT|截图|
|WAIT|等待|
|SWIPE|滑动|
|DOUBLE\.CLICK|双击|
|LEFT\.CLICK\.DRAG|拖拽|

**亮点2：UI样式AI检测** **问题类别** ：
（图 11） 左侧为“空坑”，包含商品主图空白、豆腐块空白；中间为“元素堆叠”，有Toast重叠、组件遮挡、侵入状态栏；右侧为“内容异常”，包括NaN/undefined/null、小数精度超2位、乱码；最右侧为“白屏报错”，有页面完全空白、404/系统错误。这些问题是UI自动化测试中需重点关注和解决的，与文档中介绍的淘宝闪购\-AI驱动UI自动化提效实践内容相关。

![Image](https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/authcode/?code=NTU5OTc5MjE5N2I0Y2Q4ZWU3YzUyYWNhODY0MmVhNGRfNTgwMTA1MTBlYmI2NjBmNDQ1OTg0Yzk2ZjkyNWViZDZfSUQ6NzY0NTE5NTQzMjUyMzc2Mjg5Ml8xNzgwMDM2OTY3OjE3ODAxMjMzNjdfVjM)

**SFT优化流程** ：
（图 12） 流程从人工梳理图片集开始，经大模型产出描述、人工修正，再到数据湖，接着进行SFT微调，最后完成模型部署。该流程与文档中介绍的亮点2：UI样式AI检测相关，体现了从图片集整理到模型部署的优化过程，是AI驱动UI自动化提效实践中的重要环节。

![Image](https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/authcode/?code=YzQ5M2Y2ODZlNTM3ZmMyZWMzMDFhNDc1MWJiMzNjNzVfYTI0YjMzMDg5N2VkOTZhMDEzZDQ2NmI5YzM5NzIyNThfSUQ6NzY0NTE5NTQzMjU5OTU4ODAyOF8xNzgwMDM2OTY3OjE3ODAxMjMzNjdfVjM)

---

**三、总结** **1、四方案横向对比**

|维度|小红书|58同城|蔡明哲\(Ubiquiti\)|淘宝闪购|
|---|---|---|---|---|
|**核心定位**|AI Coding式自动化|业务流程\+Agent协同|单点到Agent闭环|AI视觉理解自动化|
|**架构设计**|三层：意图→探索→ **执行Skills**|三层：BPM→Agent→ **Skills**|混合：Playwright\+ **Skills** \+MCP|分层：Agent→框架→环境|
|**AI模型**|**GPT 5\.4/Sonnet 4\.6\+gemini**|GPT类（未披露）|GPT类（未披露）|**Qwen 2\.5 VL**|
|**执行模式**|**自主探索** \+自我学习|Plan\+ReAct双模式|Playwright **Agents**|纯视觉\+意图拆解|
|**知识沉淀**|分级上下文|**业务地图\+知识图谱**|知识图谱\+模板复用|模板库|
|**多端支持**|**iOS/Android/鸿蒙**|**iOS/Android/鸿蒙/PC**|**Web为主**|PC/APP双端|
|**断言能力**|AI断言|**AI断言\+规则断言**|AI断言|AI断言\+样式检测|
|**核心成效**|**75%自动化率**|**95%\+成功率**|**65%脚本效率提升**|样式问题检测|

**2、对我们的启发**
基于上述分析，我们对团队后续的AI驱动UI自动化测试建设，提出以下四点启发：

- **启发1：优先建设知识沉淀体系** 。四家均把 **知识库作为核心资产** 。我们应优先梳理核心业务链路、沉淀页面元素规范与历史用例，构建可被Agent直接调用的结构化知识地图。

- **启发2：分层架构 \+ AI/规则混合是稳定落地的关键** 。切忌追求“全AI、全自主”。应参考 **小红书的三层架构** ，在核心业务链路用规则保障绝对稳定，在探索性场景和复杂UI验证中发挥AI的灵活性。

- **启发3：从“点”开始，快速验证** 。借鉴 **蔡明哲团队的“先点后案”策略** ，可先用AI快速生成测试点，匹配敏捷开发节奏，再将其中 **高价值的场景沉淀为回归用例** ，避免初期陷入大而全的闭环建设困境。

- **启发4：自愈能力必须内置，而非人工兜底** 。参考 **58同城的四层防护** 与 **小红书的视觉兜底** ，必须将元素定位策略、弹窗处理等自愈逻辑内置于框架，否则自动化率越高，后期维护负担越重。

---

**四、业务中台UI自动化测试探索** **1、当前的探索**
（图 13） 意图层输入符合标准的自动化测试意图，经结构化业务描述后进入规划层，输入结构化任务描述，进行关卡任务分配、UI接口SUI分配、API调用SUI分配、DB重用SUI分配，生成测试计划。执行层输入YAML测试规格，通过UI执行（Playwright）、API调用（HTTP Client）、回放重用（SQL Executor）执行，输出结果集与报告、Alert规则生成、截图日志。

![Image](https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/authcode/?code=YmJjODNhYWRmMDdkZGJjODdiZjhmNDJiYTM5ZjdkNjhfMzY1NTc4NTBhNjAzNDRlODMwODBiMDIzYmIzMTQ4NmFfSUQ6NzY0NTE5NTQzMjIyNjI5NDk3NF8xNzgwMDM2OTY3OjE3ODAxMjMzNjdfVjM)

**示例业务流程**
清分商银白条将商银数据下单到清分，有如下测试用例。以逾期下单为例，测试流程：
1、修改白条的承诺付款日为小于当天的日期
2、平台端登录、进行手动下单
3、验证是否可以拦截

（图 14） 图片为商银手动下单测试记录表，重点突出“逾期场景 \- 融资条不允许多单场次”相关内容。其中，①逾期融资业务不允许手动下单，②提前融资业务不允许手动下单，③提前非融资业务和非融资业务不允许同时手动下单，④当日融资业务不允许部分下单，这些情况均标注为“柜单下仅存在融资条，且承诺付款日\&lt;当日”。该图片与上下文测试流程相关，是对逾期下单场景下不允许手动下单情况的测试记录呈现。

![Image](https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/authcode/?code=YmQ5OTcxZDJjNmU1N2QwYTE4YTgyZDA0MWQwMWM2YWJfOTFiOTMzMzE4OWNiYTFjM2NkOTM3MDRkMjkwZmIxZTlfSUQ6NzY0NTE5NTQzMjQzNTUzNTAzM18xNzgwMDM2OTY3OjE3ODAxMjMzNjdfVjM)

**测试记录**

|**步骤**|**操作类型**|**测试记录**|
|---|---|---|
|设置商银白条为提前下单|SQL|（图 15） 图片展示的是业务中台UI自动化测试中逾期下单测试记录界面。左侧为测试套件列表，显示了Suite名称、状态、执行时间等信息，其中“SpecCompletion”测试套件状态为“Passed”。右侧是“SpecCompletion”测试套件的详细执行记录，包括测试步骤、操作类型、测试记录等，如设置商银白条为提前下单、登录、手动下单等操作，还呈现了SQL语句及执行结果。该图片直观呈现了测试流程及记录，与上下文介绍的逾期下单测试流程相呼应。|
|登录|UI|（图 16） 图片展示的是业务中台UI自动化测试中登录操作的界面。左侧为测试流程，显示“登录”步骤。右侧是登录页面，有“登录”按钮，下方有“账号密码登录”“手机号登录”“企业微信登录”等登录方式选项，还设有“忘记密码”“企业微信登录”“注册”等链接。该图片与文档中以逾期下单为例的测试流程相关，直观呈现了登录操作的界面情况。|
|手动下单|UI|（图 17） 图片展示了逾期下单测试流程中手动下单步骤的界面。左侧界面有列表等内容，右侧界面显示一个弹出框，提示“订单申请失败”，框内有相关失败原因说明。该图片对应文档中逾期下单测试流程里“手动下单”这一操作类型的测试记录部分，直观呈现了手动下单时可能出现的系统反馈情况，为业务中台UI自动化测试探索中的当前探索内容提供了可视化参考。|

**2、思考和计划**

1. **【AI 的作用】** 依托 AI 能力，可有效弱化传统 UI 自动化的固有短板，在可控时间成本内，高效完成业务端到端验证。

2. **【人的价值】** 业务层面存在 AI 无法自主突破的认知边界，高质量测试知识库、标准化业务流程，是当前智能测试的核心资产。

3. **【AI 的局限】** 长链路复杂任务中，AI 单步执行成功率虽高，但多环节叠加后整体成功率会大幅衰减，需在各关键节点有机会去审核与纠错。

4. **后续计划**

    1. 从回归测试场景拆解原子化 Skill 能力，先落地固定意图场景实现业务收益，再逐步探索意图识别、任务自主规划能力。

    2. 同步调研并规划测试知识库体系建设，为后续智能化测试落地筑牢基础。

---

是否需要我帮你将所有图片单独整理成一个 **图片包文件** ？

![Image](https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/authcode/?code=ZjdiNDNmZTEyZDc4YjUzM2E2ODRmYjljMzk5YjdmMDhfOTQzNDI1OTZkNGFiZTM1MmUzZjlkY2JjZjdmYmQzNjlfSUQ6NzY0NTE5NTQzMDM4MDc2ODQ2OV8xNzgwMDM2OTY3OjE3ODAxMjMzNjdfVjM)

![Image](https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/authcode/?code=MWZiZWI1NzViNWYxZTQ0NjUwMzY4ZjIwZDdiM2RiODJfNWEyNWNkMDgwZTY4OTIzY2U5NGI0NmM5NGZjNDNlZjJfSUQ6NzY0NTE5NTQzMTM1Nzk3NTc1Ml8xNzgwMDM2OTY3OjE3ODAxMjMzNjdfVjM)

![Image](https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/authcode/?code=MGQ1MmUzMTJmYzgxNDYwYzgzYzU1N2I1ZmM2MzI5MWVfNDFkY2U2YWU4NDZmYTgyNWQyZDI4Yjk1ZDM3ZDM4NGVfSUQ6NzY0NTE5NTQzMTcxMDIxNTM3N18xNzgwMDM2OTY3OjE3ODAxMjMzNjdfVjM)

> (注：内容由 AI 生成，请谨慎参考）
