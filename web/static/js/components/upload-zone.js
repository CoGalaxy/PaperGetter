/** 拖拽上传组件 */

export function initUploadZone() {
    return {
        file: null,
        dragging: false,
        uploading: false,
        error: '',

        handleDrop(e) {
            this.dragging = false;
            const f = e.dataTransfer.files[0];
            if (f && f.name.toLowerCase().endsWith('.pdf')) {
                this.file = f;
                this.error = '';
            } else {
                this.error = '只支持 PDF 文件';
            }
        },

        handleFileInput(e) {
            const f = e.target.files[0];
            if (f) {
                this.file = f;
                this.error = '';
            }
        },

        removeFile() {
            this.file = null;
        },

        formatSize(bytes) {
            if (!bytes) return '';
            if (bytes < 1024) return bytes + ' B';
            if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
            return (bytes / 1024 / 1024).toFixed(2) + ' MB';
        }
    };
}
