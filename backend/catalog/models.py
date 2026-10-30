from django.db import models
from django.utils import timezone
from django.utils.text import slugify

from iguana.ids import new_id


class Venue(models.Model):
    id = models.CharField(primary_key=True, max_length=40, default=new_id, editable=False)
    slug = models.SlugField(max_length=120, unique=True)
    name = models.CharField(max_length=200)
    address = models.CharField(max_length=300, blank=True)
    city = models.CharField(max_length=120, blank=True)
    country = models.CharField(max_length=120, blank=True, default='Mexico')
    description = models.TextField(blank=True)
    lat = models.FloatField(null=True, blank=True)
    lng = models.FloatField(null=True, blank=True)
    time_zone = models.CharField(max_length=60, default='America/Cancun')
    capacity = models.PositiveIntegerField(default=0)
    image_url = models.CharField(max_length=500, blank=True, help_text='Absolute URL or /media/... path')
    wheelchair_accessible = models.BooleanField(null=True, blank=True)
    listed = models.BooleanField(default=True, help_text='Show on the public locations pages.')

    class Meta:
        ordering = ['city', 'name']

    def __str__(self):
        return f'{self.name} ({self.city})' if self.city else self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)[:120] or new_id()
        super().save(*args, **kwargs)


class Artist(models.Model):
    id = models.CharField(primary_key=True, max_length=40, default=new_id, editable=False)
    slug = models.SlugField(max_length=120, unique=True)
    name = models.CharField(max_length=200)
    stage_name = models.CharField(max_length=200, blank=True)
    bio = models.TextField(blank=True)
    bio_es = models.TextField(blank=True)
    image_url = models.CharField(max_length=500, blank=True, help_text='Absolute URL or /media/... path')
    website = models.URLField(max_length=500, blank=True)
    home_city = models.CharField(max_length=120, blank=True)
    residency = models.CharField(max_length=200, blank=True)
    socials = models.JSONField(default=dict, blank=True, help_text='{"instagram": "https://..."}')
    reels = models.JSONField(default=list, blank=True, help_text='[{"title": "", "url": "", "posterUrl": null}]')
    sort_order = models.IntegerField(default=0)
    listed = models.BooleanField(default=True)

    class Meta:
        ordering = ['sort_order', 'name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)[:120] or new_id()
        super().save(*args, **kwargs)


class Tour(models.Model):
    id = models.CharField(primary_key=True, max_length=40, default=new_id, editable=False)
    slug = models.SlugField(max_length=120, unique=True)
    name = models.CharField(max_length=200)
    image_url = models.CharField(max_length=500, blank=True, help_text='Absolute URL or /media/... path')

    def __str__(self):
        return self.name


class Event(models.Model):
    DRAFT, ACTIVE, SOLD_OUT, POSTPONED, CANCELLED = 'DRAFT', 'ACTIVE', 'SOLD_OUT', 'POSTPONED', 'CANCELLED'
    STATUS_CHOICES = [(s, s.replace('_', ' ').title()) for s in (DRAFT, ACTIVE, SOLD_OUT, POSTPONED, CANCELLED)]
    VISIBILITY_CHOICES = [('PUBLIC', 'Public'), ('UNLISTED', 'Unlisted'), ('MEMBERS', 'Members only')]
    TICKETING_CHOICES = [('INTERNAL', 'Sold here'), ('EXTERNAL', 'External link')]

    id = models.CharField(primary_key=True, max_length=40, default=new_id, editable=False)
    slug = models.SlugField(max_length=160, unique=True)
    name = models.CharField(max_length=200)
    name_es = models.CharField(max_length=200, blank=True, help_text='Spanish name; blank falls back to the name.')
    date = models.DateTimeField(help_text='Show day. Imported rows are midnight in Cancun.')
    doors_open = models.CharField(max_length=10, blank=True, help_text='24h clock, e.g. 19:30')
    show_time = models.CharField(max_length=10, blank=True, help_text='24h clock, e.g. 20:00')
    end_time = models.CharField(max_length=10, blank=True)
    description = models.TextField(blank=True)
    description_es = models.TextField(blank=True, help_text='Spanish description; blank falls back.')
    long_description = models.TextField(blank=True)
    long_description_es = models.TextField(blank=True, help_text='Spanish long description; blank falls back.')
    image_url = models.CharField(max_length=500, blank=True, help_text='Absolute URL or /media/... path')
    image_url_mobile = models.CharField(max_length=500, blank=True, help_text='Absolute URL or /media/... path')
    # Posters whose artwork carries Spanish text; blank falls back to the ones above.
    image_url_es = models.CharField(max_length=500, blank=True, help_text='Spanish poster; blank falls back.')
    image_url_mobile_es = models.CharField(max_length=500, blank=True, help_text='Spanish mobile poster.')
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=DRAFT)
    visibility = models.CharField(max_length=10, choices=VISIBILITY_CHOICES, default='PUBLIC')
    ticketing_type = models.CharField(max_length=10, choices=TICKETING_CHOICES, default='INTERNAL')
    external_ticket_url = models.CharField(max_length=500, blank=True, help_text='Absolute URL or /media/... path')
    currency = models.CharField(max_length=3, default='usd')
    language = models.CharField(max_length=5, default='en')
    age_restriction = models.CharField(max_length=40, blank=True)
    tags = models.JSONField(default=list, blank=True)
    reviews = models.JSONField(default=list, blank=True, help_text='[{"quote": "", "stars": 5, "source": ""}]')
    # Nullable on purpose: between `migrate` and the worker reload, old code inserts events without this column.
    gallery = models.JSONField(default=list, blank=True, null=True, help_text=(
        'Photos shown on the event page, around the description: [{"url": "/media/...", "alt": "", "alt_es": "", '
        '"section": "before" or "after", "width": 1600, "height": 1067}]'))
    venue = models.ForeignKey(Venue, null=True, blank=True, on_delete=models.SET_NULL, related_name='events')
    venue_label = models.CharField(max_length=200, blank=True, help_text='Venue name as exported, when no Venue row matched.')
    tour = models.ForeignKey(Tour, null=True, blank=True, on_delete=models.SET_NULL, related_name='events')
    # Off by default and off on every night since 2026-09-24: the club sells no membership. The field and the
    # pricing behind it are kept rather than ripped out, because removing them means surgery on the checkout's
    # price path for no gain while nobody holds a membership. Turning it on again is a product decision, not a
    # checkbox: it needs a plan marked active AND this flag, and the admin no longer offers the flag.
    members_eligible = models.BooleanField(default=False, help_text='Dead unless the club sells memberships again.')
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['date']

    def __str__(self):
        return f'{self.name} ({self.date:%Y-%m-%d})'

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)[:160] or new_id()
        super().save(*args, **kwargs)

    @property
    def is_public(self):
        return self.status != self.DRAFT and self.visibility != 'UNLISTED'

    def _localized(self, lang, spanish, english):
        return spanish if lang == 'es' and spanish else english

    def label(self, lang):
        return self._localized(lang, self.name_es, self.name)

    def details(self, lang):
        return self._localized(lang, self.description_es, self.description)

    def long_details(self, lang):
        return self._localized(lang, self.long_description_es, self.long_description)

    def poster(self, lang):
        return self._localized(lang, self.image_url_es, self.image_url)

    def poster_mobile(self, lang):
        return self._localized(lang, self.image_url_mobile_es, self.image_url_mobile)


class LineupEntry(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='lineup')
    artist = models.ForeignKey(Artist, on_delete=models.CASCADE, related_name='lineup_entries')
    role = models.CharField(max_length=60, blank=True)
    headliner = models.BooleanField(default=False)
    sort_order = models.IntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'id']
        unique_together = [('event', 'artist')]


class TicketType(models.Model):
    MEMBER_ACCESS_CHOICES = [('ALL', 'Everyone'), ('MEMBERS_ONLY', 'Members only'), ('NON_MEMBERS', 'Non-members only')]

    id = models.CharField(primary_key=True, max_length=40, default=new_id, editable=False)
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='ticket_types')
    name = models.CharField(max_length=120)
    name_es = models.CharField(max_length=120, blank=True, help_text='Spanish name; blank falls back to the name.')
    description = models.CharField(max_length=300, blank=True)
    description_es = models.CharField(max_length=300, blank=True, help_text='Spanish description; blank falls back.')
    price_cents = models.PositiveIntegerField()
    member_price_cents = models.PositiveIntegerField(null=True, blank=True)
    member_access = models.CharField(max_length=14, choices=MEMBER_ACCESS_CHOICES, default='ALL')
    capacity = models.PositiveIntegerField(null=True, blank=True, help_text='Blank = unlimited')
    sold_elsewhere = models.PositiveIntegerField(
        default=0,
        help_text='Seats already gone through another channel, e.g. a guest promoter selling the same night on '
                  'their own site. Counted against capacity so this checkout cannot oversell the room, and '
                  'counted as taken so the page tells the truth about how full it is.')
    max_per_order = models.PositiveSmallIntegerField(null=True, blank=True, help_text='Blank = 20')
    pay_at_door = models.BooleanField(
        default=False, help_text='Reserve online, pay at the door. No online payment is taken for this type.')
    is_addon = models.BooleanField(
        default=False,
        help_text='Offered as an upsell AFTER the details are filled in, not as a thing to choose first. '
                  'The open mic seat is free; drinks are the sale.')
    active = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'price_cents']

    def __str__(self):
        return f'{self.event.name}: {self.name}'

    def label(self, lang):
        return self.name_es if lang == 'es' and self.name_es else self.name

    def details(self, lang):
        return self.description_es if lang == 'es' and self.description_es else self.description


class SiteFile(models.Model):
    id = models.CharField(primary_key=True, max_length=40, default=new_id, editable=False)
    name = models.CharField(max_length=255, help_text='Brand stems such as site-hero-video are matched by the site.')
    file = models.FileField(upload_to='files/%Y/%m/')
    content_type = models.CharField(max_length=100, blank=True)
    public = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name


class StoreCollection(models.Model):
    id = models.CharField(primary_key=True, max_length=40, default=new_id, editable=False)
    slug = models.SlugField(max_length=120, unique=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    image_url = models.CharField(max_length=500, blank=True, help_text='Absolute URL or /media/... path')
    sort_order = models.IntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'name']

    def __str__(self):
        return self.name


class StoreProduct(models.Model):
    id = models.CharField(primary_key=True, max_length=40, default=new_id, editable=False)
    slug = models.SlugField(max_length=160, unique=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    currency = models.CharField(max_length=3, default='usd')
    collections = models.ManyToManyField(StoreCollection, blank=True, related_name='products')
    external_url = models.URLField(max_length=500, blank=True, help_text='Where "Buy" sends people until on-site merch checkout exists.')
    active = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'name']

    def __str__(self):
        return self.name


class StoreProductImage(models.Model):
    product = models.ForeignKey(StoreProduct, on_delete=models.CASCADE, related_name='images')
    url = models.CharField(max_length=500, help_text='Absolute URL or /media/... path')
    alt = models.CharField(max_length=200, blank=True)
    sort_order = models.IntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'id']


class StoreVariant(models.Model):
    id = models.CharField(primary_key=True, max_length=40, default=new_id, editable=False)
    product = models.ForeignKey(StoreProduct, on_delete=models.CASCADE, related_name='variants')
    name = models.CharField(max_length=120, default='Default')
    sku = models.CharField(max_length=80, blank=True)
    price_cents = models.PositiveIntegerField()
    compare_at_cents = models.PositiveIntegerField(null=True, blank=True)
    available_quantity = models.PositiveIntegerField(null=True, blank=True, help_text='Blank = unlimited')
    sort_order = models.IntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'price_cents']


class MenuCategory(models.Model):
    """A section of the bar menu: beers, cocktails, snacks.

    The menu lives in the database rather than in the site's code so the club can change a price the night it
    changes, without a deploy and without asking anybody.
    """

    id = models.CharField(primary_key=True, max_length=40, default=new_id, editable=False)
    name = models.CharField(max_length=80)
    name_es = models.CharField(max_length=80, blank=True, help_text='Spanish name; blank falls back to the name.')
    active = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'name']
        verbose_name_plural = 'menu categories'

    def __str__(self):
        return self.name

    def label(self, lang):
        return self.name_es if lang == 'es' and self.name_es else self.name


class MenuItem(models.Model):
    id = models.CharField(primary_key=True, max_length=40, default=new_id, editable=False)
    category = models.ForeignKey(MenuCategory, on_delete=models.CASCADE, related_name='items')
    name = models.CharField(max_length=120)
    name_es = models.CharField(max_length=120, blank=True, help_text='Spanish name; blank falls back to the name.')
    description = models.CharField(max_length=300, blank=True)
    description_es = models.CharField(max_length=300, blank=True, help_text='Spanish; blank falls back.')
    price_cents = models.PositiveIntegerField()
    currency = models.CharField(max_length=3, default='mxn')
    # Turned off for the night rather than deleted, so it comes back without being retyped and an old order
    # still names what it was.
    available = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'name']

    def __str__(self):
        return f'{self.name} ({self.price_cents / 100:.2f} {self.currency.upper()})'

    def label(self, lang):
        return self.name_es if lang == 'es' and self.name_es else self.name

    def details(self, lang):
        return self.description_es if lang == 'es' and self.description_es else self.description


class FormEndpoint(models.Model):
    INTENTS = [(i, i) for i in ('show_request', 'contact', 'newsletter', 'external_lead', 'custom')]

    slug = models.SlugField(max_length=80, unique=True)
    intent = models.CharField(max_length=20, choices=INTENTS, default='contact')
    title = models.CharField(max_length=200, blank=True)
    success_message = models.CharField(max_length=300, blank=True, default='Thanks! We will be in touch soon.')
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.slug


class FormSubmission(models.Model):
    endpoint = models.ForeignKey(FormEndpoint, on_delete=models.PROTECT, related_name='submissions')
    email = models.EmailField()
    phone = models.CharField(max_length=40, blank=True)
    fields = models.JSONField(default=dict, blank=True)
    context = models.JSONField(default=dict, blank=True)
    visitor_key = models.CharField(max_length=100, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    handled = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.endpoint.slug}: {self.email}'


class InventoryItem(models.Model):
    """What is behind the bar, counted by the people who are behind the bar.

    Deliberately NOT tied to `MenuItem`. A menu item is what a customer can order; inventory is what runs out,
    and the two are different lists. A bar sells one gin and tonic and loses gin, tonic, limes and ice from
    four different suppliers in four different units, so a model that decrements a drink when it is sold gets
    the arithmetic wrong in a way nobody can correct at 1am. This is a count sheet: the staff say what is
    there, and the number is whatever they last said it was.

    `par` is the level worth reordering at, not a minimum. The list sorts anything at or below it to the top,
    because the only question this page answers in a hurry is what to buy tomorrow.
    """

    BAR = 'bar'
    KITCHEN = 'kitchen'
    SUPPLIES = 'supplies'
    AREAS = [(BAR, 'Barra'), (KITCHEN, 'Cocina'), (SUPPLIES, 'Insumos')]

    # 🚨 One name field, in Spanish, and no `name_es` beside it. The floor console is Spanish only because
    # the floor is: everything else in this project is bilingual because a CUSTOMER reads it, and a staff
    # count sheet has no second audience. A second name column here would only ever be half filled.
    id = models.CharField(primary_key=True, max_length=40, default=new_id, editable=False)
    name = models.CharField(max_length=120, help_text='En español: es lo que ve el personal.')
    area = models.CharField(max_length=20, choices=AREAS, default=BAR)
    unit = models.CharField(max_length=30, blank=True, help_text='bottle, case, kg, each. Free text on purpose.')
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    par = models.DecimalField(max_digits=10, decimal_places=2, default=0,
                              help_text='Reorder at or below this. 0 means never flag it.')
    note = models.CharField(max_length=300, blank=True)
    # Archived rather than deleted, so a count from last month still names what it counted.
    active = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)
    # auto_now, not a default: every write here is somebody recounting, and "when was this last looked at" is
    # the second question the page gets asked. A `default=timezone.now` would freeze at the row's creation.
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['area', 'sort_order', 'name']

    def __str__(self):
        return f'{self.name} ({self.quantity:g} {self.unit})'.replace(' )', ')')

    @property
    def low(self):
        return self.par > 0 and self.quantity <= self.par


class InventoryChange(models.Model):
    """Every adjustment, with who made it.

    A count sheet with no history cannot answer the only question worth asking of one, which is where it went.
    The row keeps the resulting quantity as well as the change, so a later correction does not rewrite what an
    earlier person said they saw.
    """

    id = models.CharField(primary_key=True, max_length=40, default=new_id, editable=False)
    item = models.ForeignKey(InventoryItem, on_delete=models.CASCADE, related_name='changes')
    delta = models.DecimalField(max_digits=10, decimal_places=2)
    quantity_after = models.DecimalField(max_digits=10, decimal_places=2)
    note = models.CharField(max_length=200, blank=True)
    # The name rather than a foreign key: the row has to survive the account being removed, and "who counted
    # this" is a fact about that night, not a live link to a user.
    who = models.CharField(max_length=80, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.item.name} {self.delta:+g} -> {self.quantity_after:g}'


class MenuItemIngredient(models.Model):
    """What one of these takes out of the store room.

    This is the wiring between the menu and the count sheet, and it is a RECIPE rather than an assumption. The
    reason inventory is not simply a column on `MenuItem` is that one gin and tonic consumes gin, tonic, a lime
    and ice, in four units, from four suppliers; a single "stock" number on the drink cannot express that and
    would quietly be wrong. A row here says one true thing: selling one of this takes this much of that.

    🚨 A menu item with no rows here consumes NOTHING, and that is deliberate rather than a gap. A guess is
    worse than a blank: an invented 1:1 between a cocktail and a bottle makes the count sheet drift every night
    and the drift is invisible until somebody counts by hand and finds the numbers lying. `/mesas/carta/` shows
    which items are unlinked so the blank is visible instead of silent.
    """

    id = models.CharField(primary_key=True, max_length=40, default=new_id, editable=False)
    menu_item = models.ForeignKey(MenuItem, on_delete=models.CASCADE, related_name='ingredients')
    inventory_item = models.ForeignKey(InventoryItem, on_delete=models.CASCADE, related_name='used_in')
    # Per ONE sold. Fractions are the normal case: a shot is 0.04 of a bottle, a slice is 0.02 of a kilo.
    quantity = models.DecimalField(max_digits=10, decimal_places=3, default=1)

    class Meta:
        ordering = ['inventory_item__name']
        constraints = [models.UniqueConstraint(fields=['menu_item', 'inventory_item'],
                                               name='one_row_per_ingredient_per_item')]

    def __str__(self):
        return f'{self.menu_item.name}: {self.quantity:g} {self.inventory_item.unit or "x"} {self.inventory_item.name}'


class FloorSettings(models.Model):
    """The handful of numbers about the room itself, editable by the people in it.

    One row, ever. A settings table with a key and a value would have been more general and less readable:
    there is exactly one room, and a named column can carry a comment explaining what the number is for.

    It exists because `TABLES_ON_SHOW` was a constant in the code, so adding a table meant a developer and a
    deploy. A club that is still working out its own layout cannot wait for that, and the bar is the only party
    who knows how many tables are actually out tonight.
    """

    SINGLETON = 1

    id = models.PositiveSmallIntegerField(primary_key=True, default=SINGLETON, editable=False)
    # How many table cards the board draws. NOT a limit on what a customer may type: `menu_views.MAX_TABLE`
    # stays the ceiling for that, because a round sent to a table nobody has added yet should reach the bar and
    # be dealt with, not be refused at the one moment somebody is trying to buy a drink. The board unions in
    # any table that has a round, so an unexpected number still appears.
    tables = models.PositiveSmallIntegerField(default=12, help_text='Cuántas mesas hay en el salón.')
    # What each spot is called, keyed by its number: {"3": "Box 1"}. Not every seat in this room is a table,
    # and a board that insists on calling a box "Mesa 3" makes the staff translate in their heads every time.
    # The NUMBER still routes the drink, so a renamed spot keeps working for the QR and for the customer.
    labels = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.CharField(max_length=80, blank=True)

    class Meta:
        verbose_name = 'floor settings'
        verbose_name_plural = 'floor settings'

    def __str__(self):
        return f'{self.tables} tables'

    def save(self, *args, **kwargs):
        self.id = self.SINGLETON
        return super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        """The row, created on first use. Never raises, because the board must draw even on a fresh database."""
        row, _ = cls.objects.get_or_create(pk=cls.SINGLETON)
        return row


class SiteVideo(models.Model):
    """A video uploaded under "For the site" on /upload/, managed on /videos/ (api/videos_views.py).

    The original stays where the upload put it (`source`, in CHAT_FILES_DIR/upload, where the /chat/ agent can read
    it). `process_videos` makes a web copy beside a poster frame in SITE_VIDEOS_DIR: an iPhone .MOV is usually
    HEVC, which Chrome on most computers will not play, so nothing is shown from the original. The web copy's name
    carries a random token, so a video that is not shown on the site has no address anyone can guess.
    """
    PENDING, PROCESSING, READY, FAILED = 'pending', 'processing', 'ready', 'failed'
    STATUS_CHOICES = [(PENDING, 'Waiting'), (PROCESSING, 'Processing'), (READY, 'Ready'), (FAILED, 'Failed')]

    id = models.CharField(primary_key=True, max_length=40, default=new_id, editable=False)
    source = models.CharField(max_length=500, help_text='The original upload, on the server.')
    original_name = models.CharField(max_length=200, blank=True)
    title = models.CharField(max_length=160, blank=True)
    title_es = models.CharField(max_length=160, blank=True)
    published = models.BooleanField(default=False, help_text='Shown on the Videos page of the site.')
    position = models.IntegerField(default=0, help_text='Lower comes first on the site.')
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=PENDING, db_index=True)
    error = models.TextField(blank=True)
    web_file = models.CharField(max_length=200, blank=True)
    poster_file = models.CharField(max_length=200, blank=True)
    duration = models.FloatField(null=True, blank=True)
    trim_start = models.FloatField(null=True, blank=True)
    trim_end = models.FloatField(null=True, blank=True)
    size = models.BigIntegerField(default=0)
    # What it is: an upload, a clip the AI cut from one (short or long), or a version the AI edited on request.
    UPLOAD, SHORT, LONG, EDIT = 'upload', 'short', 'long', 'edit'
    KIND_CHOICES = [(UPLOAD, 'Upload'), (SHORT, 'Short clip'), (LONG, 'Long clip'), (EDIT, 'AI edit')]
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default=UPLOAD, db_default=UPLOAD, db_index=True)
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='children',
                               help_text='The video this clip or edit was made from.')
    # db_default on both: between `migrate` and the reload, the old code still inserts rows without these columns.
    comedian = models.CharField(max_length=120, blank=True, default='', db_default='', db_index=True)
    # This video's own conversation with the /chat/ agent ("edit by instruction" on /videos/).
    conversation = models.ForeignKey('assistant.Conversation', null=True, blank=True, on_delete=models.SET_NULL,
                                     related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['position', '-created_at']

    def __str__(self):
        return self.title or self.original_name or self.id

    def label(self, lang):
        if lang == 'es' and self.title_es:
            return self.title_es
        return self.title or self.title_es or ''


class ClipJob(models.Model):
    """The AI clip finder run on one uploaded show (catalog/clips.py): transcribe, find the laughs, let Claude pick
    the short and long clips and tell the comedians apart, then cut them. Started from /videos/."""
    QUEUED, RUNNING, DONE, FAILED = 'queued', 'running', 'done', 'failed'
    STATUS_CHOICES = [(QUEUED, 'Queued'), (RUNNING, 'Running'), (DONE, 'Done'), (FAILED, 'Failed')]

    video = models.ForeignKey(SiteVideo, on_delete=models.CASCADE, related_name='clip_jobs')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=QUEUED, db_index=True)
    step = models.CharField(max_length=200, blank=True)
    error = models.TextField(blank=True)
    summary = models.TextField(blank=True, help_text="Claude's notes on the show: who was on, what landed.")
    clips_made = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
