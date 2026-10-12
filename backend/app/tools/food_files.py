"""Read CSV/XLSX source rows with standard-library streaming; no Excel dependency."""
import csv
from pathlib import Path
import xml.etree.ElementTree as ET
from zipfile import ZipFile

NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'


def read_rows(path: Path):
    if path.suffix.lower() == '.csv':
        # Decide encoding before yielding so fallback cannot duplicate rows.
        with path.open('rb') as stream:
            sample = stream.read(1024 * 1024)
        try:
            sample.decode('utf-8-sig')
            encoding = 'utf-8-sig'
        except UnicodeDecodeError:
            encoding = 'cp949'
        with path.open(encoding=encoding, newline='') as stream:
            yield from csv.DictReader(stream)
        return
    if path.suffix.lower() != '.xlsx':
        raise ValueError('unsupported_file_format')
    with ZipFile(path) as archive:
        strings = []
        if 'xl/sharedStrings.xml' in archive.namelist():
            with archive.open('xl/sharedStrings.xml') as stream:
                for _, element in ET.iterparse(stream, events=('end',)):
                    if element.tag == NS + 'si':
                        strings.append(''.join(child.text or '' for child in element.iter(NS + 't')))
                        element.clear()
        with archive.open('xl/worksheets/sheet1.xml') as stream:
            headers = None
            for _, element in ET.iterparse(stream, events=('end',)):
                if element.tag != NS + 'row':
                    continue
                cells = {}
                for cell in element.findall(NS + 'c'):
                    column = ''.join(ch for ch in cell.attrib['r'] if ch.isalpha())
                    value = cell.findtext(NS + 'v', '')
                    if cell.attrib.get('t') == 's':
                        value = strings[int(value)]
                    elif cell.attrib.get('t') == 'inlineStr':
                        value = ''.join(child.text or '' for child in cell.iter(NS + 't'))
                    cells[column] = value
                if headers is None:
                    headers = cells
                else:
                    yield {name: cells.get(column, '') for column, name in headers.items()}
                element.clear()
