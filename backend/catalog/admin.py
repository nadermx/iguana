from django.contrib import admin
from django.utils.html import format_html

from .models import (SiteVideo, Artist, Event, FormEndpoint, FormSubmission, InventoryChange, InventoryItem,
                     LineupEntry, MenuCategory, MenuItem, MenuItemIngredient, SiteFile,
                     StoreCollection, StoreProduct,
                     StoreProductImage, StoreVariant, TicketType, Tour, Venue)


def thumb(url):
    return format_html('<img src="{}" style="height:40px;border-radius:6px">', url) if url else ''


@admin.register(Venue)
class VenueAdmin(admin.ModelAdmin):
    list_display = ('name', 'city', 'country', 'capacity', 'listed')
    list_filter = ('city', 'listed')
    search_fields = ('name', 'city', 'address')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Artist)
class ArtistAdmin(admin.ModelAdmin):
    list_display = ('photo', 'name', 'home_city', 'listed', 'sort_order')
    list_display_links = ('photo', 'name')
    list_editable = ('listed', 'sort_order')
    search_fields = ('name', 'stage_name', 'home_city')
    prepopulated_fields = {'slug': ('name',)}

    @admin.display(description='')
    def photo(self, obj):
        return thumb(obj.image_url)


class TicketTypeInline(admin.TabularInline):
    model = TicketType
    extra = 0
    fields = ('name', 'description', 'price_cents', 'member_price_cents', 'member_access', 'capacity',
              'sold_elsewhere', 'max_per_order', 'pay_at_door', 'active', 'sort_order')


class LineupInline(admin.TabularInline):
    model = LineupEntry
    extra = 0
    autocomplete_fields = ('artist',)


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ('poster', 'name', 'date', 'venue_name', 'status', 'visibility', 'ticketing_type')
    list_display_links = ('poster', 'name')
    list_filter = ('status', 'visibility', 'ticketing_type', 'venue__city')
    search_fields = ('name', 'slug', 'venue__name', 'venue_label')
    date_hierarchy = 'date'
    prepopulated_fields = {'slug': ('name',)}
    autocomplete_fields = ('venue',)
    inlines = [TicketTypeInline, LineupInline]
    fieldsets = (
        (None, {'fields': ('name', 'name_es', 'slug', 'status', 'visibility', 'date', 'doors_open', 'show_time', 'end_time', 'venue', 'venue_label')}),
        ('Listing', {'fields': ('description', 'description_es', 'long_description', 'long_description_es', 'image_url',
                                'image_url_mobile', 'image_url_es', 'image_url_mobile_es', 'language', 'age_restriction',
                                'tags', 'reviews', 'tour')}),
        # `members_eligible` is deliberately absent: there is no membership to be eligible for, and a checkbox
        # that promises member pricing is a promise the checkout cannot keep.
        ('Ticketing', {'fields': ('ticketing_type', 'external_ticket_url', 'currency')}),
    )

    @admin.display(description='')
    def poster(self, obj):
        return thumb(obj.image_url)

    @admin.display(description='Venue')
    def venue_name(self, obj):
        return obj.venue.name if obj.venue else obj.venue_label


admin.site.register(Tour)


@admin.register(SiteFile)
class SiteFileAdmin(admin.ModelAdmin):
    list_display = ('name', 'content_type', 'public', 'created_at')


class StoreImageInline(admin.TabularInline):
    model = StoreProductImage
    extra = 0


class StoreVariantInline(admin.TabularInline):
    model = StoreVariant
    extra = 0


@admin.register(StoreProduct)
class StoreProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'currency', 'active', 'sort_order')
    list_editable = ('active', 'sort_order')
    prepopulated_fields = {'slug': ('name',)}
    filter_horizontal = ('collections',)
    inlines = [StoreVariantInline, StoreImageInline]


@admin.register(StoreCollection)
class StoreCollectionAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'sort_order')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(FormEndpoint)
class FormEndpointAdmin(admin.ModelAdmin):
    list_display = ('slug', 'intent', 'title', 'active')


@admin.register(FormSubmission)
class FormSubmissionAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'endpoint', 'email', 'phone', 'handled')
    list_filter = ('endpoint', 'handled')
    list_editable = ('handled',)
    search_fields = ('email', 'phone')
    readonly_fields = ('endpoint', 'email', 'phone', 'fields', 'context', 'visitor_key', 'ip', 'created_at')


class MenuItemInline(admin.TabularInline):
    model = MenuItem
    extra = 1
    fields = ('name', 'name_es', 'description', 'description_es', 'price_cents', 'currency', 'available', 'sort_order')


@admin.register(MenuCategory)
class MenuCategoryAdmin(admin.ModelAdmin):
    """Where the club edits the bar menu. Prices change on the night, so this is the point of keeping the menu
    in the database instead of in the site's code."""

    list_display = ('name', 'name_es', 'active', 'sort_order', 'how_many')
    list_editable = ('active', 'sort_order')
    inlines = [MenuItemInline]

    @admin.display(description='items')
    def how_many(self, obj):
        return obj.items.filter(available=True).count()


class IngredientInline(admin.TabularInline):
    """What one of these takes out of the store room. The bar sets these at /mesas/carta/; this mirrors it."""

    model = MenuItemIngredient
    extra = 1
    autocomplete_fields = ('inventory_item',)


@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = ('name', 'name_es', 'category', 'price_cents', 'currency', 'available', 'recipe',
                    'sort_order')
    list_editable = ('price_cents', 'available', 'sort_order')
    list_filter = ('category', 'available')
    search_fields = ('name', 'name_es')
    inlines = [IngredientInline]

    @admin.display(description='consumes', boolean=True)
    def recipe(self, obj):
        """Visible in the list, because an item with no recipe silently consumes nothing when it sells."""
        return obj.ingredients.exists()


@admin.register(InventoryItem)
class InventoryItemAdmin(admin.ModelAdmin):
    """The owner's view of the count sheet. The floor keeps it at /mesas/inventario/; this is for corrections."""

    list_display = ('name', 'area', 'quantity', 'unit', 'par', 'low', 'active', 'updated_at')
    list_filter = ('area', 'active')
    # search_fields is also what makes the recipe inline's autocomplete work on MenuItem.
    search_fields = ('name', 'note')
    list_editable = ('quantity', 'par', 'active')


@admin.register(InventoryChange)
class InventoryChangeAdmin(admin.ModelAdmin):
    """Read only on purpose: it is the audit trail, and an editable audit trail is not one."""

    list_display = ('created_at', 'item', 'delta', 'quantity_after', 'who', 'note')
    list_filter = ('item__area',)
    search_fields = ('item__name', 'who', 'note')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(SiteVideo)
class SiteVideoAdmin(admin.ModelAdmin):
    """Managed on /videos/ (watch, trim, show on the site); the admin is for looking things up."""
    list_display = ('__str__', 'status', 'published', 'position', 'created_at')
    list_filter = ('status', 'published')
    readonly_fields = ('source', 'original_name', 'web_file', 'poster_file', 'duration', 'size', 'error')
