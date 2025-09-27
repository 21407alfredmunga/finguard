# Invoice PDF Storage Directory

This directory stores generated invoice PDF files.

## Structure
- Invoice PDFs are automatically saved here with unique filenames
- Format: `invoice_{invoice_number}_{timestamp}.pdf`
- Files are served via FastAPI static file serving at `/storage/invoices/`

## Production Notes
In production environments, consider:
- Using cloud storage (AWS S3, Google Cloud Storage)
- Implementing signed URLs for security
- Setting up CDN for faster delivery
- Configuring proper backup strategies

## Development
- PDFs are stored locally for development
- Access via: `http://localhost:8000/storage/invoices/{filename}`