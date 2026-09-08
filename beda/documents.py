"""Editable, revisioned working copies of the three supplied attachments."""
import hashlib
from pathlib import Path
from beda.models import utc_now_iso

CATALOG = (
    ('01_hume_energy_bill.txt', 'Hume energy bill', 'E001', 'July 2026 · Truganina distribution centre'),
    ('02_northbank_site_notes.txt', 'Northbank site notes', 'E005', 'Lighting inventory and missing information'),
    ('03_greenfields_invoice_query.txt', 'Greenfields invoice query', 'E003', 'Purchase order and invoice comparison'),
)
SOURCE = Path(__file__).resolve().parent.parent / 'data' / 'documents'


class Documents:
    def __init__(self, db):
        self.db = db
        with db._connection() as conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS document_revisions (
                filename TEXT NOT NULL, revision INTEGER NOT NULL, content TEXT NOT NULL,
                note TEXT NOT NULL, actor TEXT NOT NULL, created_at TEXT NOT NULL,
                sha256 TEXT NOT NULL, PRIMARY KEY(filename,revision))''')
            for filename, _, _, _ in CATALOG:
                if conn.execute('SELECT 1 FROM document_revisions WHERE filename=?',(filename,)).fetchone():
                    continue
                text=(SOURCE/filename).read_text(encoding='utf-8')
                conn.execute('INSERT INTO document_revisions VALUES(?,?,?,?,?,?,?)',
                    (filename,1,text,'Imported supplied original','system',utc_now_iso(),hashlib.sha256(text.encode()).hexdigest()))

    def list(self):
        result=[]
        with self.db._connection() as conn:
            for filename,title,enquiry,description in CATALOG:
                revisions=[dict(row) for row in conn.execute(
                    'SELECT * FROM document_revisions WHERE filename=? ORDER BY revision DESC',(filename,))]
                result.append({'filename':filename,'title':title,'enquiry_id':enquiry,'description':description,
                    'current':revisions[0],'revisions':revisions})
        return result

    def get(self,filename):
        return next((d for d in self.list() if d['filename']==filename),None)

    def save(self,filename,content,note,expected_revision):
        if filename not in {row[0] for row in CATALOG}:
            raise ValueError('Unknown document')
        if not isinstance(content,str) or not content.strip() or len(content.encode())>40000:
            raise ValueError('Document must contain text and be no larger than 40 KB')
        if not isinstance(note,str) or not note.strip() or len(note)>500:
            raise ValueError('Add a short change note (1–500 characters)')
        if type(expected_revision) is not int:
            raise ValueError('A base revision is required')
        with self.db._connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            previous=conn.execute('SELECT revision,content FROM document_revisions WHERE filename=? ORDER BY revision DESC LIMIT 1',(filename,)).fetchone()
            if previous['revision']!=expected_revision:
                raise ValueError('This document changed in another tab. Reload it before saving.')
            if previous['content']==content:
                raise ValueError('No changes to save')
            conn.execute('INSERT INTO document_revisions VALUES(?,?,?,?,?,?,?)',
                (filename,expected_revision+1,content,note.strip(),'local_reviewer',utc_now_iso(),hashlib.sha256(content.encode()).hexdigest()))
        return self.get(filename)

    def attach(self,payload):
        """Attach a snapshot, not a mutable reference, to a new full run."""
        document=self.get(payload.get('attachment_filename') or payload.get('attachment'))
        if document:
            payload={**payload,'attachment_filename':document['filename'],
                'attachment_content':document['current']['content'],
                'attachment_revision':document['current']['revision'],
                'attachment_sha256':document['current']['sha256']}
        return payload
