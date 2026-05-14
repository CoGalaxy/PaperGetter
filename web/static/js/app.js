/** 主应用 — Alpine.js 根组件 + 路由 + 任务流程 */

import { createJob, listJobs, getReportJSON, getReportMDUrl, cancelJob, getStreamUrl } from './api.js';
import { SSEClient } from './utils/sse-client.js';
import { initUploadZone } from './components/upload-zone.js';
import { initProgressPanel } from './components/progress-panel.js';
import { renderReport } from './components/result-viewer.js';
import { initSettingsForm } from './components/settings-form.js';

document.addEventListener('alpine:init', () => {
    Alpine.data('app', function () {
        return {
            // ── 全局状态 ──
            page: 'home',           // home | settings | results
            dark: false,

            // Upload
            upload: initUploadZone(),

            // Progress
            progress: initProgressPanel(),
            jobId: null,
            sse: null,

            // Results
            currentReport: null,
            reportHTML: '',
            loadingReport: false,

            // Settings
            settings: initSettingsForm(),

            // Job history
            jobHistory: [],

            // Toast
            toast: { show: false, message: '', type: 'success' },

            // ── 初始化 ──
            init() {
                this.dark = localStorage.getItem('theme') === 'dark'
                    || (!localStorage.getItem('theme') && window.matchMedia('(prefers-color-scheme: dark)').matches);
                this.applyTheme();
                this.loadJobHistory();
                window.addEventListener('hashchange', () => this.route());
                this.route();
            },

            // ── 主题 ──
            toggleTheme() {
                this.dark = !this.dark;
                localStorage.setItem('theme', this.dark ? 'dark' : 'light');
                this.applyTheme();
            },
            applyTheme() {
                document.documentElement.classList.toggle('dark', this.dark);
            },

            // ── 路由 ──
            route() {
                const hash = window.location.hash.slice(1) || 'home';
                if (hash.startsWith('results/')) {
                    this.page = 'results';
                    this.loadReport(hash.replace('results/', ''));
                } else if (hash === 'settings') {
                    this.page = 'settings';
                    this.settings.load();
                } else {
                    this.page = 'home';
                }
            },
            navigate(page) {
                window.location.hash = page;
            },

            // ── 任务流程 ──
            async startAnalysis() {
                if (!this.upload.file) return;
                this.upload.uploading = true;
                try {
                    const { job_id } = await createJob(this.upload.file);
                    this.jobId = job_id;
                    this.progress.reset();
                    this.progress.startTimer();

                    // 连接 SSE
                    this.sse = new SSEClient(getStreamUrl(job_id), {
                        progress: (data) => { this.progress.handleEvent(data); },
                        llm_chunk: (data) => { this.progress.handleLLMChunk(data); },
                        job_done: async () => {
                            this.progress.stopTimer();
                            this.progress.percentage = 100;
                            this.showToast('分析完成', 'success');
                            this.loadJobHistory();
                            await this.loadReport(job_id);
                            this.navigate('results/' + job_id);
                        },
                        job_error: (data) => {
                            this.progress.stopTimer();
                            this.showToast('分析失败: ' + (data.error || '未知错误'), 'error');
                            this.loadJobHistory();
                        },
                    });
                    this.sse.connect();
                } catch (e) {
                    this.showToast('启动失败: ' + e.message, 'error');
                }
                this.upload.uploading = false;
            },

            cancelCurrentJob() {
                if (this.jobId) {
                    cancelJob(this.jobId);
                    this.sse?.close();
                    this.progress.stopTimer();
                    this.showToast('已取消', 'info');
                }
            },

            // ── 报告 ──
            async loadReport(jobId) {
                this.loadingReport = true;
                try {
                    this.currentReport = await getReportJSON(jobId);
                    this.reportHTML = renderReport(this.currentReport);
                } catch (e) {
                    this.reportHTML = `<div class="text-center py-10 text-red-500">加载失败: ${e.message}</div>`;
                }
                this.loadingReport = false;
            },

            downloadMarkdown(jobId) {
                window.open(getReportMDUrl(jobId), '_blank');
            },

            // ── 历史 ──
            async loadJobHistory() {
                try {
                    this.jobHistory = await listJobs();
                } catch (e) { /* ignore */ }
            },

            // ── Toast ──
            showToast(msg, type) {
                this.toast = { show: true, message: msg, type };
                setTimeout(() => { this.toast.show = false; }, 3000);
            },
        };
    });
});
