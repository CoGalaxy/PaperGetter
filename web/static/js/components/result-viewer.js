/** 结构化报告渲染器 — 将 AnalysisReport JSON 渲染为 HTML */

const CLAIM_TYPE_ZH = { theoretical: '理论', empirical: '实验', comparative: '对比', design: '设计' };
const LIM_CAT_ZH = { method: '方法', experiment: '实验', theory: '理论', reproducibility: '可复现性', generalization: '泛化性', ethics: '伦理' };
const SEVERITY_ZH = { critical: '严重', high: '较高', medium: '中等', low: '较低' };
const VERDICT_ZH = { supported: '支持', partially_supported: '部分支持', not_supported: '不支持', unverifiable: '无法验证', error: '出错' };
const VERDICT_COLOR = { supported: 'bg-green-100 text-green-800', partially_supported: 'bg-yellow-100 text-yellow-800', not_supported: 'bg-red-100 text-red-800', unverifiable: 'bg-gray-100 text-gray-600', error: 'bg-red-200 text-red-900' };
const SEV_COLOR = { critical: 'bg-red-100 text-red-800', high: 'bg-orange-100 text-orange-800', medium: 'bg-yellow-100 text-yellow-800', low: 'bg-gray-100 text-gray-600' };

export function renderReport(report) {
    if (!report) return '<div class="text-center py-20 text-gray-500">无报告数据</div>';

    const p = report.paper || {};
    let html = '';

    // ── Header ──
    html += renderHeader(p, report);

    // ── Abstract ──
    if (p.abstract) {
        html += renderSection('摘要', renderAbstract(p.abstract));
    }

    // ── Methodologies ──
    if (report.methodologies?.length) {
        html += renderSection('方法论', report.methodologies.map(m => renderMethodology(m)).join(''));
    }

    // ── Claims ──
    if (report.claims?.length) {
        html += renderSection('核心观点', report.claims.map((c, i) => renderClaim(c, i)).join(''));
    }

    // ── Validations ──
    if (report.validations?.length) {
        html += renderSection('验证结果', renderValidationTable(report.validations, report.claims));
    }

    // ── Limitations ──
    if (report.limitations?.length) {
        const sorted = [...report.limitations].sort((a, b) => {
            const order = { critical: 0, high: 1, medium: 2, low: 3 };
            return (order[a.severity] ?? 99) - (order[b.severity] ?? 99);
        });
        html += renderSection('局限性分析', sorted.map(l => renderLimitation(l)).join(''));
    }

    // ── Summary ──
    if (report.summary) {
        html += renderSection('总结', `<div class="prose dark:prose-invert max-w-none text-gray-700 dark:text-gray-300 leading-relaxed space-y-3">${escapeHtml(report.summary).replace(/\n\n/g, '</p><p class="mt-3">').replace(/\n/g, '<br>')}</div>`);
    }

    return html;
}

function renderHeader(p, report) {
    const yearTag = p.year ? `<span class="tag">${p.year}</span>` : '';
    const arxivTag = p.arxiv_id ? `<a href="https://arxiv.org/abs/${p.arxiv_id}" target="_blank" class="tag tag-link">arXiv:${p.arxiv_id}</a>` : '';
    const doiTag = p.doi ? `<a href="https://doi.org/${p.doi}" target="_blank" class="tag tag-link">DOI:${p.doi}</a>` : '';

    return `
    <div class="mb-8 pb-6 border-b border-gray-200 dark:border-gray-700">
        <h1 class="text-2xl font-bold text-gray-900 dark:text-white mb-3">${escapeHtml(p.title || '未命名论文')}</h1>
        <div class="flex flex-wrap gap-2 mb-2 text-sm text-gray-500 dark:text-gray-400">
            ${yearTag} ${arxivTag} ${doiTag}
        </div>
        <div class="text-xs text-gray-400 dark:text-gray-500">
            分析时间: ${report.analyzed_at ? new Date(report.analyzed_at).toLocaleString('zh-CN') : '-'}
        </div>
    </div>`;
}

function renderAbstract(text) {
    return `<p class="text-gray-600 dark:text-gray-400 leading-relaxed text-sm">${escapeHtml(text)}</p>`;
}

function renderMethodology(m) {
    const catTag = m.category ? `<span class="tag tag-blue">${escapeHtml(m.category)}</span>` : '';
    let body = '';
    if (m.overview) body += `<p class="text-gray-600 dark:text-gray-400 mb-3">${escapeHtml(m.overview)}</p>`;
    if (m.innovations?.length) {
        body += '<div class="mb-3"><span class="font-medium text-sm text-gray-700 dark:text-gray-300">创新点</span><ul class="list-disc list-inside text-sm text-gray-600 dark:text-gray-400 mt-1 space-y-0.5">';
        body += m.innovations.map(i => `<li>${escapeHtml(i)}</li>`).join('');
        body += '</ul></div>';
    }
    if (m.procedure?.length) {
        body += '<details class="mb-3"><summary class="cursor-pointer text-sm font-medium text-gray-700 dark:text-gray-300">步骤 (' + m.procedure.length + ' 步)</summary><ol class="list-decimal list-inside text-sm text-gray-600 dark:text-gray-400 mt-1 space-y-0.5">';
        body += m.procedure.map(s => `<li>${escapeHtml(s)}</li>`).join('');
        body += '</ol></details>';
    }
    if (m.key_formulas?.length) {
        body += '<div class="mb-3"><span class="font-medium text-sm text-gray-700 dark:text-gray-300">关键公式</span>';
        body += m.key_formulas.map(f => `<pre class="bg-gray-50 dark:bg-gray-800 rounded p-2 mt-1 text-sm font-mono overflow-x-auto">$${escapeHtml(f)}$</pre>`).join('');
        body += '</div>';
    }
    if (m.inputs) body += `<div class="text-sm text-gray-500 dark:text-gray-400 mb-1"><span class="font-medium">输入:</span> ${escapeHtml(m.inputs)}</div>`;
    if (m.outputs) body += `<div class="text-sm text-gray-500 dark:text-gray-400 mb-2"><span class="font-medium">输出:</span> ${escapeHtml(m.outputs)}</div>`;

    return `
    <div class="card mb-3" x-data="{ open: false }">
        <div class="flex items-center justify-between cursor-pointer" @click="open=!open">
            <div class="flex items-center gap-2">
                <span class="text-xs text-blue-500 font-mono">${escapeHtml(m.id)}</span>
                <span class="font-semibold text-gray-800 dark:text-gray-200">${escapeHtml(m.name)}</span>
                ${catTag}
            </div>
            <span class="text-gray-400 text-sm" x-text="open ? '▾' : '▸'"></span>
        </div>
        <div x-show="open" class="mt-3">${body}</div>
    </div>`;
}

function renderClaim(c, i) {
    const typeZh = CLAIM_TYPE_ZH[c.type] || c.type;
    const refs = c.related_method_ids?.length ? c.related_method_ids.map(r => `<span class="tag tag-blue">${escapeHtml(r)}</span>`).join('') : '';

    const fields = [
        ['问题', c.problem],
        ['方法', c.method_applied],
        ['机制', c.mechanism],
        ['结果', c.result],
        ['前提', c.condition],
    ];
    let fieldHtml = fields.filter(([, v]) => v).map(([label, value]) =>
        `<div class="mb-1.5"><span class="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">${label}</span><p class="text-sm text-gray-700 dark:text-gray-300 mt-0.5">${escapeHtml(value)}</p></div>`
    ).join('');

    if (c.assumptions?.length) {
        fieldHtml += `<div class="mb-1.5"><span class="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">隐含假设</span><p class="text-sm text-gray-600 dark:text-gray-400 mt-0.5">${c.assumptions.map(a => escapeHtml(a)).join('; ')}</p></div>`;
    }
    if (c.context) {
        fieldHtml += `<blockquote class="border-l-2 border-gray-300 dark:border-gray-600 pl-3 my-2 text-xs text-gray-400 dark:text-gray-500 italic">${escapeHtml(c.context.slice(0, 200))}</blockquote>`;
    }

    const confPct = Math.round((c.confidence || 0) * 100);
    const confColor = confPct >= 80 ? 'text-green-600' : confPct >= 60 ? 'text-yellow-600' : 'text-red-600';

    return `
    <div class="card mb-3" x-data="{ open: ${i === 0 ? 'true' : 'false'} }">
        <div class="flex items-center justify-between cursor-pointer" @click="open=!open">
            <div class="flex-1 min-w-0">
                <div class="flex items-center gap-2 flex-wrap">
                    <span class="text-xs text-blue-500 font-mono">${escapeHtml(c.id)}</span>
                    <span class="tag tag-purple">${typeZh}</span>
                    ${refs}
                    <span class="text-xs ${confColor} font-medium ml-auto">${confPct}%</span>
                </div>
                ${c.summary ? `<p class="text-sm text-gray-800 dark:text-gray-200 mt-1 font-medium">${escapeHtml(c.summary)}</p>` : ''}
            </div>
            <span class="text-gray-400 text-sm ml-2" x-text="open ? '▾' : '▸'"></span>
        </div>
        <div x-show="open" class="mt-3 pt-3 border-t border-gray-100 dark:border-gray-700">
            ${fieldHtml}
        </div>
    </div>`;
}

function renderValidationTable(validations, claims) {
    const claimMap = {};
    if (claims) claims.forEach(c => { claimMap[c.id] = c; });

    let rows = validations.map(v => {
        const claim = claimMap[v.claim_id];
        const summary = claim?.summary || (claim?.statement || '').slice(0, 80);
        const verdictZh = VERDICT_ZH[v.verdict] || v.verdict;
        const verdictCls = VERDICT_COLOR[v.verdict] || 'bg-gray-100 text-gray-600';

        let expandable = '';
        if (v.generated_code) {
            expandable += `<details class="mt-2"><summary class="cursor-pointer text-xs text-blue-500 hover:text-blue-700">查看验证代码</summary><pre class="bg-gray-900 text-green-400 rounded p-3 mt-1 text-xs overflow-x-auto font-mono">${escapeHtml(v.generated_code)}</pre></details>`;
        }
        if (v.execution_output) {
            expandable += `<details class="mt-1"><summary class="cursor-pointer text-xs text-blue-500 hover:text-blue-700">查看执行输出</summary><pre class="bg-gray-900 text-gray-300 rounded p-3 mt-1 text-xs overflow-x-auto font-mono max-h-40 overflow-y-auto">${escapeHtml(v.execution_output)}</pre></details>`;
        }

        return `
        <div class="border-b border-gray-100 dark:border-gray-700 pb-3 mb-3 last:border-0">
            <div class="flex items-center gap-2 flex-wrap mb-1">
                <span class="text-xs font-mono text-blue-500">${escapeHtml(v.claim_id)}</span>
                <span class="tag text-xs ${verdictCls}">${verdictZh}</span>
            </div>
            <p class="text-sm text-gray-700 dark:text-gray-300">${escapeHtml(summary)}</p>
            ${v.evidence ? `<p class="text-xs text-gray-500 dark:text-gray-400 mt-1">${escapeHtml(v.evidence.slice(0, 300))}</p>` : ''}
            ${expandable}
        </div>`;
    }).join('');

    return rows;
}

function renderLimitation(l) {
    const catZh = LIM_CAT_ZH[l.category] || l.category;
    const sevZh = SEVERITY_ZH[l.severity] || l.severity;
    const sevCls = SEV_COLOR[l.severity] || 'bg-gray-100 text-gray-600';

    return `
    <div class="card mb-3 border-l-3 ${l.severity === 'critical' ? 'border-red-400' : l.severity === 'high' ? 'border-orange-400' : 'border-gray-300'}">
        <div class="flex items-center gap-2 mb-2 flex-wrap">
            <span class="tag ${sevCls}">${sevZh}</span>
            <span class="tag bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300">${catZh}</span>
        </div>
        <p class="text-sm text-gray-700 dark:text-gray-300 leading-relaxed">${escapeHtml(l.description)}</p>
        ${l.suggested_fix ? `<p class="mt-2 text-xs text-gray-500 dark:text-gray-400"><span class="font-medium">建议:</span> ${escapeHtml(l.suggested_fix)}</p>` : ''}
    </div>`;
}

function renderSection(title, content) {
    return `
    <div class="mb-8">
        <h2 class="text-lg font-bold text-gray-900 dark:text-white mb-4 pb-2 border-b border-gray-200 dark:border-gray-700">${title}</h2>
        ${content}
    </div>`;
}

function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}
