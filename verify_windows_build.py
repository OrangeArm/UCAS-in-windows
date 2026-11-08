# SPDX-License-Identifier: AGPL-3.0-or-later
"""Run the actual EXE from a Unicode path and check its offline GUI diagnostic."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile


def main():
    exe = Path('dist/UCAS-Sign-in.exe').resolve()
    with tempfile.TemporaryDirectory(prefix='ucas-') as tmp:
        folder = Path(tmp) / '中文路径测试'
        folder.mkdir()
        target = folder / exe.name
        shutil.copy2(exe, target)
        report = folder / 'result.json'
        subprocess.run([str(target), '--smoke-test', str(report)], check=True, timeout=90)
        result = json.loads(report.read_text(encoding='utf-8'))
        if not result.get('ok') or not result.get('frozen') or result.get('platform') != 'win32':
            raise RuntimeError(f'Frozen Windows verification failed: {result}')
        Path('dist/build-verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print('EXE verification passed: offline desktop workflow, including Unicode paths.')


if __name__ == '__main__':
    main()
