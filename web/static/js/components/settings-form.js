/** 配置编辑表单 */

import { getConfig, updateConfig, getModels } from '../api.js';

export function initSettingsForm() {
    return {
        config: null,
        models: [],
        loading: true,
        saving: false,
        toast: { show: false, message: '', type: 'success' },

        async load() {
            this.loading = true;
            try {
                const [cfg, mod] = await Promise.all([getConfig(), getModels()]);
                this.config = cfg;
                this.models = mod.models || [];
            } catch (e) {
                this.showToast('加载配置失败: ' + e.message, 'error');
            }
            this.loading = false;
        },

        async save() {
            this.saving = true;
            try {
                await updateConfig(this.config);
                this.showToast('配置已保存', 'success');
            } catch (e) {
                this.showToast('保存失败: ' + e.message, 'error');
            }
            this.saving = false;
        },

        showToast(msg, type) {
            this.toast = { show: true, message: msg, type };
            setTimeout(() => { this.toast.show = false; }, 3000);
        },

        modelRoles: [
            { key: 'extraction', label: '方法论与观点提取', desc: '两阶段提取 (方法骨架 + 因果链主张)' },
            { key: 'code_generation', label: '验证代码生成', desc: '为每一条 claim 生成 toy validation script' },
            { key: 'parsing', label: 'PDF 解析', desc: '章节标题识别 (LLM 辅助)' },
            { key: 'comparison', label: '验证结果对照', desc: '对比执行输出与原始主张' },
            { key: 'limitation', label: '局限性分析', desc: '六维度局限性审查' },
            { key: 'summarization', label: '论文总结', desc: '逐 claim 摘要 + 整体总结' },
        ],

        // 输入框辅助方法
        getLlamaModels(key) { return this.config?.llm?.models || {}; },
        getLlamaDefaults(key) { return this.config?.llm?.defaults || {}; },
    };
}
