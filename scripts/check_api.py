# SPDX-License-Identifier: GPL-3.0-only
"""Read-only AST comparison with Autodesk's installed Python definitions.

This verifies class/static-member names, not runtime geometry or overload behavior.
Pass the defs/adsk directory. Fusion is never imported or contacted.
"""
import argparse
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def check(definitions):
    namespaces = {}
    for namespace in ('core', 'fusion'):
        tree = ast.parse((Path(definitions) / (namespace + '.py')).read_text(encoding='utf-8'))
        namespaces[namespace] = {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}
    checked, errors = set(), []
    def members(namespace, name):
        cls = namespaces[namespace].get(name)
        if cls is None:
            return set()
        names = {node.name for node in cls.body if isinstance(node, (ast.FunctionDef, ast.ClassDef))}
        names.update(target.id for node in cls.body if isinstance(node, ast.Assign)
                     for target in node.targets if isinstance(target, ast.Name))
        for base in cls.bases:
            if isinstance(base, ast.Name) and base.id != name:
                names.update(members(namespace, base.id))
        return names
    for path in (ROOT / 'Ejix').glob('*.py'):
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            if not isinstance(node, ast.Attribute):
                continue
            parts, cursor = [], node
            while isinstance(cursor, ast.Attribute):
                parts.insert(0, cursor.attr)
                cursor = cursor.value
            if not isinstance(cursor, ast.Name) or cursor.id != 'adsk' or len(parts) < 2:
                continue
            namespace, name = parts[:2]
            if namespace not in namespaces:
                continue
            checked.add('.'.join(parts))
            if name not in namespaces[namespace] or (len(parts) > 2 and parts[2] not in members(namespace, name)):
                errors.append('%s:%d: adsk.%s' % (path.name, node.lineno, '.'.join(parts)))
    if errors:
        raise ValueError('\n'.join(sorted(set(errors))))
    return len(checked)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('definitions', type=Path)
    args = parser.parse_args()
    print('%d API references checked (static only).' % check(args.definitions))
