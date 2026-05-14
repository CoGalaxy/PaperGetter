/** API 封装 — fetch 包装器 */

const BASE = '';

export async function uploadFile(file) {
    const form = new FormData();
    form.append('file', file);
    const res = await fetch(`${BASE}/api/upload`, { method: 'POST', body: form });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function createJob(file) {
    const form = new FormData();
    form.append('file', file);
    const res = await fetch(`${BASE}/api/jobs`, { method: 'POST', body: form });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function listJobs() {
    const res = await fetch(`${BASE}/api/jobs`);
    return res.json();
}

export async function getJob(jobId) {
    const res = await fetch(`${BASE}/api/jobs/${jobId}`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function cancelJob(jobId) {
    const res = await fetch(`${BASE}/api/jobs/${jobId}/cancel`, { method: 'POST' });
    return res.json();
}

export async function deleteJob(jobId) {
    const res = await fetch(`${BASE}/api/jobs/${jobId}`, { method: 'DELETE' });
    return res.json();
}

export async function getReportJSON(jobId) {
    const res = await fetch(`${BASE}/api/reports/${jobId}/json`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export function getReportMDUrl(jobId) {
    return `${BASE}/api/reports/${jobId}/markdown`;
}

export function getStreamUrl(jobId) {
    return `${BASE}/api/jobs/${jobId}/stream`;
}

export async function getConfig() {
    const res = await fetch(`${BASE}/api/config`);
    return res.json();
}

export async function updateConfig(data) {
    const res = await fetch(`${BASE}/api/config`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export async function getModels() {
    const res = await fetch(`${BASE}/api/models`);
    return res.json();
}
