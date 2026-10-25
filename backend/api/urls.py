from django.views.generic import RedirectView
from django.urls import path, re_path

from . import (carta_views, chat_views, comic_views, door_views, drop_views, embed_views, fan_views, floor_views, inventory_views,
               menu_views, pay_views, public_views, reservations_views, revenue_views, stats_views,
               tables_views)

urlpatterns = [
    # Public catalogue (@kintana/sdk KintanaClient)
    path('api/public/v1/events', public_views.events),
    path('api/public/v1/events/<str:key>', public_views.event_detail),
    path('api/public/v1/artists', public_views.artists),
    path('api/public/v1/artists/<str:key>', public_views.artist_detail),
    path('api/public/v1/venues', public_views.venues),
    path('api/public/v1/venues/<str:key>', public_views.venue_detail),
    path('api/public/v1/endpoints', public_views.endpoints),
    path('api/public/v1/endpoints/<str:slug>/submit', public_views.endpoint_submit),
    path('api/public/v1/forms', public_views.forms),
    path('api/public/v1/files', public_views.files),
    path('api/public/v1/store/products', public_views.store_products),
    path('api/public/v1/store/products/<str:key>', public_views.store_product_detail),
    path('api/public/v1/store/collections', public_views.store_collections),
    path('api/public/v1/store/collections/<str:key>', public_views.store_collection_detail),
    # The bar menu, and a round ordered from a table. One path for both languages, because a printed QR can
    # never be re-printed with a different URL: the page picks its own language.
    # Staff, on the API domain so it shares the admin session rather than inventing a login.
    path('revenue/', revenue_views.revenue),
    path('reservations/', reservations_views.reservations, name='reservations'),
    path('stats/', stats_views.stats, name='stats'),
    # The owner's chat with the Claude Code instance that runs the site (docs/chat-agent.md). Superusers only.
    path('chat/', chat_views.chat, name='chat'),
    path('chat/send/', chat_views.send, name='chat-send'),
    path('chat/<int:conversation_id>/turns/', chat_views.turns, name='chat-turns'),
    path('chat/turn/<int:turn_id>/stop/', chat_views.stop, name='chat-stop'),
    # The bar board and the old console pages moved to the point of sale (pos/) on 2026-09-28.
    path('tables/', RedirectView.as_view(url='/pos/'), name='tables'),
    # The floor console. Spanish only, its own login, and no admin behind it: see `api/floor.py`.
    path('mesas/', RedirectView.as_view(url='/pos/'), name='mesas'),
    path('mesas/entrar/', floor_views.sign_in, name='floor-sign-in'),
    path('mesas/salir/', floor_views.sign_out, name='floor-sign-out'),
    path('mesas/inventario/', RedirectView.as_view(url='/pos/inventario/'), name='floor-inventory'),
    path('mesas/inventario/agregar/', inventory_views.add_item, name='floor-inventory-add'),
    path('mesas/inventario/<str:item_id>/ajustar/', inventory_views.adjust, name='floor-inventory-adjust'),
    path('mesas/inventario/<str:item_id>/editar/', inventory_views.edit_item, name='floor-inventory-edit'),
    path('mesas/carta/', RedirectView.as_view(url='/pos/productos/'), name='floor-carta'),
    path('mesas/carta/agregar/', carta_views.add_menu_item, name='floor-carta-add'),
    path('mesas/carta/<str:item_id>/guardar/', carta_views.save_item, name='floor-carta-save'),
    path('mesas/carta/<str:item_id>/cambiar/', carta_views.toggle_item, name='floor-carta-toggle'),
    path('mesas/carta/<str:item_id>/receta/', carta_views.link_ingredient, name='floor-carta-recipe'),
    path('mesas/carta/receta/<str:pk>/quitar/', carta_views.unlink_ingredient, name='floor-carta-unrecipe'),
    # The address the door is given (owner, 2026-09-29): short enough to type on a phone, and any staff PIN opens
    # it. /mesas/puerta/ stays for the tablets that already have it bookmarked.
    path('scan/', door_views.door, name='floor-scan'),
    path('drop/', drop_views.drop, name='drop'),
    # Comedians send their photo, clips and the dates they want (api/comic_views.py).
    path('comic/', comic_views.comic, name='comic'),
    path('comic/thanks/', comic_views.thanks, name='comic-thanks'),
    path('mesas/puerta/', door_views.door, name='floor-door'),
    path('mesas/puerta/verificar/', door_views.verify, name='floor-door-verify'),
    path('mesas/puerta/deshacer/', door_views.undo, name='floor-door-undo'),
    path('mesas/puerta/buscar/', door_views.lookup, name='floor-door-lookup'),
    # The guest list, which is the DOOR list: same view, Spanish, and reached without the admin.
    # /reservas/ is the address staff are given (owner, 2026-09-30); /mesas/reservas/ stays for bookmarks.
    path('reservas/', reservations_views.reservations, name='floor-reservas'),
    path('reservas/<str:order_id>/verificar/', reservations_views.check_in_order, name='floor-reservas-check-in'),
    path('mesas/reservas/', reservations_views.reservations, name='floor-reservations'),
    path('mesas/reservas/<str:order_id>/verificar/', reservations_views.check_in_order, name='floor-check-in'),
    # La cuenta de la mesa, pagada desde el teléfono del cliente. Una sola ruta para los dos idiomas: el QR
    # es el mismo papel y la página sigue al teléfono.
    path('mesa/pagar/<str:token>/', pay_views.pay_page, name='table-pay'),
    path('mesa/pagar/<str:token>/intent/', pay_views.pay_intent, name='table-pay-intent'),
    path('mesa/pagar/<str:token>/confirmar/', pay_views.pay_confirm, name='table-pay-confirm'),
    path('mesa/pagar/<str:token>/listo/', pay_views.pay_done, name='table-pay-done'),
    path('tables/<int:number>/close/', tables_views.close_table, name='close-table'),
    path('tables/<int:number>/settle/', tables_views.settle_table, name='settle-table'),
    path('tables/<int:number>/linea/<str:item_id>/quitar/', tables_views.void_item, name='void-item'),
    path('tables/<int:number>/cerrar/', tables_views.close_out, name='close-out'),
    path('tables/<int:number>/nombre/', tables_views.name_table, name='name-table'),
    path('tables/cuantas/', tables_views.set_tables, name='set-tables'),
    path('mesas/mesa/<int:number>/agregar/', tables_views.add_round, name='floor-add-round'),
    path('mesas/estado/', tables_views.board_state, name='floor-board-state'),
    path('api/public/v1/menu', menu_views.menu),
    path('api/public/v1/table-orders', menu_views.table_order),
    path('api/public/v1/site', public_views.site),
    path('api/public/v1/site/manifest', public_views.site_manifest),
    # Fans
    path('api/fan/v1/config', fan_views.config),
    path('api/fan/v1/auth/request', fan_views.auth_request),
    path('api/fan/v1/auth/verify', fan_views.auth_verify),
    path('api/fan/v1/account/profile', fan_views.account_profile),
    path('api/fan/v1/events', fan_views.fan_events),
    path('api/fan/v1/events/<str:slug>', fan_views.fan_event_detail),
    path('api/fan/v1/tickets', fan_views.tickets),
    path('api/fan/v1/tickets/<str:order_id>', fan_views.ticket_detail),
    path('api/fan/v1/membership/plans', fan_views.membership_plans),
    path('api/fan/v1/membership/status', fan_views.membership_status),
    path('api/fan/v1/membership/redeem-code', fan_views.redeem_code),
    path('api/fan/v1/membership/credits/transfer', fan_views.credits_transfer),
    path('api/fan/v1/membership/credits/transfers', fan_views.credits_transfers),
    path('api/fan/v1/membership/subscribe', fan_views.membership_subscribe),
    path('api/fan/v1/membership/oneoff', fan_views.membership_oneoff),
    path('api/fan/v1/membership/billing-portal', fan_views.billing_portal),
    # Checkout widget, tracker, tickets
    path('_t/k.js', embed_views.tracker_js),
    path('embed/event/<str:key>', embed_views.event_checkout),
    path('unsubscribe/<str:token>', embed_views.unsubscribe),
    path('newsletter/confirm/<str:token>', embed_views.newsletter_confirm),
    path('unsubscribe/<str:token>/', embed_views.unsubscribe),
    path('api/checkout/<str:event_id>/quote', embed_views.checkout_quote),
    path('api/checkout/<str:event_id>/start', embed_views.checkout_start),
    path('api/checkout/<str:event_id>/engaged', embed_views.checkout_engaged),
    path('api/checkout/orders/<str:order_id>/confirm', embed_views.checkout_confirm),
    path('orders/<str:token>/', embed_views.order_page),
    path('orders/<str:token>/release/', embed_views.release_seat, name='release-seat'),
    path('checkin/<str:token>/', embed_views.checkin, name='checkin'),
    path('api/stripe/webhook', embed_views.stripe_webhook),
    re_path(r'^api/ingest/(?P<kind>pageview|event|identify)$', embed_views.ingest),
]
