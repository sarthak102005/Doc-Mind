import React, { useState, useRef } from 'react';
import { uploadDocument, DocumentItem } from '../api';
import { AlertCircleIcon, UploadCloudIcon } from './icons';

interface UploadDropzoneProps {
  onUploadSuccess: (doc: DocumentItem) => void;
}

export const UploadDropzone: React.FC<UploadDropzoneProps> = ({ onUploadSuccess }) => {
  const [isDragging, setIsDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFile = async (file: File) => {
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      setError('Please upload a PDF document (.pdf).');
      return;
    }

    if (file.size > 50 * 1024 * 1024) {
      setError('File exceeds maximum upload size of 50 MB.');
      return;
    }

    setError(null);
    setUploading(true);

    try {
      const doc = await uploadDocument(file);
      onUploadSuccess(doc);
    } catch (err: any) {
      setError(err.message || 'Upload failed');
    } finally {
      setUploading(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  const onDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const onDragLeave = () => {
    setIsDragging(false);
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFile(e.dataTransfer.files[0]);
    }
  };

  return (
    <div style={{ marginBottom: '2rem' }}>
      <input
        type="file"
        ref={fileInputRef}
        accept="application/pdf"
        style={{ display: 'none' }}
        onChange={(e) => {
          if (e.target.files && e.target.files.length > 0) {
            handleFile(e.target.files[0]);
          }
        }}
      />

      <div
        className={`dropzone ${isDragging ? 'active' : ''}`}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
        onClick={() => !uploading && fileInputRef.current?.click()}
      >
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '0.85rem' }}>
          <div
            style={{
              width: '54px',
              height: '54px',
              borderRadius: '50%',
              background: isDragging ? 'var(--accent-teal-subtle)' : 'var(--bg-secondary)',
              border: '1px solid var(--border-subtle)',
              color: isDragging ? 'var(--accent-teal)' : 'var(--brand-muted-blue)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              transition: 'all 0.2s ease',
            }}
          >
            {uploading ? (
              <span className="spinner" style={{ width: '22px', height: '22px' }} />
            ) : (
              <UploadCloudIcon size={26} />
            )}
          </div>

          <div>
            <h3 style={{ fontSize: '1.05rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.3rem' }}>
              {uploading ? 'Ingesting and validating document...' : 'Click to upload or drag and drop PDF'}
            </h3>
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', lineHeight: 1.5 }}>
              Standard and scanned technical manuals, specs, or reports (up to 50 MB)
            </p>
          </div>

          <div
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.4rem',
              padding: '0.2rem 0.6rem',
              background: 'var(--bg-card-subtle)',
              borderRadius: '4px',
              border: '1px solid var(--border-subtle)',
              fontSize: '0.75rem',
              color: 'var(--text-muted)',
            }}
          >
            <span>Password-protected files must be decrypted prior to upload</span>
          </div>
        </div>
      </div>

      {error && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.6rem',
            padding: '0.75rem 1rem',
            borderRadius: 'var(--radius-sm)',
            background: 'var(--status-error-bg)',
            border: '1px solid var(--status-error-border)',
            color: 'var(--status-error)',
            fontSize: '0.85rem',
            marginTop: '0.85rem',
          }}
        >
          <AlertCircleIcon size={16} />
          <span>{error}</span>
        </div>
      )}
    </div>
  );
};
