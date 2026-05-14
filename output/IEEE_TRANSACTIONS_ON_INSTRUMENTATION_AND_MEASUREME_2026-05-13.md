# 论文分析报告: IEEE TRANSACTIONS ON INSTRUMENTATION AND MEASUREMENT, VOL. 73, 2024

- **评分**: 5.8/10
- **分析时间**: 2026-05-13T23:33:08.093191

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

### method-001 Data Preparation and Feature Encoding [数据预处理]

该方法对采集的3218名大学生原始行为数据进行清洗、缺失值填补、标准化和特征编码，为DeepFM模型提供结构化输入。首先删除缺失率超过20%的样本，使用Z-score检测并移除离群值；然后利用miceforest多变量插补填充剩余缺失值；最后对离散特征进行one-hot编码，对连续特征进行min-max归一化，得到最终的输入特征向量。

**创新点**:
- 将miceforest算法用于学生行为数据的缺失值插补，以提高数据完整性。
- 规范化了离散-连续混合特征的预处理流程，使其适配DeepFM输入要求。

**输入**: 5000名志愿者的原始多维行为数据，包含缺失值和异常值
**输出**: 维度为 d 的标准化特征向量 X^s（由one-hot编码后的离散分量 X^s_d 和min-max归一化后的连续分量 X^s_c 拼接而成）

**步骤**:
1. 收集5000名志愿者中签署数据共享协议的学生原始行为数据。
2. 删除缺失值占比超过20%的样本，并利用Z-score移除离群值。
3. 对剩余记录的缺失值，使用miceforest算法进行多项插补填充。
4. 选取人口统计、学习成绩、体能素质、日常生活共35维特征构成数据集。
5. 对离散特征（如性别、年级类别）进行one-hot编码，生成高维稀疏向量 X^s_d。
6. 对连续特征（如成绩分数、消费金额）进行min-max归一化，得到 X^s_c。
7. 拼接编码后的离散特征和归一化后的连续特征，形成模型输入 X^s。

### method-002 DeepFM Network for Depression Detection [模型架构]

DeepFM网络由一个因子分解机（FM）组件和一个深度神经网络（DNN）组件并联组成，能够同时学习输入特征的一阶线性关系、成对二阶特征交互以及高阶非线性关系。输入混合特征先经过嵌入层降维，再分别送入FM和DNN，两者输出相加后通过sigmoid激活函数输出学生患抑郁的概率。模型使用随机梯度下降优化所有参数。

**创新点**:
- 首次将DeepFM网络应用于大学生行为数据的抑郁检测，充分利用其处理离散‑连续混合特征的能力。
- 通过并行融合FM的线性/二阶交互和DNN的高阶非线性学习，捕获行为数据中多种层次的抑郁关联模式。

**输入**: 经过数据预处理的特征向量 X^s（维度为 d，包含嵌入后的离散特征和归一化后的连续特征）
**输出**: 学生患抑郁的概率 p 以及二分类预测标签 ŷ

**步骤**:
1. 将离散特征的one-hot高维向量通过嵌入层映射为低维稠密向量。
2. 将嵌入后的离散向量与归一化后的连续向量拼接，得到特征向量 X^s。
3. 将 X^s 同时输入FM组件和DNN组件。
4. FM组件计算线性部分 w^T[1; X^s] 与二阶交叉部分 ∑∑v_i·v_j^T x_i x_j，输出 FFM。
5. DNN组件经过四层全连接（每层后接ReLU和Dropout）前向传播，输出 FDNN。
6. 将 FFM 与 FDNN 相加，经 sigmoid 函数获得抑郁概率 p = σ(FFM + FDNN)。
7. 使用SGD优化器，依据MFL损失更新模型参数 Θ = {w, V, U}。
8. 预测时，若 p > 0.5 则判定为抑郁 (ŷ=1)，否则为健康 (ŷ=0)。

**关键公式**:
$$$$F_{FM} = w^T \begin{bmatrix}1 \\ X^s \end{bmatrix} + \sum_{i=1}^{d-1} \sum_{j=i+1}^{d} \mathbf{v}_i \mathbf{v}_j^T x_i x_j$$$$
$$$$p = \sigma(F_{FM} + F_{DNN})$$$$
$$$$\hat{y} = \begin{cases} 1, & \text{if } p > 0.5 \\ 0, & \text{otherwise} \end{cases}$$$$

### method-003 Modified Focal Loss (MFL) [损失函数]

针对数据集中正常学生数量远超抑郁学生造成的严重类别不平衡，对标准Focal Loss进行了改进。MFL在原有权重衰减因子 (1−p̂)^γ 的基础上，引入一个与训练集不平衡程度 λ 和正负样本数量相关的调制函数 f(λ, S1, S0)，并进一步使用 sin(π/2·p̂) 项对损失进行缩放，使得少数类样本对应的梯度被放大，从而迫使模型在训练中给予抑郁样本更多关注，减少偏向多数类。

**创新点**:
- 将训练集的类别分布信息通过函数 f(λ, S1, S0) 显式编码到损失权重中，使损失函数能自适应调整平衡程度。
- 引入 sin(π/2·p̂) 项替代部分线性权重，在 p̂ 较小时提供更大的梯度增益，进一步强化对少数类样本的关注。
- 避免权重过大导致梯度消失或不稳定，通过分段的 f 函数限制放大倍数。

**输入**: 模型输出的预测概率 p，样本真实标签 y_s，以及训练集中抑郁学生数量 S1 与健康学生数量 S0
**输出**: 标量损失值 L，以及用于反向传播的各参数梯度

**步骤**:
1. 根据真实标签 y_s 定义样本的估计概率 p̂：若 y_s=1，则 p̂ = p；否则 p̂ = 1−p。
2. 计算不平衡指标 λ = −½·log(S1/S0)。
3. 根据 λ 是否小于等于 1，选择 f(λ, S1, S0) 的值：(S0/S1)^{1/2} 或 (S0/S1)^{1/8}。
4. 构造损失项：正类样本 (y_s=1) 的损失为 −[1−sin(π/2·p̂)]^{f}·(1−p̂)^γ·log(p̂)；负类样本 (y_s=0) 的损失为 −[1−sin(π/2·p̂)]·(1−p̂)^γ·log(p̂)。
5. 按batch累加损失得到 L，通过反向传播计算各参数梯度，使用SGD更新参数。

**关键公式**:
$$$$L = -y_s \big(1 - \sin(\frac{\pi}{2}\hat{p})\big)^{f(\lambda, S_1, S_0)} (1-\hat{p})^\gamma \log \hat{p} - (1-y_s) \big(1 - \sin(\frac{\pi}{2}\hat{p})\big) (1-\hat{p})^\gamma \log \hat{p}$$$$
$$$$\hat{p} = \begin{cases} p, & \text{if } y_s = 1 \\ 1-p, & \text{otherwise} \end{cases}$$$$
$$$$f(\lambda, S_1, S_0) = \begin{cases} (S_0 / S_1)^{1/2}, & \text{if } \lambda \le 1 \\ (S_0 / S_1)^{1/8}, & \text{otherwise} \end{cases}$$$$
$$$$\lambda = -\frac{1}{2} \log \frac{S_1}{S_0}$$$$

## 核心观点

### claim-001 [empirical]
**前提假设**: 抑郁标签（PHQ-9 ≥5）是可靠的地面真值。; 五折交叉验证的划分方式和每次实验的随机种子选择不会引入系统性偏差。; 所有模型的超参数（如学习率、dropout率、γ等）均经过公平调优。; 数据集能够代表目标学生群体，没有严重的分布漂移。
**主张**: 在五折交叉验证下，DeepFM‑MFL方法在准确率（96.4%）、敏感性（82.1%）、F1分数（81.2%）、AUC（91.9%）和G‑mean（92.3%）上均优于MLP、FNN和PNN，证明该框架对大学生抑郁检测的有效性。
> 原文: The experiment results have illustrated that DeepFM has obtained the highest average accuracy compared with MLP, FNN, and PNN... demonstrating the effectiveness of the proposed framework.

### claim-002 [design]
**前提假设**: 少数类样本在特征空间中与多数类样本是可分离的，即抑郁行为模式存在可学习的特性。; 使用MFL不会导致模型在少数类上过拟合或损失发散。; 参数γ和f函数的分段阈值适合当前数据集的不平衡程度。
**主张**: MFL通过在损失函数中引入训练集分布信息，能够使少数类样本的梯度进一步下降，从而缓解严重类别不平衡对模型训练造成的偏差。
> 原文: The MFL can compensate for less training data for the depressed group by making it descend further in the SGD process, thus reducing the bias of the model in the training phase.

### claim-003 [empirical]
**前提假设**: 各损失函数的训练超参数（学习率、批量大小等）保持一致。; 敏感性的提升确实来自损失函数的调制作用，而非随机波动或其他因素。; 基线损失函数的实现方式（如FL的γ=3）是最优或代表性配置。
**主张**: 与交叉熵损失和标准Focal Loss相比，MFL在所有四个模型（MLP、FNN、PNN、DeepFM）上均显著提高了敏感性，证明其处理不平衡问题的优越性。
> 原文: Fig. 5 shows the sensitivity values of four models with different loss functions. The figure demonstrates that the proposed loss function is superior to CE loss and FL...

### claim-004 [empirical]
**前提假设**: 数据类别划分合理，各类特征之间没有重叠或强多重共线性。; 去除一类数据后，剩余特征的信息足以维持模型分类能力的最小下降，避免由维度急剧变化引起的混淆。
**主张**: 在四类行为数据中，学术表现数据对抑郁检测最重要，其次是日常行为数据，而去除任何一种数据均会降低检测敏感性。
> 原文: As can be seen from the figure, all four types of data we collected are crucial for the detection of depression among students... The four types of data in descending order of importance are academic 

### claim-005 [empirical]
**前提假设**: FM和DNN的结构规模（如嵌入维度、隐藏层数）代表了模型在该数据上的最优或典型能力。; FM和DNN分别有效捕获了线性和非线性模式，且不存在其他混淆因素（如训练不充分）。
**主张**: FM组件在行为数据上的检测灵敏度优于DNN组件，表明线性特征交互关系比高阶非线性关系更为显著。
> 原文: In addition, FM outperforms DNN, indicating that the linear correlation between behavioral data and students’ depression is more pronounced compared with nonlinearity.

### claim-006 [empirical]
**前提假设**: 训练使用相同的初始化策略、优化器和学习率调度。; 损失曲线波动差异并非由个别实验的随机种子造成。
**主张**: MFL的收敛速度比交叉熵损失和标准Focal Loss更快，且损失曲线波动更小，说明模型训练更加稳定。
> 原文: We conjecture that the main reason is that our loss function takes into account the distribution of the training data... the proposed loss function converges faster than others.

## 局限性分析

- **[theory]** (medium) 论文提出的修改焦点损失（MFL）函数声称通过引入训练集分布信息可进一步降低少数类梯度，但未提供任何理论证明或收敛性分析，仅依赖于经验实验，其有效性缺乏理论支撑，导致该损失函数的泛用性存疑。
  > 建议: 应补充定理证明或至少提供梯度动态分析，以解释分布信息为何能提升模型对少数类的敏感度。

- **[experiment]** (high) 实验采用五折交叉验证，但是否以学生为个体进行独立划分未明确说明。行为数据若包含多个时间窗口的样本而未按学生分层，则同一学生的数据可能同时出现在训练集和测试集中，导致数据泄露和性能高估。
  > 建议: 需明确数据采样单元并进行学生级别的分组交叉验证，或提供数据划分示意图以确保独立。

- **[experiment]** (medium) 尽管样本极度不平衡（阳性率约5.6%），论文仍以准确率作为首要比较指标并报告了96.4%的高值，这可能掩盖模型对少数类识别能力不足的问题，而仅凭敏感性、F1等指标未进行阈值无关分析（如精确率-召回率曲线下面积），评估不够全面。
  > 建议: 应避免使用准确率作为主要评价标准，改用MCC、精确率-召回率AUC等适合不平衡场景的指标，并报告混淆矩阵和决策阈值的选择方法。

- **[experiment]** (medium) 对多个模型的性能比较仅报告了指标均值，未进行统计显著性检验（如t检验或Wilcoxon检验），无法确定DeepFM-MFL的改进是否具有统计意义上的可靠性。
  > 建议: 补充必要的统计检验，提供p值和置信区间，以证明结果差异并非由随机性导致。

- **[experiment]** (medium) 为了证明MFL处理不平衡问题的优越性，实验仅与标准交叉熵损失和原始Focal Loss对比，未涉及其他常见不平衡学习方法，如重采样（SMOTE、过采样）、代价敏感学习或阈值移动等，比较不充分。
  > 建议: 增加与SMOTE+交叉熵、加权交叉熵等方法的对比，以全面验证MFL的有效性。

- **[reproducibility]** (high) 论文未提供代码或数据处理细节，关键超参数（如MFL中的γ、α，网络层数、学习率等）未完整公开，读者难以复现实验结果。
  > 建议: 应公开核心代码或伪代码，并完整列出所有超参数取值及其调优范围，或提供补充材料详述实验设置。

- **[generalization]** (high) 实验数据仅源自一所中国大学的学生，学生群体的人口学特征、教育背景和行为模式较为单一，模型能否泛化到其他文化、年龄或教育体系群体未知，且样本量较小（179例阳性），易过拟合于本地模式。
  > 建议: 应收集多中心、多地区的数据集进行外部验证，或至少采用留一学校等交叉验证方式测试跨群组泛化能力。

- **[ethics]** (critical) 论文利用学生校园行为数据进行抑郁检测，但未明确说明是否获得伦理委员会批准及学生知情同意。自动采集行为数据用于心理状态推断可能严重侵犯学生隐私，若未得到充分知情同意，将违反科研伦理。
  > 建议: 必须在论文中声明通过伦理审查并获取学生明确知情同意，说明数据脱敏和存储措施，并讨论隐私保护策略（如联邦学习）的可能性。

- **[ethics]** (high) 模型可能因行为数据隐含社会经济地位、性别或专业背景等信息而产生偏见，对特定群体（如低收入、工科专业学生）的抑郁检测性能可能不同，而论文未进行任何公平性分析或偏见讨论，可能导致有害的决策偏差。
  > 建议: 应进行分组性能分析（如按性别、专业、消费水平），报告各子群指标差异，并探索减轻偏见的方法。

- **[method]** (medium) DeepFM网络本身并非新颖架构，且MFL引入额外的超参数（如调制因子γ、加权系数等），论文未分析模型对这些超参数的敏感性，在实际部署中可能因参数设置不当而性能骤降。
  > 建议: 建议进行超参数敏感性分析，展示不同γ、α取值下的性能变化，并给出参数选择指南。

## 总结
提取 3 个方法，6 条观点，发现 10 条局限性。