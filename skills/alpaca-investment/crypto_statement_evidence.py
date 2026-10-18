"""Read captured native statement rows without assigning fees or proving account scope."""
from datetime import date, datetime
from decimal import Decimal
from email.utils import parsedate_to_datetime
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import stat
import subprocess
import tempfile
from uuid import UUID

from crypto_ownership_proof import _digest

MAX_PDF_BYTES = 8 * 1024 * 1024
MAX_TEXT_BYTES = 2 * 1024 * 1024
INVALID = 'crypto_statement_input_invalid'
CONFLICT = 'crypto_statement_evidence_conflict'
_ID = r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}'
_ROW = re.compile(r'^\s*(\d{2}/\d{2}/\d{4})\s+(' + _ID + r')\s+([A-Z][A-Z0-9/]{1,15})'
    r'\s+([+-]?\d{1,24}(?:\.\d{1,24})?)\s+(\$\s+(?:--|[+-]?\d[\d,]*(?:\.\d{1,8})?))\s*$')


def _private_directory(path, *, dir_fd=None):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=dir_fd)
    try:
        info = os.fstat(descriptor)
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise ValueError(INVALID)
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def _private_bytes(name, directory, limit):
    descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    try:
        info = os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1
                or stat.S_IMODE(info.st_mode) != 0o600 or not 0 < info.st_size <= limit):
            raise ValueError(INVALID)
        with os.fdopen(descriptor, 'rb') as handle:
            descriptor = -1
            raw = handle.read(limit + 1)
            after = os.fstat(handle.fileno())
        if len(raw) != info.st_size or (info.st_size, info.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError(INVALID)
        return raw
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _metadata(raw, digest, mode):
    if hashlib.sha256(raw.encode()).hexdigest() != digest:
        raise ValueError(INVALID)
    metadata = json.loads(raw)
    if (not isinstance(metadata, dict) or metadata.get('source_host') != 'app.alpaca.markets'
            or metadata.get('measurement_mode') != mode or metadata.get('account_binding_verified') is not True):
        raise ValueError(INVALID)
    account = metadata['native_trading_account_id']
    if not isinstance(account, str) or str(UUID(account)) != account:
        raise ValueError(INVALID)
    # UI account IDs and Trading account IDs occupy different namespaces.
    path = metadata['source_path']
    if not isinstance(path, str) or not re.fullmatch(r'/api/v1/accounts/[a-f0-9-]{36}/documents', path):
        raise ValueError(INVALID)
    UUID(path.split('/')[4])
    for field in ('native_account_get_request_id', 'documents_request_id'):
        value = metadata[field]
        if not isinstance(value, str) or not 0 < len(value) <= 256 or not value.isascii() or not value.isprintable():
            raise ValueError(INVALID)
    captured_at = parsedate_to_datetime(metadata['native_account_get_date'])
    if captured_at.tzinfo is None:
        raise ValueError(INVALID)
    rows = metadata['rows']
    if not isinstance(rows, list) or not 0 < len(rows) <= 100:
        raise ValueError(INVALID)
    documents = {}
    for row in rows:
        if not isinstance(row, dict) or not re.fullmatch(_ID, row.get('id', '')) or row['id'] in documents:
            raise ValueError(INVALID)
        if not isinstance(row.get('type'), str) or not row['type']:
            raise ValueError(INVALID)
        if date.fromisoformat(row['date']).isoformat() != row['date']:
            raise ValueError(INVALID)
        documents[row['id']] = row
    return metadata, documents


def _output_limit():
    resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_TEXT_BYTES, MAX_TEXT_BYTES))


def _extract_pdf(pdf):
    if not pdf.startswith(b'%PDF-'):
        raise ValueError(INVALID)
    try:
        with tempfile.TemporaryFile() as output:
            subprocess.run(['pdftotext', '-layout', '-enc', 'UTF-8', '-', '-'], input=pdf,
                stdout=output, stderr=subprocess.DEVNULL, timeout=10, check=True, preexec_fn=_output_limit)
            output.seek(0)
            raw = output.read(MAX_TEXT_BYTES + 1)
        if not raw or len(raw) > MAX_TEXT_BYTES:
            raise ValueError(INVALID)
        return raw.decode('utf-8')
    except FileNotFoundError:
        raise ValueError('crypto_statement_tool_unavailable') from None
    except (subprocess.SubprocessError, OSError):
        raise ValueError('crypto_statement_extraction_failed') from None


def _fee_lines(text):
    lines = text.split('\n')
    result = []
    start = next((i for i, line in enumerate(lines) if line.strip() == 'Fees'), None)
    if start is None:
        raise ValueError(INVALID)
    cursor = start + 1
    need_header = True
    while cursor < len(lines):
        content = lines[cursor].strip()
        header = bool(re.fullmatch(r'Trade Date\s+Order ID\s+Symbol\s+Qty\s+Net Amt', content))
        if not content:
            cursor += 1
            continue
        if need_header:
            if not header:
                raise ValueError(INVALID)
            need_header = False
        elif content == 'Transaction':
            break
        elif content == 'Fees':
            need_header = True
        elif header:
            pass
        elif _ROW.fullmatch(lines[cursor]):
            result.append({'source_line_number': cursor + 1, 'raw_line': lines[cursor]})
        elif content.isdecimal():
            following = cursor + 1
            while following < len(lines) and not lines[following].strip():
                following += 1
            # Only a page number immediately preceding a form feed is furniture.
            if not any('\f' in line for line in lines[cursor + 1:following + 1]):
                raise ValueError(INVALID)
        else:
            raise ValueError(INVALID)
        cursor += 1
    if need_header or len(result) > 10000:
        raise ValueError(INVALID)
    return result


def _document(metadata_text, metadata_sha256, document_id, pdf_sha256, text_sha256, fee_lines, mode):
    metadata, documents = _metadata(metadata_text, metadata_sha256, mode)
    native = documents[document_id]
    if native['type'] != 'crypto_account_statement':
        raise ValueError(INVALID)
    if (not re.fullmatch(r'[a-f0-9]{64}', pdf_sha256) or not re.fullmatch(r'[a-f0-9]{64}', text_sha256)
            or not isinstance(fee_lines, list) or len(fee_lines) > 10000):
        raise ValueError(INVALID)
    document = {'metadata_text': metadata_text, 'metadata_sha256': metadata_sha256,
        'document_id': document_id, 'document_type': native['type'], 'document_date': native['date'],
        'pdf_sha256': pdf_sha256, 'text_sha256': text_sha256, 'fee_lines': fee_lines,
        'source_host': metadata['source_host'], 'source_path': metadata['source_path'], 'mode': mode,
        'capture_trading_account_id': metadata['native_trading_account_id'],
        'capture_mapping_status': 'metadata_filename_only', 'current_account_scope_status': 'unknown'}
    observations = []
    last_line = 0
    for line in fee_lines:
        number = line['source_line_number']
        raw = line['raw_line']
        if type(number) is not int or number <= last_line or not isinstance(raw, str) or len(raw) > 4096:
            raise ValueError(INVALID)
        match = _ROW.fullmatch(raw)
        if not match:
            raise ValueError(INVALID)
        trade_date, order, symbol, quantity, net = match.groups()
        if datetime.strptime(trade_date, '%m/%d/%Y').strftime('%m/%d/%Y') != trade_date:
            raise ValueError(INVALID)
        amount = net.removeprefix('$').strip()
        if amount != '--' and not re.fullmatch(r'[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,8})?', amount):
            raise ValueError(INVALID)
        observations.append({'source_line_number': number, 'raw_line': raw, 'trade_date_raw': trade_date,
            'order_id': order, 'symbol': symbol, 'signed_qty_raw': quantity, 'net_amount_raw': net,
            'net_amount_usd': None if amount == '--' else format(Decimal(amount.replace(',', '')), 'f'),
            'attribution_status': 'unattributed', 'reasons': ['account_scope_unknown',
                'owner_release_scope_unproved', 'fee_identity_unproved', 'fee_period_coverage_unknown']})
        last_line = number
    immutable = {k: v for k, v in document.items() if k not in {'metadata_text', 'metadata_sha256'}}
    document['document_fingerprint'] = _digest(immutable)
    document['source_receipt_id'] = 'alpaca-crypto-statement-capture:' + _digest(document)
    document['observations'] = observations
    return document


def statement_inventory(documents, *, mode):
    try:
        if not isinstance(documents, list) or len(documents) > 64:
            raise ValueError(CONFLICT)
        unique = {}
        captures = {}
        for document in documents:
            rebuilt = _document(*(document[key] for key in ('metadata_text', 'metadata_sha256', 'document_id',
                'pdf_sha256', 'text_sha256', 'fee_lines')), mode)
            if rebuilt != document:
                raise ValueError(CONFLICT)
            key = document['document_id']
            if key in unique and unique[key]['document_fingerprint'] != document['document_fingerprint']:
                raise ValueError(CONFLICT)
            unique[key] = document
            captures.setdefault(key, {})[document['source_receipt_id']] = {
                'source_receipt_id': document['source_receipt_id'], 'metadata_sha256': document['metadata_sha256']}
        summaries = []
        observations = []
        for key, document in sorted(unique.items()):
            summary = {k: v for k, v in document.items() if k not in {
                'metadata_text', 'metadata_sha256', 'source_receipt_id', 'fee_lines', 'observations'}}
            summary['capture_refs'] = [captures[key][ref] for ref in sorted(captures[key])]
            summaries.append(summary)
            observations.extend({**summary, **row} for row in document['observations'])
        return {'status': 'recorded' if unique else 'unavailable',
            'observation_scope': 'native_statement_capture', 'completeness_status': 'unknown',
            'observed_row_count': len(observations) if unique else None,
            'documents': summaries, 'observations': observations}
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        raise ValueError(CONFLICT) from None


def read_statement_readbacks(path, *, mode, known_metadata_hashes=()):
    directory = None
    captured = None
    try:
        try:
            directory = _private_directory(Path(path))
        except FileNotFoundError:
            return []
        folders = os.listdir(directory)
        if len(folders) > 32:
            raise ValueError(INVALID)
        result = []
        for folder in sorted(folders):
            captured = folder
            if not re.fullmatch(r'[a-f0-9]{64}', folder):
                raise ValueError(INVALID)
            child = _private_directory(folder, dir_fd=directory)
            try:
                raw = _private_bytes('metadata.json', child, 256 * 1024)
                metadata_text = raw.decode('utf-8')
                _, documents = _metadata(metadata_text, folder, mode)
                selected = [key for key, row in documents.items() if row['type'] == 'crypto_account_statement']
                names = os.listdir(child)
                if not selected or {name for name in names if name.endswith('.pdf')} != {key + '.pdf' for key in selected}:
                    raise ValueError(INVALID)
                for key in sorted(selected):
                    pdf = _private_bytes(key + '.pdf', child, MAX_PDF_BYTES)
                    text = _extract_pdf(pdf)
                    result.append(_document(metadata_text, folder, key, hashlib.sha256(pdf).hexdigest(),
                        hashlib.sha256(text.encode()).hexdigest(), _fee_lines(text), mode))
            finally:
                os.close(child)
        return result
    except (ValueError, TypeError, KeyError, AttributeError, OSError, OverflowError) as error:
        reason = str(error)
        if reason not in {'crypto_statement_tool_unavailable', 'crypto_statement_extraction_failed'}:
            reason = CONFLICT if captured in known_metadata_hashes else INVALID
        raise ValueError(reason) from None
    finally:
        if directory is not None:
            os.close(directory)
