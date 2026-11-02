"""Step presale prices up when their moment comes (cron, every minute).

A ticket type with `price_change_at` in the past and a `price_after_cents` gets that price, and both fields are
cleared so it happens once. The checkout reads `price_cents` like always, so a presale needs nothing else.
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from catalog.models import TicketType


class Command(BaseCommand):
    help = 'Apply scheduled ticket price changes whose time has come.'

    def handle(self, *args, **options):
        due = TicketType.objects.filter(price_change_at__lte=timezone.now(), price_after_cents__isnull=False)
        with transaction.atomic():
            for ticket_type in due.select_for_update(of=('self',)).select_related('event'):
                before = ticket_type.price_cents
                ticket_type.price_cents = ticket_type.price_after_cents
                ticket_type.price_change_at = None
                ticket_type.price_after_cents = None
                ticket_type.save(update_fields=['price_cents', 'price_change_at', 'price_after_cents'])
                self.stdout.write(f'{ticket_type.event.slug}: {ticket_type.name} {before / 100:g} -> '
                                  f'{ticket_type.price_cents / 100:g} {ticket_type.event.currency.upper()}')
