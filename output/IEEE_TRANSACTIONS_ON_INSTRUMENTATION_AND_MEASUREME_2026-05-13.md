# 论文分析报告: IEEE TRANSACTIONS ON INSTRUMENTATION AND MEASUREMENT, VOL. 73, 2024

- **评分**: 6.1/10
- **分析时间**: 2026-05-13T23:01:37.153572

## 摘要
Depressive disorder has become a common problem
among higher education students, but it often gets undiagnosed
and untreated due to unrecognized symptoms, poor access to
medical resources, and fear of stigma. To improve the situation,
automatic depression detection would be essential. In this article,
we explore the feasibility of depression detection in higher educa-
tion students using their behavioral data automatically collected
by the university system. First, a DeepFM network, which can
not only take discrete–continuous mixed features as its input but
also can learn linear and nonlinear relations between the input
and the output, is presented for depression detection. A modified
focal loss (MFL) function is then proposed to alleviate data imbal-
ance impact caused by the fact that the proportion of healthy
students outweighs those diagnosed with depression significantly.
To verify the effectiveness of the proposed method, behavioral
data from 3218 students were collected, of which 179 were
diagnosed with depression by university psychologists using
PHQ-9 scale scores. Fivefold cross validations are performed, and
the experiment results have illustrated that DeepFM obtains the
highest average accuracy compared with multilayer perceptron
(MLP), factorization neural network (FNN), and product-based
neural network (PNN), demonstrating the effectiveness of the
proposed framework for depression detection among university
students.
Index Terms— Campus big data, data imbalance, deep learn-
ing, DeepFM, depression detection.
NOMENCLATURE
Xs
Behavioral features of the sth student.
ys
Ground truth of the sth student.
X s
d
Discrete features after one-hot coding of the
sth student.
X s
c
Continuous features after min–max
normalization of the sth student.
Manuscript
received
7
September
2023;
revised
20
January
2024;
accepted 6 February 2024. Date of publication 12 June 2024; date of current
version 21 June 2024. This work was supported in part by Shaanxi Key
Technology Re

## 方法论

### method-001 DeepFM-based Depression Detection Framework [模型架构]

该整体框架以DeepFM网络为核心分类器，接收预处理后的离散-连续混合学生行为特征，通过嵌入层降维、FM与DNN双组件并行学习特征间的线性与非线性交互，最终输出抑郁概率。训练时采用Modified Focal Loss缓解类别不平衡，优化器为SGD。整个过程从数据清洗、特征编码到模型训练和评估构成完整的抑郁检测流程。

**创新点**:
- 首次将DeepFM应用于校园大数据环境下的学生抑郁检测。
- 设计混合特征处理流水线，无缝集成离散与连续行为数据。

**输入**: 学生行为数据记录 (Xs, ys)，包含35维离散与连续特征。
**输出**: 学生抑郁的预测概率p及二分类预测标签\hat{y}。

**步骤**:
对离散特征进行one-hot编码，转化为高维稀疏向量X_s_d。
对连续特征进行min-max归一化，得到向量X_s_c。
通过嵌入层对X_s_d降维，然后与X_s_c拼接，得到模型输入X_s。
将X_s同时送入FM组件和DNN组件，分别计算FFM和FDNN。
将FFM与FDNN求和，经sigmoid激活输出抑郁概率p。
利用p和真实标签ys计算Modified Focal Loss，通过SGD更新模型参数。

**关键公式**:
$$p = \sigma(F_{FM} + F_{DNN})$$
$$\hat{y} = \begin{cases} 1, & \text{if } p > 0.5 \\ 0, & \text{otherwise} \end{cases}$$

### method-002 DeepFM Network Architecture [模型架构]

DeepFM由因子分解机（FM）组件和前馈深度神经网络（DNN）组件并联构成。FM组件捕捉特征的一阶线性重要度和两两特征的低维交互，DNN组件通过多层全连接网络学习高阶非线性关系。两者共享输入X_s，各自的输出相加后通过sigmoid得到最终预测。该设计能够同时利用线性和非线性信号，特别适合离散-连续混合输入。

**创新点**:
- 针对学生行为数据中离散与连续特征的混合特性，采用嵌入层降维后统一输入。
- 并行学习线性（FM）和非线性（DNN）特征交互，无需额外特征工程。

**输入**: 拼接后的特征向量X_s（维度d）。
**输出**: FM组件输出FFM与DNN组件输出FDNN，最终合并为抑郁概率p。

**步骤**:
定义FM的一阶权重w和隐向量矩阵V（维度d×k）。
计算FM输出: FFM = w^T [1; X_s] + sum_{i<j} (v_i · v_j) x_i x_j。
将X_s输入DNN组件，经过FC1(256)→ReLU→Dropout→FC2(128)→ReLU→Dropout→FC3(64)→ReLU→Dropout→FC4(1)得到FDNN。
将FFM与FDNN相加，通过sigmoid得到p。

**关键公式**:
$$F_{FM} = w \begin{pmatrix} 1 \\ X_s \end{pmatrix} + \sum_{i=1}^{d-1} \sum_{j=i+1}^{d} v_i v_j^T x_i x_j$$

### method-003 Modified Focal Loss (MFL) [损失函数]

Modified Focal Loss是针对高度不平衡的抑郁检测任务提出的损失函数。它在Focal Loss的基础上引入训练集类别分布信息，通过函数f(λ,S1,S0)增大正类（少数类）的梯度缩放因子，使模型在训练中对少数类样本施加更大的惩罚，从而缓解模型偏向多数类的问题。同时利用正弦函数调制难易样本的权重，使得难分类样本获得更高关注。

**创新点**:
- 将训练数据的类别分布作为动态因子嵌入损失权重，自适应调整少数类的梯度长度。
- 结合正弦函数与Focal Loss，同时处理类不平衡和难易样本不平衡。
- 通过分段函数f(λ,S1,S0)防止极端不平衡下梯度过大导致不稳定。

**输入**: 模型输出概率p与真实标签ys，训练集中各类别样本数S1, S0。
**输出**: 标量损失值L，用于反向传播更新网络参数。

**步骤**:
根据预测概率p和真实标签ys计算\hat{p}：若ys=1，\hat{p}=p，否则\hat{p}=1-p。
计算类别不平衡度 λ = -1/2 log_{S1} S0。
根据λ计算分布因子f：若λ≤1则f=(S0/S1)^{1/2}，否则f=(S0/S1)^{1/8}。
计算MFL: L = -ys [1 - sin(π/2 \hat{p})]^f (1-\hat{p})^{γ} log\hat{p} - (1-ys) [1 - sin(π/2 \hat{p})] (1-\hat{p})^{γ} log\hat{p}。
基于链式法则计算梯度∂L/∂θ，通过SGD更新参数。

**关键公式**:
$$\hat{p} = \begin{cases} p, & \text{if } y_s = 1 \\ 1 - p, & \text{otherwise} \end{cases}$$
$$\lambda = -\frac{1}{2} \log_{S_1} S_0$$
$$f(\lambda, S_1, S_0) = \begin{cases} (S_0/S_1)^{1/2}, & \text{if } \lambda \leq 1 \\ (S_0/S_1)^{1/8}, & \text{otherwise} \end{cases}$$
$$L = -y_s \left[1 - \sin(\frac{\pi}{2} \hat{p})\right]^{f(\lambda, S_1, S_0)} (1-\hat{p})^{\gamma} \log \hat{p} - (1 - y_s) \left[1 - \sin(\frac{\pi}{2} \hat{p})\right] (1-\hat{p})^{\gamma} \log \hat{p}$$

## 核心观点

### claim-001 [empirical]
**前提假设**: 数据预处理（缺失值插补、异常值移除、归一化等）正确执行，未引入偏差。; 五折交叉验证的划分方式使训练集与测试集分布一致，结果具有泛化代表性。; 所有对比模型均使用相同的MFL损失函数和相同的超参数调优策略。; 性能评估中使用的准确率、敏感度等指标能够全面反映模型的抑郁检测能力。
**主张**: DeepFM-MFL在该校园行为数据集上的平均准确率达到96.4%，显著优于MLP、FNN、PNN等基线模型。
> 原文: The experiment results have illustrated that DeepFM obtained the highest average accuracy 96.4% compared with multilayer perceptron (MLP) 93.3%, factorization neural network (FNN) 91.8%, and product-b

### claim-002 [empirical]
**前提假设**: 敏感度的提升确实源于MFL的设计，而非训练过程中的随机波动或其他超参数影响。; 实验中使用的正负样本划分标准（PHQ-9分数>4）准确反映了真实抑郁状态。; 交叉熵损失和Focal Loss的对比实验中，Focal Loss的γ参数设置为与MFL相同的3，保证了可比性。
**主张**: Modified Focal Loss（MFL）相比交叉熵损失和标准Focal Loss能显著提升模型对抑郁样本的敏感度。
> 原文: Fig. 5 shows the sensitivity values of four models with different loss functions. The figure demonstrates that the proposed loss function is superior to CE loss and FL under the depression detection t

### claim-003 [comparative]
**前提假设**: 消融实验中通过移除某一类特征来衡量其重要性，假设特征之间没有复杂的非线性依赖导致交互效应被忽略。; 数据集中的四类数据覆盖了影响学生抑郁的主要行为方面，不存在其他未测量但关键的混杂变量。; 模型对不同类型数据的敏感度变化直接反映其在决策中的贡献度，且不受特征维度高低的影响。
**主张**: 在行为数据中，学业数据和日常行为数据对抑郁检测的重要性最高，其次是身体素质和人口统计学数据。
> 原文: The four types of data in descending order of importance are academic data, daily data, physical quality data, and demographic data. ... This illustrates that depression among higher education student

### claim-004 [design]
**前提假设**: 行为数据与抑郁之间确实存在显著的线性和非线性关联，缺一不可。; FM与DNN组件的输出通过简单求和合并是合适的融合方式，不会造成信号冲突或抵消。; 训练过程中模型没有因为参数增多而导致过拟合，从而能够发挥双组件的优势。
**主张**: DeepFM同时学习线性（FM组件）和非线性（DNN组件）关系，比单独使用FM或DNN的敏感度更高。
> 原文: DeepFM has achieved the highest sensitivity compared with FM and DNN. In addition, FM outperforms DNN, indicating that the linear correlation between behavioral data and students’ depression is more p

### claim-005 [empirical]
**前提假设**: f()函数与γ的最优值是针对当前数据集和任务搜索得到的，在其他数据集上可能需要重新调优。; 敏感度和G-mean的提升源于MFL内部机制，而非网络结构或训练技巧的变化。; 实验中使用的统计检验（配对t检验）正确拒绝了无差异的零假设。
**主张**: MFL中的类别分布函数f(λ,S1,S0)以及参数γ=3是提高敏感度和G-mean的关键设计。
> 原文: This figure shows that sensitivity and G-mean are improved when f = f(). ... both sensitivity and G-mean reach their maximum when γ is equal to 3.

### claim-006 [empirical]
**前提假设**: 各子群之间的数据分布差异较小，模型未因某一群体数量过少而失效。; 性别和入学年份以外的未测量因素（如专业、家庭背景）不会在子群间造成系统性偏差。; 子群分析中使用的样本划分足够代表性，显著性检验的统计功效充足。
**主张**: 在不同性别和入学年份的学生子群中，DeepFM-MFL的检测敏感度没有显著差异，模型具有一定的人群公平性。
> 原文: there indeed do not exist significant differences across 'gender' and 'year of entry'.

## 局限性分析

- **[experiment]** (critical) 数据集存在极端不平衡（179例抑郁 vs 3039例健康），但论文仅以平均准确率（96.4%）作为主要指标，未报告敏感度、特异度、F1分数或AUC等更适合不平衡场景的指标。高准确率可能主要来自对多数类的正确预测，无法证明模型对少数类（抑郁样本）的有效性。
  > 建议: 应在五折交叉验证中报告每一折的敏感度、特异度、精确度、F1分数、G-mean和AUC，并给出均值和标准差，必要时进行McNemar检验或配对t检验以确认提升的统计显著性。

- **[experiment]** (medium) 消融实验仅展示了不同损失函数的影响，未对MFL中的关键超参数γ和类别分布函数f(λ,S1,S0)进行充分的敏感性分析（例如γ在[1,5]范围内的变化对性能的影响），也未与其他常见的不平衡处理策略（如SMOTE、类别加权、阈值移动）进行系统性比较。
  > 建议: 补充超参数γ的网格搜索或敏感性曲线；增加与经典重采样/加权方法的对比实验，并在相同评估协议下报告结果。

- **[generalization]** (high) 数据来自单一大学（3218名学生），阳性样本仅179例，且行为数据特征与该大学的信息系统高度绑定（如校园卡消费、图书馆门禁等），模型能否迁移到其他高校、其他类型教育机构或更广泛的人群尚不可知。此外，数据采集时间段未明确，模型对不同学期、不同年份新生群体的适应性存疑。
  > 建议: 在至少两个独立学校或不同年份的数据上进行外部验证；若无法获取外部数据，应讨论特征分布的稳定性并提供基于时间分割的验证结果。

- **[ethics]** (high) 自动抑郁检测涉及高度敏感的健康信息，论文未讨论学生的知情同意过程、数据脱敏方案以及模型误判（假阳性/假阴性）可能给学生带来的心理负担、标签化和隐私泄露风险。尽管主张人群公平性，但仅检验了性别和入学年份，未考察可能导致歧视的其他敏感属性（如专业、家庭经济状况、民族等）。
  > 建议: 增加伦理申明，明确数据采集是否经过IRB批准及学生知情同意；讨论假阳性结果的潜在危害及后续人工介入机制；增加对更多敏感属性的公平性评估，并采用等机会性、平均优势比等公平性度量。

- **[reproducibility]** (high) 论文未提供代码链接或数据可获得性说明，MFL中类别分布函数f(λ,S1,S0)的具体形式、特征工程细节（如离散特征分桶策略、连续特征归一化边界）以及训练超参（学习率、批大小、优化器等）未完整公开，导致结果难以复现。
  > 建议: 在附录中给出完整的超参数列表与训练配置；如数据因隐私无法公开，应详细描述特征分布和预处理流程，并考虑提供匿名化后的合成数据或特征统计信息。

- **[experiment]** (medium) 使用PHQ-9量表得分作为诊断标签，但该量表为自评工具，与临床结构化访谈存在差异，可能引入标签噪声。论文未报告量表施测的时间窗口、是否有重复测量以及心理专家的诊断一致性，这会影响模型学习到的行为-抑郁关联的真实性。
  > 建议: 明确标签的生成依据（如PHQ-9总分、分界点及心理专家复核流程），并分析评分者间一致性；若存在纵向数据，可利用多次测量来减少标签噪声。

## 总结
提取 3 个方法，6 条观点，发现 6 条局限性。