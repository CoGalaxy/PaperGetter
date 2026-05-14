/** SSE 客户端 — EventSource 封装，支持自动重连 */

export class SSEClient {
    constructor(url, handlers) {
        this.url = url;
        this.handlers = handlers; // { progress, llm_chunk, job_done, job_error, ping }
        this.es = null;
        this.reconnectDelay = 1000;
        this.maxReconnectDelay = 10000;
        this._closed = false;
    }

    connect() {
        this._closed = false;
        this._connect();
    }

    _connect() {
        if (this._closed) return;
        this.es = new EventSource(this.url);

        this.es.addEventListener('progress', e => {
            const data = JSON.parse(e.data);
            this.handlers.progress?.(data);
        });

        this.es.addEventListener('llm_chunk', e => {
            const data = JSON.parse(e.data);
            this.handlers.llm_chunk?.(data);
        });

        this.es.addEventListener('job_done', e => {
            const data = JSON.parse(e.data);
            this.handlers.job_done?.(data);
            this.close();
        });

        this.es.addEventListener('job_error', e => {
            const data = JSON.parse(e.data);
            this.handlers.job_error?.(data);
            this.close();
        });

        this.es.addEventListener('ping', () => {});

        this.es.onerror = () => {
            this.es?.close();
            if (!this._closed) {
                setTimeout(() => this._connect(), this.reconnectDelay);
                this.reconnectDelay = Math.min(this.reconnectDelay * 2, this.maxReconnectDelay);
            }
        };
    }

    close() {
        this._closed = true;
        this.es?.close();
        this.es = null;
    }
}
