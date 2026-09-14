#!/usr/bin/python3
"""Read-only comparison of the archived SL7 base and cached Ubuntu candidates."""
from pathlib import Path
from datetime import datetime
import json
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    base = json.loads((ROOT / 'inventory/source-provenance.json').read_text())['kernel_source_version']
    running = subprocess.check_output(['uname', '-r'], text=True).strip()
    print('运行内核：' + running)
    print('本归档 Ubuntu 基线：' + base)
    newer = []
    for package in ('linux-generic-hwe-26.04', 'linux-image-generic-hwe-26.04', 'linux-headers-generic-hwe-26.04'):
        result = subprocess.check_output(['apt-cache', 'policy', package], text=True,
                                         env={**__import__('os').environ, 'LC_ALL': 'C'})
        installed = re.search(r'^\s*Installed:\s*(\S+)', result, re.M)
        candidate = re.search(r'^\s*Candidate:\s*(\S+)', result, re.M)
        value = candidate.group(1) if candidate else '(none)'
        print(f'{package}: 已装={installed.group(1) if installed else "(none)"}；候选={value}')
        if value != '(none)' and subprocess.run(['dpkg', '--compare-versions', value, 'gt', base]).returncode == 0:
            newer.append(package)
    stamps = [f.stat().st_mtime for f in Path('/var/lib/apt/lists').glob('*InRelease')]
    if stamps:
        print('缓存 InRelease 文件最新时间：' + datetime.fromtimestamp(max(stamps)).astimezone().isoformat())
    print('本工具不刷新 APT 缓存；使用前可自行运行 sudo apt update。')
    if newer:
        print('有更新的 Ubuntu 内核基线：安排移植、独立构建、签名和单次启动验证。')
    else:
        print('现有缓存没有显示更高的内核元包候选版本；这不替代安全公告检查。')
    print('固定为默认的本地内核不会自动吸收官方新包中的安全修复。')


if __name__ == '__main__':
    main()
