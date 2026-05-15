export default function UploadPanel({
  sources,
  onUpload,
  onIngestUrl,
  isUploading,
}) {
  const handleFileChange = (event) => {
    const [file] = event.target.files;
    if (file) {
      onUpload(file);
      event.target.value = '';
    }
  };

  const handleUrlSubmit = (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const url = form.elements.url?.value || '';
    if (url.trim()) {
      onIngestUrl(url.trim());
      form.reset();
    }
  };

  return (
    <section className="panel">
      <h3>My Sources</h3>
      <div className="upload-controls">
        <label className="ghost">
          {isUploading ? 'Uploading...' : 'Upload PDF/DOCX'}
          <input
            type="file"
            accept="application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            onChange={handleFileChange}
            disabled={isUploading}
            hidden
          />
        </label>
        <form className="url-form" onSubmit={handleUrlSubmit}>
          <input className="text-input" name="url" placeholder="https://example.com" />
          <button className="primary" type="submit" disabled={isUploading}>
            Ingest
          </button>
        </form>
      </div>
      <div className="source-list">
        {sources.length === 0 ? (
          <div className="empty">No sources ingested yet.</div>
        ) : (
          sources.map((item) => (
            <div className="source-item" key={item.id}>
              <span className={`badge ${item.type}`}>{item.type.toUpperCase()}</span>
              <div>
                <div className="source-title">{item.title}</div>
                <div className="source-meta">{item.meta}</div>
              </div>
              <span className="status-dot" />
            </div>
          ))
        )}
      </div>
    </section>
  );
}
