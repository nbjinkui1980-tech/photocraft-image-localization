#!/usr/bin/env python3
import argparse
import json
import zipfile
from pathlib import Path


def walk(layers, parent_visible=True, ancestry=()):
    for layer in layers:
        visible = parent_visible and layer.get('visible', True) and layer.get('opacity', 1) > 0
        content = layer.get('content', {})
        if content.get('kind') == 'text':
            yield {'id': layer.get('id'), 'name': layer.get('name'), 'parents': ancestry,
                   'visible': bool(visible), 'text': content.get('text', ''),
                   'transform': content.get('transform'), 'shape': content.get('shape')}
        children = content.get('children', layer.get('children', [])) or []
        yield from walk(children, visible, (*ancestry, layer.get('id')))


def main():
    parser = argparse.ArgumentParser(description='JSONL editable text; excludes hidden layers and hidden ancestors by default')
    parser.add_argument('--include-hidden', action='store_true')
    parser.add_argument('files', nargs='+', type=Path)
    args = parser.parse_args()
    for path in args.files:
        with zipfile.ZipFile(path) as archive:
            doc = json.loads(archive.read('manifest.json'))['document']
        for row in walk(doc.get('layers', [])):
            if row['visible'] or args.include_hidden:
                print(json.dumps({'file': str(path), **row}, ensure_ascii=False))


if __name__ == '__main__':
    main()
