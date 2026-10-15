import csv
import io
import json


def export_rows(storage, batch_id=None, format='jsonl'):
    offset = 0
    columns = None
    while True:
        items = storage.history(limit=200, offset=offset, batch_id=batch_id)
        if not items:
            return
        for item in items:
            if format == 'jsonl':
                yield json.dumps(item, ensure_ascii=False) + '\n'
                continue
            output = io.StringIO(newline='')
            if columns is None:
                columns = list(item)
                writer = csv.DictWriter(output, fieldnames=columns)
                writer.writeheader()
            else:
                writer = csv.DictWriter(output, fieldnames=columns)
            row = {}
            for key, value in item.items():
                if isinstance(value, (dict, list)):
                    value = json.dumps(value, ensure_ascii=False)
                if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@')):
                    value = "'" + value
                row[key] = value
            writer.writerow(row)
            yield output.getvalue()
        offset += len(items)
