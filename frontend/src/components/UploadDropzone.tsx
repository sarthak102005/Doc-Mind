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
    <div style={{ marginBottom: '2.5rem' }}>
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
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '0.75rem' }}>
          <div
            style={{
              padding: '1rem',
              borderRadius: '50%',
              background: 'rgba(99, 102, 241, 0.1)',
              color: '#818cf8',
            }}
          >
            {uploading ? <span className="spinner" style={{ width: '24px', height: '24px' }} /> : <UploadCloudIcon size={32} />}
          </div>

          <div>
            <h3 style={{ fontSize: '1.1rem', fontWeight: 600, marginBottom: '0.25rem' }}>
              {uploading ? 'Validating and uploading document...' : 'Click or drag PDF document to upload'}
            </h3>
            <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
              Standard and scanned PDFs up to 50 MB (Password protected files not permitted)
            </p>
          </div>
        </div>
      </div>

      {error && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
            padding: '0.75rem 1rem',
            borderRadius: '8px',
            background: 'rgba(244, 63, 94, 0.1)',
            border: '1px solid rgba(244, 63, 94, 0.25)',
            color: '#fda4af',
            fontSize: '0.85rem',
            marginTop: '1rem',
          }}
        >
          <AlertCircleIcon size={16} />
          <span>{error}</span>
        </div>
      )}
    </div>
  );
};
