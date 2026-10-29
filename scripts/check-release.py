"""Audit the exact tracked source list before public upload; never echo secrets."""
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
FORBIDDEN_PARTS={'.venv','.build','.work','.uploads','.models','results','dist','release','__pycache__'}
PATTERNS={
    'personal developer profile':re.compile(r'C:[\\/]+Users[\\/]+Cheng(?:[\\/]|\b)',re.I),
    'GitHub credential':re.compile(r'gh[oprsu]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}'),
    'private key':re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    'API credential':re.compile(r'\bsk-[A-Za-z0-9_-]{30,}'),
}


def main():
    paths=subprocess.run(['git','ls-files','-z'],cwd=ROOT,capture_output=True,check=True).stdout.decode('utf-8').split('\0')
    paths=[path for path in paths if path]
    if not paths:raise SystemExit('Nothing tracked: stage the intended public source before auditing.')
    failures=[]
    for relative in paths:
        path=ROOT/relative
        if set(Path(relative).parts)&FORBIDDEN_PARTS or path.suffix.lower() in ('.sqlite3','.log','.docx','.pem','.key'):
            failures.append((relative,'private/generated file category'));continue
        if path.is_symlink():failures.append((relative,'symbolic link'));continue
        if not path.is_file():failures.append((relative,'missing tracked file'));continue
        if path.stat().st_size>5*1024*1024:failures.append((relative,'unexpected large source asset'));continue
        if path.suffix.lower() in ('.jpg','.png','.wav','.woff','.woff2'):continue
        try:text=path.read_text('utf-8')
        except UnicodeError:failures.append((relative,'unreviewed binary'));continue
        for label,pattern in PATTERNS.items():
            if pattern.search(text):failures.append((relative,label))
    for path,label in failures:print(f'REVIEW {path}: {label}')
    if failures:raise SystemExit(1)
    print(f'PASS: {len(paths)} tracked source files; no excluded data categories or configured secret/profile patterns.')
    print('This is a bounded automated check, not a legal audit or exhaustive secret detector.')


if __name__=='__main__':main()
