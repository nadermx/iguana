"""Run the open mic ads for the three days before each night, unless it is full or an hour from starting.

    manage.py open_mic_ads            # say what it would do
    manage.py open_mic_ads --apply    # do it

Runs on a cron every ten minutes. The rule and why it touches only the campaign live in crm/open_mic_ads.py.
"""

from django.core.management.base import BaseCommand

from crm.open_mic_ads import sync


class Command(BaseCommand):
    help = 'Switch the open mic Meta campaigns on or off by whether their next night can still sell'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Change the campaigns (default: dry run)')

    def handle(self, *args, **opts):
        for line in sync(apply=opts['apply']):
            self.stdout.write(line)
