#!/usr/bin/env python3
"""Keeps customer details and secrets out of git, for the /chat/ agent's checkout. nadermx/iguana is PUBLIC, and
git history is not a place anything can be quietly deleted from.

Installed to /usr/local/lib/iguana-agent/ and called by the checkout's pre-commit and commit-msg hooks
(git-hooks/), which ansible points `core.hooksPath` at in the system gitconfig:

    pii_scan.py staged            the lines this commit adds
    pii_scan.py message FILE      the commit message

What it refuses:
  * any email address or phone number that belongs to a real person in the database (contacts, orders, form
    and comic submissions, sign-in codes, campaign recipients), read live through the app user's peer login;
  * an address at a webmail domain that is not already somewhere in the repo (old test fixtures are), because a
    new gmail address in a commit is far more likely a customer than a fixture;
  * anything shaped like a credential: Stripe, Meta, GitHub, Anthropic, Slack keys, private keys.

It fails CLOSED: if the database cannot be read, the commit is refused, because "could not check" must not
read as "clean".
"""

import re
import subprocess
import sys

EMAIL = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}')
PHONE = re.compile(r'\+?\d[\d\s().-]{7,}\d')
WEBMAIL = {'gmail.com', 'googlemail.com', 'hotmail.com', 'outlook.com', 'live.com', 'msn.com', 'yahoo.com',
           'yahoo.com.mx', 'hotmail.es', 'icloud.com', 'me.com', 'aol.com', 'protonmail.com', 'proton.me',
           'gmx.com', 'yandex.com', 'mail.ru', 'qq.com'}
SECRETS = [
    (r'\b[sr]k_(live|test)_[A-Za-z0-9]{16,}', 'a Stripe secret key'),
    (r'\bwhsec_[A-Za-z0-9]{16,}', 'a Stripe webhook secret'),
    (r'\bEAA[A-Za-z0-9]{60,}', 'a Meta access token'),
    (r'\b(gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})', 'a GitHub token'),
    (r'\bsk-ant-[A-Za-z0-9_-]{20,}', 'an Anthropic key'),
    (r'\bxox[abposr]-[A-Za-z0-9-]{10,}', 'a Slack token'),
    (r'-----BEGIN [A-Z ]*PRIVATE KEY-----', 'a private key'),
]
PEOPLE_SQL = """
select lower(email), '' from crm_contact union select '', phone from crm_contact
union select lower(customer_email), customer_phone from sales_order
union select lower(email), phone from catalog_formsubmission
union select lower(email), phone from crm_comicsubmission
union select lower(email), '' from crm_campaignrecipient
union select lower(email), '' from sales_logintoken
union select lower(to_email), '' from sales_credittransfer
"""
OURS = re.compile(r'@(iguanacomedy\.(com|mx)|example\.(com|org|net)|[a-z0-9.-]+\.test|anthropic\.com)$', re.I)


def digits(text):
    return re.sub(r'\D', '', text or '')


def load_people(runner=subprocess.run):
    """(emails, phone digit strings) of every real person the database knows. Raises when it cannot read them."""
    result = runner(['sudo', '-n', '-u', 'iguana', 'psql', '-d', 'iguana', '-AtF', '\t', '-c', PEOPLE_SQL],
                    capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or 'psql failed')
    emails, phones = set(), set()
    for line in result.stdout.splitlines():
        email, _, phone = line.partition('\t')
        if email.strip():
            emails.add(email.strip().lower())
        if len(digits(phone)) >= 8:
            phones.add(digits(phone)[-10:])
    if not emails:
        raise RuntimeError('the database returned no addresses at all, which cannot be right')
    return emails, phones


def problems(text, emails, phones, already_in_repo=frozenset()):
    """Every reason `text` must not be committed, one line each."""
    found = []
    for pattern, label in SECRETS:
        if re.search(pattern, text):
            found.append(f'it contains what looks like {label}')
    for address in sorted({a.lower() for a in EMAIL.findall(text)}):
        if OURS.search(address):
            continue
        if address in emails:
            found.append(f'it contains the email address of a real customer ({_mask(address)})')
        elif address.split('@', 1)[1] in WEBMAIL and address not in already_in_repo:
            found.append(f'it contains a personal email address ({_mask(address)}); use someone@example.com in '
                         'tests and docs')
    for number in {digits(n)[-10:] for n in PHONE.findall(text) if len(digits(n)) >= 8}:
        if number in phones:
            found.append(f'it contains the phone number of a real customer (ending {number[-3:]})')
    return found


def _mask(address):
    local, _, domain = address.partition('@')
    return f'{local[:1]}***@{domain}'


def _staged_added_text():
    diff = subprocess.run(['git', 'diff', '--cached', '-U0', '--no-color', '--text', '--diff-filter=ACMR'],
                          capture_output=True, text=True, errors='replace', check=True).stdout
    return '\n'.join(line[1:] for line in diff.splitlines() if line.startswith('+') and not line.startswith('+++'))


def _repo_addresses():
    out = subprocess.run(['git', 'grep', '-ohIE', EMAIL.pattern, 'HEAD'], capture_output=True, text=True).stdout
    return frozenset(a.split(':', 1)[-1].lower() for a in out.split())


def main(argv):
    if len(argv) < 2 or argv[1] not in ('staged', 'message'):
        sys.stderr.write(__doc__)
        return 2
    text = _staged_added_text() if argv[1] == 'staged' else open(argv[2], errors='replace').read()
    try:
        emails, phones = load_people()
    except Exception as exc:  # noqa: BLE001: any failure to check is a refusal
        sys.stderr.write(f'Commit refused: could not read the customer list to check against ({exc}).\n')
        return 1
    found = problems(text, emails, phones, _repo_addresses())
    if found:
        what = 'commit message' if argv[1] == 'message' else 'staged changes'
        sys.stderr.write(f'Commit refused, the {what} would publish this on GitHub (the repo is public):\n')
        sys.stderr.write(''.join(f'  - {line}\n' for line in found))
        sys.stderr.write('Take it out and commit again. Cite a measurement without the identifier '
                         '("one address on the list").\n')
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
