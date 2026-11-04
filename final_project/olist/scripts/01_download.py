"""Download the Olist archive from Kaggle's official public file endpoint.

No web-page scraping or third-party mirrors are used. Run from any directory.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import urllib.request
from zipfile import ZipFile, is_zipfile

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data' / 'raw'
SOURCE = 'https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce'
DOWNLOAD = 'https://www.kaggle.com/api/v1/datasets/download/olistbr/brazilian-ecommerce'
EXPECTED = {
    'olist_customers_dataset.csv', 'olist_geolocation_dataset.csv',
    'olist_order_items_dataset.csv', 'olist_order_payments_dataset.csv',
    'olist_order_reviews_dataset.csv', 'olist_orders_dataset.csv',
    'olist_products_dataset.csv', 'olist_sellers_dataset.csv',
    'product_category_name_translation.csv',
}


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    archive = RAW / 'brazilian-ecommerce.zip'
    if not archive.exists():
        part = archive.with_suffix('.zip.part')
        req = urllib.request.Request(DOWNLOAD, headers={'User-Agent': 'OlistCourseAnalysis/1.0'})
        size = 0
        with urllib.request.urlopen(req, timeout=90) as response, part.open('wb') as out:
            final_url = response.url
            while chunk := response.read(1024 * 1024):
                size += len(chunk)
                if size > 250 * 1024 * 1024:
                    raise RuntimeError('Download exceeds the expected 250 MiB limit.')
                out.write(chunk)
        if not is_zipfile(part):
            raise RuntimeError('Kaggle did not return a ZIP. Login or manual official download may be needed.')
        part.replace(archive)
        downloaded_at = datetime.now(timezone.utc).isoformat()
    else:
        final_url = None
        downloaded_at = None

    with ZipFile(archive) as z:
        if set(z.namelist()) != EXPECTED:
            raise RuntimeError('Unexpected archive contents; inspect before extracting.')
        if z.testzip() is not None:
            raise RuntimeError('Archive CRC check failed.')
        files = []
        for name in sorted(EXPECTED):
            data = z.read(name)
            target = RAW / name
            if target.exists() and target.read_bytes() != data:
                raise RuntimeError(f'Refusing to overwrite changed raw file: {name}')
            if not target.exists():
                target.write_bytes(data)
            files.append({'file': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
    manifest_path = RAW / 'source_manifest.json'
    if not manifest_path.exists():
        manifest = {
            'source_name': 'Brazilian E-Commerce Public Dataset by Olist',
            'publisher': 'Olist on Kaggle', 'source_url': SOURCE,
            'download_endpoint': DOWNLOAD, 'downloaded_at_utc': downloaded_at,
            'method': 'Official Kaggle public archive download; no scraping',
            'license': 'CC BY-NC-SA 4.0 (as displayed on the official dataset page)',
            'license_url': 'https://creativecommons.org/licenses/by-nc-sa/4.0/',
            'dataset_version': 'Not independently verified; identify this copy using archive and file hashes.',
            'archive_bytes': archive.stat().st_size,
            'archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
            'uncompressed_bytes': sum(f['bytes'] for f in files), 'files': files,
        }
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'archive_bytes': archive.stat().st_size,
                      'uncompressed_bytes': sum(f['bytes'] for f in files),
                      'files': len(files), 'crc_check': 'passed'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
