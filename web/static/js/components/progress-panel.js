/** 实时进度面板 — SSE 事件消费 */

const PHASE_LABELS = {
    parse: '解析 PDF',
    extract: '提取方法论与观点',
    validate: '验证观点',
    analyze: '局限性分析',
    summarize: '生成总结',
    report: '导出报告',
};

const STEP_ICONS = {
    start: '○', step: '◉', sub: '·', done: '✓', skip: '—', error: '✗',
};

const PHASE_ORDER = ['parse', 'extract', 'validate', 'analyze', 'summarize', 'report'];

export function initProgressPanel() {
    return {
        phases: PHASE_ORDER.map(p => ({ key: p, label: PHASE_LABELS[p] || p, status: 'pending', detail: '', subs: [] })),
        percentage: 0,
        elapsed: 0,
        elapsedTimer: null,
        llmOutput: '',
        llmVisible: false,
        phaseStatus: {},

        reset() {
            this.phases = PHASE_ORDER.map(p => ({ key: p, label: PHASE_LABELS[p] || p, status: 'pending', detail: '', subs: [] }));
            this.percentage = 0;
            this.elapsed = 0;
            this.llmOutput = '';
            this.llmVisible = false;
            this.phaseStatus = {};
            if (this.elapsedTimer) clearInterval(this.elapsedTimer);
        },

        startTimer() {
            const start = Date.now();
            this.elapsedTimer = setInterval(() => {
                this.elapsed = Math.floor((Date.now() - start) / 1000);
            }, 1000);
        },

        stopTimer() {
            if (this.elapsedTimer) {
                clearInterval(this.elapsedTimer);
                this.elapsedTimer = null;
            }
        },

        handleEvent(evt) {
            const { phase, step, detail, elapsed, pct } = evt;
            if (!phase) return;

            const ph = this.phases.find(p => p.key === phase);
            if (!ph) return;

            // 更新阶段状态
            if (step === 'start') {
                ph.status = 'running';
            } else if (step === 'done') {
                ph.status = 'passed';
                ph.detail = detail;
            } else if (step === 'error') {
                ph.status = 'error';
                ph.detail = detail;
            } else if (step === 'skip') {
                ph.status = 'skipped';
                ph.detail = detail;
            } else if (step === 'step') {
                ph.status = 'running';
                ph.detail = detail;
            } else if (step === 'sub') {
                ph.subs.unshift(detail);
                if (ph.subs.length > 20) ph.subs.pop();
            }

            if (pct !== undefined) this.percentage = pct;
            this.elapsed = Math.floor(elapsed || 0);
        },

        handleLLMChunk(data) {
            if (data.text) {
                this.llmOutput += data.text;
                this.llmVisible = true;
            }
        },

        formatTime(secs) {
            const m = Math.floor(secs / 60);
            const s = secs % 60;
            return m > 0 ? `${m}m ${s.toString().padStart(2, '0')}s` : `${s}s`;
        },

        phaseIconClass(ph) {
            if (ph.status === 'running') return 'text-yellow-500';
            if (ph.status === 'passed') return 'text-green-500';
            if (ph.status === 'error') return 'text-red-500';
            if (ph.status === 'skipped') return 'text-gray-400';
            return 'text-gray-600 dark:text-gray-500';
        }
    };
}
