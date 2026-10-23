from datetime import timedelta

from django.db import models
from django.utils import timezone

from catalog.models import Event, TicketType
from crm.models import Contact
from iguana.ids import new_id, new_token


class Order(models.Model):
    PENDING, COMPLETED, REFUNDED, CANCELLED = 'PENDING', 'COMPLETED', 'REFUNDED', 'CANCELLED'
    STATUS_CHOICES = [(s, s.title()) for s in (PENDING, COMPLETED, REFUNDED, CANCELLED)]

    id = models.CharField(primary_key=True, max_length=40, default=new_id, editable=False)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=PENDING)
    currency = models.CharField(max_length=3, default='usd')
    total_amount_cents = models.PositiveIntegerField(default=0)
    discount_amount_cents = models.PositiveIntegerField(default=0)
    credits_applied_cents = models.PositiveIntegerField(default=0)
    # Reservations of pay-at-the-door ticket types: nothing is charged online and the door collects this amount,
    # so revenue actually received online is total_amount_cents - pay_at_door_cents.
    pay_at_door_cents = models.PositiveIntegerField(default=0)
    # The language the customer booked in; the order page and confirmation email follow it.
    locale = models.CharField(max_length=5, default='en')
    contact = models.ForeignKey(Contact, null=True, blank=True, on_delete=models.SET_NULL, related_name='orders')
    customer_name = models.CharField(max_length=200, blank=True)
    customer_email = models.EmailField()
    customer_phone = models.CharField(max_length=40, blank=True)
    event = models.ForeignKey(Event, null=True, blank=True, on_delete=models.SET_NULL, related_name='orders')
    event_name = models.CharField(max_length=200, blank=True, help_text='Snapshot, kept when the event row is missing.')
    stripe_payment_intent_id = models.CharField(max_length=80, blank=True, db_index=True)
    stripe_charge_id = models.CharField(max_length=80, blank=True)
    public_view_token = models.CharField(max_length=60, default=new_token, unique=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    refunded_at = models.DateTimeField(null=True, blank=True)
    # Stamped by `send_after_show`, so the morning-after note can only ever go out once per booking however
    # many times the cron runs or is re-run by hand.
    follow_up_sent_at = models.DateTimeField(null=True, blank=True)
    # Stamped by `send_show_reminders` so the day-of reminder goes out once per booking.
    reminder_sent_at = models.DateTimeField(null=True, blank=True)
    # Set when the guest gave their open mic seat back from the reminder. The order becomes CANCELLED, which is
    # what frees the seat everywhere (every count reads COMPLETED); this says it was THEIR choice, so the door
    # can say "gave their seat back" rather than "unpaid".
    released_at = models.DateTimeField(null=True, blank=True)
    attribution = models.JSONField(default=dict, blank=True)
    # Blank for our own sales. Set when the row came from somewhere else, currently a guest promoter's export:
    # those guests need to be findable at the door, but their money is not ours and must not be counted twice.
    source = models.CharField(max_length=20, blank=True, db_index=True,
                              help_text="Blank for our own sales; 'goliiive' for an imported promoter list.")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.customer_email} {self.event_name} ({self.status})'


class OrderItem(models.Model):
    id = models.CharField(primary_key=True, max_length=40, default=new_id, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    ticket_type = models.ForeignKey(TicketType, null=True, blank=True, on_delete=models.SET_NULL)
    name = models.CharField(max_length=120)
    quantity = models.PositiveIntegerField()
    unit_price_cents = models.PositiveIntegerField()
    # Snapshotted rather than read back off `ticket_type`, which is nullable: a drink must still be a drink
    # after its ticket type is deleted, or an old order starts issuing seat tickets for a round of beers.
    is_addon = models.BooleanField(default=False)


class Ticket(models.Model):
    id = models.CharField(primary_key=True, max_length=40, default=new_id, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='tickets')
    ticket_type_name = models.CharField(max_length=120)
    checkin_token = models.CharField(max_length=80, default=new_token, unique=True)
    checked_in_at = models.DateTimeField(null=True, blank=True)

    @property
    def door_price_cents(self):
        """What the door collects for this seat: 0 unless the order was reserved to pay at the door."""
        if not self.order.pay_at_door_cents:
            return 0
        item = next((i for i in self.order.items.all() if i.name == self.ticket_type_name), None)
        return item.unit_price_cents if item else 0


class MembershipPlan(models.Model):
    id = models.CharField(primary_key=True, max_length=40, default=new_id, editable=False)
    name = models.CharField(max_length=120)
    name_es = models.CharField(max_length=120, blank=True)
    description = models.TextField(blank=True)
    description_es = models.TextField(blank=True)
    benefits = models.JSONField(default=list, blank=True, help_text='["Two free tickets", ...]')
    benefits_es = models.JSONField(default=list, blank=True, help_text='["Dos boletos gratis", ...]')
    currency = models.CharField(max_length=3, default='mxn')
    monthly_cents = models.PositiveIntegerField(null=True, blank=True)
    annual_cents = models.PositiveIntegerField(null=True, blank=True)
    lifetime_cents = models.PositiveIntegerField(null=True, blank=True)
    pass_cents = models.PositiveIntegerField(null=True, blank=True)
    pass_days = models.PositiveIntegerField(null=True, blank=True)
    free_tickets_per_order = models.PositiveIntegerField(default=2)
    guest_discount_percent = models.PositiveIntegerField(default=10)
    stripe_product_id = models.CharField(max_length=60, blank=True)

    def label(self, lang):
        return self.name_es if lang == 'es' and self.name_es else self.name

    def details(self, lang):
        return self.description_es if lang == 'es' and self.description_es else self.description

    def perks(self, lang):
        return self.benefits_es if lang == 'es' and self.benefits_es else (self.benefits or [])
    active = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'name']

    def __str__(self):
        return self.name


class Membership(models.Model):
    ACTIVE, PENDING, CANCELED, EXPIRED, PAST_DUE = 'ACTIVE', 'PENDING', 'CANCELED', 'EXPIRED', 'PAST_DUE'
    STATUS_CHOICES = [(s, s.replace('_', ' ').title()) for s in (ACTIVE, PENDING, CANCELED, EXPIRED, PAST_DUE)]

    id = models.CharField(primary_key=True, max_length=40, default=new_id, editable=False)
    contact = models.ForeignKey(Contact, on_delete=models.CASCADE, related_name='memberships')
    plan = models.ForeignKey(MembershipPlan, on_delete=models.PROTECT, related_name='memberships')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=PENDING)
    source = models.CharField(max_length=20, blank=True, help_text='RECURRING, LIFETIME, PASS, CODE, MANUAL')
    billing_interval = models.CharField(max_length=10, blank=True)
    starts_at = models.DateTimeField(default=timezone.now)
    ends_at = models.DateTimeField(null=True, blank=True)
    auto_renew = models.BooleanField(default=False)
    credit_balance_cents = models.IntegerField(default=0)
    stripe_subscription_id = models.CharField(max_length=80, blank=True, db_index=True)
    stripe_customer_id = models.CharField(max_length=60, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.contact.email}: {self.plan.name} ({self.status})'

    @property
    def is_current(self):
        return self.status == self.ACTIVE and (self.ends_at is None or self.ends_at > timezone.now())


class RedeemCode(models.Model):
    MEMBERSHIP, CREDITS = 'membership', 'credits'

    code = models.CharField(max_length=40, unique=True)
    kind = models.CharField(max_length=12, choices=[(MEMBERSHIP, 'Membership'), (CREDITS, 'Credits')])
    plan = models.ForeignKey(MembershipPlan, null=True, blank=True, on_delete=models.PROTECT)
    days = models.PositiveIntegerField(null=True, blank=True, help_text='Membership length granted')
    amount_cents = models.PositiveIntegerField(null=True, blank=True)
    currency = models.CharField(max_length=3, default='mxn')
    max_uses = models.PositiveIntegerField(default=1)
    uses = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.code


class CreditTransfer(models.Model):
    id = models.CharField(primary_key=True, max_length=40, default=new_id, editable=False)
    sender = models.ForeignKey(Contact, on_delete=models.CASCADE, related_name='credit_transfers_sent')
    from_membership = models.ForeignKey(Membership, null=True, blank=True, on_delete=models.SET_NULL)
    to_email = models.EmailField()
    recipient = models.ForeignKey(Contact, null=True, blank=True, on_delete=models.SET_NULL, related_name='credit_transfers_received')
    amount_cents = models.PositiveIntegerField()
    currency = models.CharField(max_length=3, default='mxn')
    status = models.CharField(max_length=10, default='PENDING')
    created_at = models.DateTimeField(default=timezone.now)
    claimed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']


def _login_expiry():
    return timezone.now() + timedelta(minutes=30)


class TableOrder(models.Model):
    """A round ordered from the table, by the person sitting at it.

    The QR on the table carries the table number, so the order knows where to go: the whole point is that
    nobody has to catch a waiter's eye during a set. Payment happens at the table as it always has; this
    replaces the waiting, not the till.
    """

    OPEN, DELIVERED, PAID, CANCELLED = 'OPEN', 'DELIVERED', 'PAID', 'CANCELLED'
    STATUS_CHOICES = [(s, s.title()) for s in (OPEN, DELIVERED, PAID, CANCELLED)]

    id = models.CharField(primary_key=True, max_length=40, default=new_id, editable=False)
    table_number = models.PositiveSmallIntegerField()
    # The night this round belongs to, stamped when it is ordered. Without it the bar's takings are a pile of
    # timestamps: "what did we sell on the Fredy night" is the question, and the answer has to survive the
    # calendar rolling over at midnight while the show is still on.
    event = models.ForeignKey('catalog.Event', null=True, blank=True, on_delete=models.SET_NULL,
                              related_name='table_orders')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=OPEN)
    total_cents = models.PositiveIntegerField(default=0)
    currency = models.CharField(max_length=3, default='mxn')
    # Who ordered it. Optional, and the table number is what actually routes the drink, but a name lets the
    # waiter arrive saying one rather than holding a tray over a table asking who had the margarita.
    guest_name = models.CharField(max_length=80, blank=True)
    note = models.CharField(max_length=300, blank=True)
    locale = models.CharField(max_length=5, default='en')
    # Settled at the table, which is the end of the round trip: ordered, carried over, paid for.
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    delivered_at = models.DateTimeField(null=True, blank=True)
    # When this round was taken out of the store room. A stamp rather than a boolean so it is obvious WHEN, and
    # so the only way to double-count is to clear it deliberately. Delivering a round twice, a double-tap on a
    # phone, or a page reload must not empty the fridge twice: see `sales/stock.py`.
    stock_applied_at = models.DateTimeField(null=True, blank=True)
    # The party paid, got up and left, and the table is free for the next one. The round stays in the night's
    # takings; it just stops being this table's running tab, so the next people do not sit down in front of
    # somebody else's bill. Without this a card carried its total until 6am and there was no way to clear it.
    closed_at = models.DateTimeField(null=True, blank=True)
    # Set when the table paid by card from its own phone. A `Marcar pagado` tap leaves it blank, which is the
    # difference between "somebody said they paid" and "a card was charged", and the takings should never have
    # to guess which happened.
    payment = models.ForeignKey('TablePayment', null=True, blank=True, on_delete=models.SET_NULL,
                                related_name='orders')

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Table {self.table_number}: {self.status}'

    @property
    def summary(self):
        return ', '.join(f'{i.quantity} x {i.name}' for i in self.items.all() if not i.voided)

    def recount(self):
        """Re-add the lines that still count and save the total.

        `total_cents` stays a stored column rather than becoming a property: the board, `/stats/` and the
        night's takings all sum it across hundreds of rows, and a property would turn each of those into a
        query per round. So it is recomputed at the one moment it can change.
        """
        self.total_cents = sum(item.line_cents for item in self.items.all())
        self.save(update_fields=['total_cents'])
        return self.total_cents


class TablePayment(models.Model):
    """A table settling its whole bill from a phone, by scanning the QR the waiter holds up.

    🚨 The amount is NEVER taken from the browser. The page posts which TIP was chosen, out of a fixed list of
    percentages, and the bill itself is summed here from the rounds that are actually on the table: a form
    field carrying an amount is a form field somebody can edit, and a bar bill is exactly the thing worth
    editing. What the customer sends is a choice; what they are charged is a fact.

    One payment covers every unpaid round on the table, because that is what "the bill" means to the people
    sitting at it. The rounds point back here (`TableOrder.payment`), so "what did this table pay and when"
    survives the night, and so the takings can tell a card payment from a `Marcar pagado` tap.
    """

    PENDING, PAID, ABANDONED = 'PENDING', 'PAID', 'ABANDONED'
    STATUS_CHOICES = [(s, s.title()) for s in (PENDING, PAID, ABANDONED)]

    id = models.CharField(primary_key=True, max_length=40, default=new_id, editable=False)
    table_number = models.PositiveSmallIntegerField()
    event = models.ForeignKey('catalog.Event', null=True, blank=True, on_delete=models.SET_NULL,
                              related_name='table_payments')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=PENDING)
    # The drinks, the tip, and what the card was actually charged. Kept apart on purpose: the tip is not the
    # bar's takings and must never be added to them, and a single `total` would make that impossible to undo
    # later without guessing.
    bill_cents = models.PositiveIntegerField(default=0)
    tip_cents = models.PositiveIntegerField(default=0)
    tip_percent = models.PositiveSmallIntegerField(default=0)
    total_cents = models.PositiveIntegerField(default=0)
    currency = models.CharField(max_length=3, default='mxn')
    locale = models.CharField(max_length=5, default='es')
    stripe_payment_intent_id = models.CharField(max_length=120, blank=True)
    stripe_charge_id = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Table {self.table_number}: {self.total_cents / 100:.2f} {self.currency.upper()}'


class TableOrderItem(models.Model):
    """A line on a round, and whether it was taken back off.

    🚨 Taking a line off VOIDS it rather than deleting it. The bar wants it gone from the bill, which it is, but
    a deleted row changes the night's takings leaving nothing behind: a void is the one thing in a bar that
    everybody agrees has to be traceable, because "remove a drink from the bill" is also how money leaves a
    till. The line stays, struck through, with who took it off and why.
    """

    # Why it came off, and the two are NOT the same fact about the store room. A drink that was never made is
    # still in the bottle, so the count has to come back up. A drink that was made and thrown away is gone,
    # and returning it to the count would make the sheet claim stock that is in a bin.
    NOT_MADE, WASTED = 'NOT_MADE', 'WASTED'
    VOID_REASONS = [(NOT_MADE, 'No se preparó'), (WASTED, 'Se preparó y se tiró')]

    id = models.CharField(primary_key=True, max_length=40, default=new_id, editable=False)
    order = models.ForeignKey(TableOrder, on_delete=models.CASCADE, related_name='items')
    menu_item = models.ForeignKey('catalog.MenuItem', null=True, blank=True, on_delete=models.SET_NULL)
    # Snapshotted, in the customer's language: a price change tonight must not rewrite what they ordered.
    name = models.CharField(max_length=120)
    quantity = models.PositiveSmallIntegerField()
    unit_price_cents = models.PositiveIntegerField()
    voided_at = models.DateTimeField(null=True, blank=True)
    void_reason = models.CharField(max_length=10, choices=VOID_REASONS, blank=True)
    void_note = models.CharField(max_length=200, blank=True)
    voided_by = models.CharField(max_length=80, blank=True)
    # Whether the ingredients went back on the shelf. A stamp rather than inferred from the reason, because the
    # round may never have been delivered, in which case nothing had left and there is nothing to return.
    stock_returned_at = models.DateTimeField(null=True, blank=True)

    @property
    def voided(self):
        return self.voided_at is not None

    @property
    def line_cents(self):
        return 0 if self.voided else self.unit_price_cents * self.quantity


class LoginToken(models.Model):
    email = models.EmailField(db_index=True)
    token = models.CharField(max_length=60, default=new_token, unique=True)
    code = models.CharField(max_length=6)
    expires_at = models.DateTimeField(default=_login_expiry)
    used_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    ip = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
