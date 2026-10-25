"""English and Spanish for everything a customer sees from the backend: checkout, order page, emails and errors.

The English text is both the key and the fallback. `api.tests.TranslationTests` scans the code for every string that
goes through `tr()`, `{% t %}` or `CheckoutError(...)` and fails when one has no Spanish here, or when a Spanish entry
drops or adds a slot, so a customer-facing string cannot ship untranslated. Slots are positional (`{0}`) so a Spanish
sentence can reorder them.
"""

from urllib.parse import urlparse

ES = {
    # Checkout
    'Tickets': 'Boletos',
    'Tickets · {0}': 'Boletos · {0}',
    'Checkout needs JavaScript enabled.': 'Para comprar necesitas activar JavaScript.',
    'Member pricing applied.': 'Se aplicó el precio de socio.',
    'Full name': 'Nombre completo',
    'Email': 'Correo electrónico',
    'Phone (optional)': 'Teléfono (opcional)',
    'Choose how many with +': 'Elige cuántos con +',
    'Up to {0} per order': 'Máximo {0} por orden',
    'Reserve 1 seat': 'Reservar 1 lugar',
    'Reserve {0} seats': 'Reservar {0} lugares',
    'Pay {0} at the door': 'Pagas {0} en la puerta',
    'Free': 'Gratis',
    'Get 1 ticket': 'Obtener 1 boleto',
    'Get {0} tickets': 'Obtener {0} boletos',
    'Pay {0}': 'Pagar {0}',
    '1 ticket': '1 boleto',
    '{0} tickets': '{0} boletos',
    'Reserving...': 'Reservando...',
    'Processing...': 'Procesando...',
    'The total is now {0}. Press the button again to pay it.':
        'El total ahora es {0}. Vuelve a presionar el botón para pagarlo.',
    'Tickets are not on sale for this show.': 'Los boletos para este show no están a la venta.',
    'Local development: Stripe keys are not configured, so this button simulates a successful payment.':
        'Desarrollo local: Stripe no está configurado, así que este botón simula un pago exitoso.',
    'Sold out': 'Agotado',
    'pay at the door': 'pagas en la puerta',
    'members only': 'solo socios',
    '{0} left': 'quedan {0}',
    'Add one {0}': 'Agregar uno: {0}',
    'Remove one {0}': 'Quitar uno: {0}',
    'Member benefit ({0} free)': 'Beneficio de socio ({0} gratis)',
    'Discount': 'Descuento',
    'Member discount': 'Descuento de socio',
    'Something went wrong.': 'Algo salió mal.',

    # Checkout errors
    'Invalid request': 'Solicitud no válida.',
    'Invalid ticket selection': 'La selección de boletos no es válida.',
    'Enter your name and email.': 'Escribe tu nombre y tu correo electrónico.',
    'Online payment is not available yet. Please contact us to book.':
        'El pago en línea aún no está disponible. Contáctanos para reservar.',
    'Payment has not completed yet.': 'El pago aún no se ha completado.',
    'That ticket type is no longer available.': 'Ese tipo de boleto ya no está disponible.',
    'Choose between 0 and 20 tickets.': 'Elige entre 0 y 20 boletos.',
    'You can book up to {0} {1} per order.': 'Puedes reservar hasta {0} de «{1}» por orden.',
    '{0} is for members only.': '«{0}» es solo para socios.',
    '{0} is not available to members.': '«{0}» no está disponible para socios.',
    'Only {0} {1} tickets left.': 'Solo quedan {0} de «{1}».',
    '{0} is sold out.': '«{0}» está agotado.',
    'Choose at least one ticket.': 'Elige al menos un boleto.',
    'Reserve pay-at-the-door seats in their own order.': 'Reserva los lugares que se pagan en la puerta en una orden aparte.',
    'Only {0} {1} left.': 'Solo quedan {0} de «{1}».',
    '{0} is fully booked.': '«{0}» ya está lleno.',
    'You already have a reservation for this night. Check your email for your seats.':
        'Ya tienes una reservación para esta noche. Revisa tu correo para ver tus lugares.',
    'Too many reservations from this connection. Write to hello@iguanacomedy.com and we will hold your seats.':
        'Demasiadas reservaciones desde esta conexión. Escríbenos a hello@iguanacomedy.com y te apartamos tus lugares.',

    # Order page
    'Your tickets': 'Tus boletos',
    'Your seats': 'Tus lugares',
    'Your tickets · {0}': 'Tus boletos · {0}',
    'doors {0}': 'puertas {0}',
    'show {0}': 'show {0}',
    'This order is {0}. Tickets appear here once payment completes.':
        'Esta orden está {0}. Los boletos aparecen aquí cuando se complete el pago.',
    'Booked by {0}. Show the code for each ticket at the door.':
        'Reservado por {0}. Muestra el código de cada boleto en la puerta.',
    'Pay {0} at the door.': 'Paga {0} en la puerta.',
    'Your seats are reserved. Nothing was charged online.': 'Tus lugares están reservados. No se cobró nada en línea.',
    'Ticket {0} of {1}': 'Boleto {0} de {1}',
    'Checked in': 'Registrado',
    'Check-in code': 'Código de registro',
    'Back to Iguana Comedy': 'Volver a Iguana Comedy',
    'pending': 'pendiente',
    'completed': 'completada',
    'refunded': 'reembolsada',
    'cancelled': 'cancelada',

    # Confirmation email
    'Hi {0},': 'Hola, {0}:',
    'Hi there,': 'Hola:',
    'You are booked for {0} on {1}.': 'Tu lugar para {0} el {1} está confirmado.',
    'You are booked for {0}.': 'Tu lugar para {0} está confirmado.',
    'Doors {0} · Show {1}': 'Puertas {0} · Show {1}',
    'Show {0}': 'Show {0}',
    'Venue: {0}': 'Lugar: {0}',
    'Pay {0} at the door for your seat. Nothing was charged online.':
        'Paga {0} en la puerta por tu lugar. No se cobró nada en línea.',
    'Pay {0} at the door for your {1} seats. Nothing was charged online.':
        'Paga {0} en la puerta por tus {1} lugares. No se cobró nada en línea.',
    'Your seats (show this at the door): {0}': 'Tus lugares (muéstralo en la puerta): {0}',
    'Your tickets (show this at the door): {0}': 'Tus boletos (muéstralo en la puerta): {0}',
    'See you there,': '¡Nos vemos ahí!',
    'Your reservation: {0}': 'Tu reservación: {0}',
    'Your tickets: {0}': 'Tus boletos: {0}',

    # Sign-in email
    'Sign in to Iguana Comedy:': 'Inicia sesión en Iguana Comedy:',
    'Or enter this code: {0}': 'O escribe este código: {0}',
    'The link and code expire in 30 minutes. If you did not ask for this, ignore this email.':
        'El enlace y el código vencen en 30 minutos. Si no lo pediste, ignora este correo.',
    'Your Iguana Comedy sign-in code: {0}': 'Tu código para iniciar sesión en Iguana Comedy: {0}',

    # API errors the site shows as-is (translated by api.middleware.TranslateErrorsMiddleware)
    'A valid email is required': 'Se requiere un correo electrónico válido.',
    'Billing is not available for this account': 'La facturación no está disponible para esta cuenta.',
    'Body must be a JSON object': 'La solicitud no es válida.',
    'Enter a valid email address': 'Escribe un correo electrónico válido.',
    'Enter an amount and a different recipient email': 'Escribe un monto y el correo de otra persona.',
    'Invalid or missing token': 'La clave de acceso no es válida o falta.',
    'Method not allowed': 'Método no permitido.',
    'Not enough credit for that transfer': 'No tienes suficiente crédito para esa transferencia.',
    'Not found': 'No encontrado.',
    'Provide the link token, or your email and code': 'Usa el enlace, o escribe tu correo y el código.',
    'Sign in required': 'Necesitas iniciar sesión.',
    'That billing interval is not offered for this plan': 'Ese periodo de facturación no está disponible para este plan.',
    'That code is invalid or has already been used.': 'Ese código no es válido o ya se usó.',
    'That option is not offered for this plan': 'Esa opción no está disponible para este plan.',
    'That sign-in link or code is invalid or has expired.': 'Ese enlace o código no es válido o ya venció.',
    'Too many sign-in emails. Try again in a few minutes.':
        'Demasiados correos para iniciar sesión. Intenta de nuevo en unos minutos.',
    'Unknown form': 'Formulario desconocido.',
    'Unknown plan or interval': 'Plan o periodo desconocido.',
    'Unknown plan or kind': 'Plan o tipo desconocido.',
    'amountCents must be a whole number': 'El monto debe ser un número entero.',
    'redirectUrl is not an allowed site URL': 'La dirección de regreso no es un sitio permitido.',
    'returnUrl is not an allowed site URL': 'La dirección de regreso no es un sitio permitido.',

    # Door check-in (staff; language follows the phone's browser)
    'Check-in': 'Registro',
    'Door check-in': 'Registro en la puerta',
    'Order is {0}. Do not admit.': 'La orden está {0}. No dejar pasar.',
    'Checked in. Enjoy the show.': 'Registrado. Disfruta el show.',
    'Already checked in at {0}.': 'Ya se registró a las {0}.',
    'Reserved, not paid: collect {0} for this seat, then check in.':
        'Reservado sin pagar: cobra {0} por este lugar y después registra.',
    'Check in': 'Registrar',
    # Unsubscribe page and the footer line on bulk email.
    'Email preferences': 'Preferencias de correo',
    'That link is not valid': 'Ese enlace no es válido',
    'Write to hello@iguanacomedy.com and we will take you off the list by hand.':
        'Escríbenos a hello@iguanacomedy.com y te sacamos de la lista a mano.',
    'You are on the list': 'Estás en la lista',
    'We email {0} when new shows go on sale.': 'Escribimos a {0} cuando salen shows nuevos a la venta.',
    'Unsubscribe': 'Cancelar suscripción',
    'You are unsubscribed': 'Cancelaste tu suscripción',
    'We will not email {0} about new shows again. Tickets you already bought are not affected.':
        'No volveremos a escribir a {0} sobre shows nuevos. Los boletos que ya compraste no se ven afectados.',
    'Changed your mind? Resubscribe': '¿Cambiaste de opinión? Vuelve a suscribirte',
    'You are receiving this because you signed up at iguanacomedy.com.':
        'Recibes esto porque te suscribiste en iguanacomedy.com.',
    'Unsubscribe: {0}': 'Cancelar suscripción: {0}',
    # Weekly what-is-on email (crm/whats_on.py)
    'This week at Iguana Comedy, Playa del Carmen:': 'Esta semana en Iguana Comedy, Playa del Carmen:',
    'This week at Iguana Comedy: {0}': 'Esta semana en Iguana Comedy: {0}',
    'This week at Iguana Comedy: open mic Tuesday and Wednesday':
        'Esta semana en Iguana Comedy: open mic martes y miércoles',
    'Sign-up list {0}, show {1}. Free entry.': 'Lista {0}, show {1}. Entrada gratis.',
    'Doors {0}, show {1}. Free entry.': 'Puertas {0}, show {1}. Entrada gratis.',
    'Hold your seat for {0}, a free drink included: {1}':
        'Aparta tu lugar por {0}, incluye una bebida gratis: {1}',
    # The share link somebody sends after booking, and the morning-after note.
    'I am going to see {0} at Iguana Comedy. Tickets here: {1}':
        'Voy a ver a {0} en Iguana Comedy. Boletos aquí: {1}',
    'Shows here sell out. Send this to whoever you want to bring and they can get their own ticket.':
        'Los shows aquí se llenan. Manda esto a quien quieras traer y puede sacar su propio boleto.',
    # The staff reservations board: how many we have for each night, and who they are.
    # The spend-against-bookings page.
    'The room, night by night': 'La sala, noche por noche',
    'Today, from visit to booking': 'Hoy, de la visita a la reservación',
    'visits': 'visitas',
    'started booking': 'empezaron a reservar',
    'booked': 'reservaron',
    'Over seven days: {0} visits, {1} started, {2} booked.':
        'En siete días: {0} visitas, {1} empezaron, {2} reservaron.',
    'Everything else': 'Lo demás',
    'Where the bookings came from, last 7 days': 'De dónde vinieron las reservaciones, últimos 7 días',
    'No ad click': 'Sin clic en anuncio',
    '{0} paid': '{0} pagados',
    'not connected yet': 'aún no conectado',
    "A booking counts for the platform whose ad link it arrived through. Cost per seat is that platform's spend over our own seats.":
        'Una reservación cuenta para la plataforma por cuyo anuncio llegó. El costo por lugar es el gasto de esa plataforma entre nuestros lugares.',
    '{0} people on the mailing list, {1} joined this week.':
        '{0} personas en la lista de correo, {1} se sumaron esta semana.',
    '{0} table(s) open at the bar, {1} owed': '{0} mesa(s) abiertas en la barra, {1} por cobrar',
    'The ads, campaign by campaign': 'Los anuncios, campaña por campaña',
    'Campaign': 'Campaña',
    'Spend': 'Gasto',
    'People': 'Personas',
    'Times each': 'Veces c/u',
    'Clicks': 'Clics',
    'free seats': 'lugares gratis',
    'tickets': 'boletos',
    'Nothing spent this week.': 'Nada gastado esta semana.',
    'Seven days. People is how many saw it at all; times each is how often the same person saw it, which is why it is never added up across days.':
        'Siete días. Personas es cuántas lo vieron; veces c/u es cuántas veces lo vio la misma persona, y por eso nunca se suma entre días.',
    'The target is {0} or under.': 'La meta es {0} o menos.',
    'Anything above it is being shown to the same people again, and the budget is buying repetition rather than new faces.':
        'Todo lo que esté por encima se le está mostrando otra vez a las mismas personas, y el presupuesto compra repetición en lugar de caras nuevas.',
    'Today so far:': 'Hoy hasta ahora:',
    'people': 'personas',
    'Stats': 'Números',
    'Spend from Meta, {0} ago': 'Gasto según Meta, hace {0}',
    'No spend figures yet': 'Todavía no hay cifras de gasto',
    'These spend figures are not fresh. The snapshot cron has not written in a while, so treat the cost per seat as the last known one.':
        'Estas cifras de gasto no están frescas. El cron no ha escrito en un rato, así que toma el costo por lugar como el último conocido.',
    'Today so far': 'Hoy hasta ahora',
    'Yesterday': 'Ayer',
    'Last 7 days': 'Últimos 7 días',
    '{0} spent': '{0} gastados',
    'The day is {0}% through. Spend runs from midnight while bookings arrive in the evening, so this reads high in the afternoon.':
        'Va {0}% del día. El gasto corre desde medianoche y las reservaciones llegan de noche, así que por la tarde se ve alto.',
    'Free reservations': 'Reservaciones gratis',
    'Paid tickets': 'Boletos pagados',
    'seat': 'lugar',
    'no seats yet': 'sin lugares todavía',
    'Ad spend': 'Gasto en anuncios',
    'Bookings': 'Reservaciones',
    'Per booking': 'Por reservación',
    'Taken': 'Cobrado',
    'Return': 'Retorno',
    'Ads as share': 'Anuncios como parte',
    'Bookings and seats are our own rows, counted now. Spend is Meta\'s, from the snapshot. Cost per seat is their spend over our seats, never over their purchase count: today they report {0} purchases against the {1} bookings we actually hold.':
        'Las reservaciones y los lugares son nuestros propios registros, contados ahora. El gasto es de Meta, del snapshot. El costo por lugar es su gasto entre nuestros lugares, nunca entre su conteo de compras: hoy reportan {0} compras contra las {1} reservaciones que realmente tenemos.',
    # The bar board's running tab: what this table owes for the night, not just what is waiting.
    'Mark paid': 'Marcar pagado',
    'Paid': 'Pagado',
    'Undo': 'Deshacer',
    'Not paid after all': 'No pagó después de todo',
    '1 round tonight': '1 ronda esta noche',
    '1 round · {0} drinks': '1 ronda · {0} bebidas',
    '{0} rounds tonight': '{0} rondas esta noche',
    '{0} taken': '{0} cobrados',
    '{0} still owed': '{0} por cobrar',
    'The bar, night by night': 'La barra, noche por noche',
    '{0} rounds · {1} drinks': '{0} rondas · {1} bebidas',
    'nothing yet': 'nada todavía',
    'Waiting now': 'Pendientes ahora',
    '{0} min': '{0} min',
    'See breakdown': 'Ver desglose',
    'Hide breakdown': 'Ocultar desglose',
    'Waiting': 'Pendiente',
    'Delivered at the table': 'Entregado en la mesa',
    'Paid for': 'Pagado',
    'Over half reserved, worth booking early': 'Más de la mitad reservada, mejor reserva pronto',
    # Quitar una línea de la cuenta. Los dos motivos no son el mismo hecho para el inventario.
    'no seats to sell': 'no hay lugares que vender',
    'Ticket': 'Boleto',
    'At the door': 'En la puerta',
    'Verified': 'Verificado',
    'Undo': 'Deshacer',
    'What this spot is called': 'Cómo se llama este lugar',
    'Clear the table': 'Liberar la mesa',
    'Add a round': 'Apuntar una ronda',
    'Tables in the room': 'Cuántas mesas hay',
    'One table fewer': 'Una mesa menos',
    'One table more': 'Una mesa más',
    'Save': 'Guardar',
    'Take it off': 'Quitar de la cuenta',
    'What happened (optional)': 'Qué pasó (opcional)',
    'Not made, back in stock': 'No se preparó, regresa al inventario',
    'Made and thrown away': 'Se preparó y se tiró',
    'Due': 'Por cobrar',
    '{0} rounds': '{0} rondas',
    'Nothing waiting': 'Nada pendiente',
    'Reservations': 'Reservaciones',
    '{0} seats booked across every night to come': '{0} lugares apartados en todas las noches por venir',
    'show {0}': 'show {0}',
    'tonight': 'esta noche',
    '1 booking': '1 reservación',
    '{0} bookings': '{0} reservaciones',
    '{0} left': 'quedan {0}',
    '{0} sold elsewhere': '{0} vendidos por otro lado',
    '{0} taken online': '{0} cobrados en línea',
    '{0} to collect at the door': '{0} por cobrar en la puerta',
    '{0} checked in': '{0} registrados en la puerta',
    'Who is coming': 'Quién viene',
    'Name': 'Nombre',
    'Seats': 'Lugares',
    'Booked': 'Reservó',
    'Nobody yet.': 'Nadie todavía.',
    'Nothing on the calendar yet.': 'Nada en el calendario todavía.',
    'Recent nights': 'Noches recientes',
    'nobody was scanned at the door': 'nadie fue registrado en la puerta',
    'How was last night?': '¿Qué tal estuvo anoche?',
    # Day-of reminder and giving an open mic seat back (sales/reminders.py, embed/release.html)
    'See you tonight at {0}, {1}.':
        'Te esperamos hoy en {0}, {1}.',
    'Arrive when doors open to get the best seats.':
        'Llega cuando abran las puertas para alcanzar los mejores lugares.',
    'Arrive when doors open so your seat is still yours.':
        'Llega cuando abran las puertas para que tu lugar siga siendo tuyo.',
    'Cannot make it any more? Give your seat back so somebody else can come in:':
        '¿Ya no puedes venir? Devuelve tu lugar para que alguien más pueda entrar:',
    'Cannot make it any more? Give your seats back so somebody else can come in:':
        '¿Ya no pueden venir? Devuelve tus lugares para que alguien más pueda entrar:',
    'Tonight: {0}':
        'Hoy: {0}',
    'Give your seat back':
        'Devuelve tu lugar',
    'Done. Your seat is free for somebody else.':
        'Listo. Tu lugar quedó libre para alguien más.',
    'Thank you for letting us know. The open mic is every week, so come to the next one.':
        'Gracias por avisarnos. El open mic es cada semana, así que ven al siguiente.',
    'See the next open mic':
        'Ver el próximo open mic',
    'This booking cannot be given back here.':
        'Esta reservación no se puede devolver aquí.',
    'The show may already have started, or the seat was already used. Write to hello@iguanacomedy.com if you need help.':
        'Puede que el show ya haya empezado o que el lugar ya se haya usado. Escríbenos a hello@iguanacomedy.com si necesitas ayuda.',
    'See your booking':
        'Ver tu reservación',
    'Cannot make it tonight?':
        '¿No puedes venir hoy?',
    'Giving your seat back lets somebody else come in. Entry is still free if you change your mind, but your seat will not be held.':
        'Si devuelves tu lugar, alguien más puede entrar. La entrada sigue siendo gratis si cambias de opinión, pero ya no te apartaremos el lugar.',
    'Giving your {0} seats back lets other people come in. Entry is still free if you change your mind, but your seats will not be held.':
        'Si devuelves tus {0} lugares, otras personas pueden entrar. La entrada sigue siendo gratis si cambian de opinión, pero ya no les apartaremos los lugares.',
    'Give my seat back':
        'Devolver mi lugar',
    'Give my seats back':
        'Devolver mis lugares',
    'Keep my booking':
        'Conservar mi reservación',
    'You gave this seat back, so somebody else could come in. Thank you.':
        'Devolviste este lugar para que alguien más pudiera entrar. Gracias.',
    'You had a seat for {0} last night. We hope you made it, and that it was a good one.':
        'Tenías lugar para {0} anoche. Esperamos que hayas podido venir y que la hayas pasado bien.',
    'If you enjoyed it, tell somebody. The open mic is every week and free to reserve:':
        'Si te gustó, cuéntaselo a alguien. El open mic es cada semana y reservar es gratis:',
    'And if anything could have been better, just reply to this email. We read every one.':
        'Y si algo pudo haber estado mejor, solo responde a este correo. Los leemos todos.',
    'See you at the next one,': 'Nos vemos en la próxima,',
    'Show {0}.': 'Show {0}.',
    'Tickets from {0}: {1}': 'Boletos desde {0}: {1}',
    'Details: {0}': 'Más información: {0}',
    'Everything that is on: {0}': 'Toda la cartelera: {0}',
    'See you at the club,': 'Nos vemos en el club,',
    # Confirmed opt-in (crm/optin.py, templates/embed/newsletter_confirmed.html)
    'Confirm your email': 'Confirma tu correo',
    'Confirm you want our weekly email about what is on at Iguana Comedy:':
        'Confirma que quieres nuestro correo semanal con lo que hay en Iguana Comedy:',
    'If you did not ask for this, ignore this email and nothing else will be sent.':
        'Si no lo pediste, ignora este correo y no te mandaremos nada más.',
    'Every Monday morning we send {0} one email with what is on that week.':
        'Cada lunes por la mañana mandamos a {0} un correo con lo que hay esa semana.',
    'It may have expired. Sign up again on the site and we will send a new one.':
        'Quizá caducó. Vuelve a registrarte en el sitio y te mandamos otro.',
    'Back to the site': 'Volver al sitio',
    # Free open mic reservation + the drinks upsell
    'Reserve my free spot': 'Reserva mi lugar gratis',
    'Reserve {0} free spots': 'Reserva {0} lugares gratis',
    'Nothing to pay': 'No pagas nada',
    'Want to order your drinks in advance?': '¿Quieres pedir tus bebidas por adelantado?',
    'or pay by card': 'o paga con tarjeta',
    'plus drinks': 'y bebidas',
    # The bar menu ordered from a table (api/menu_views.py)
    'That table number does not exist.': 'Ese número de mesa no existe.',
    'Choose something first.': 'Elige algo primero.',
    'Those items are not available right now.': 'Esos productos no están disponibles ahora.',
    'Order sent to the bar. Someone will bring it to table {0}.':
        'Pedido enviado a la barra. Alguien lo lleva a la mesa {0}.',
    'Reserve a free seat: {0}': 'Reserva un lugar gratis: {0}',
    # The demand line above the reserve button (sales/demand.py)
    'in the last hour': 'en la última hora',
    'in the last few hours': 'en las últimas horas',
    'in the last day': 'en el último día',
    '{0} people reserved {1}': '{0} personas reservaron {1}',
    'Only {0} seats left of {1}': 'Solo quedan {0} lugares de {1}',
    'Only {0} seats left for tonight': 'Solo quedan {0} lugares para esta noche',
    '{0} of {1} seats reserved': '{0} de {1} lugares reservados',
    # Invite a friend, after reserving (sales/sharing.py, templates/embed/order.html)
    # The bar, offered after the seat is held rather than inside the checkout (templates/embed/order.html)
    'Thirsty?': '¿Con sed?',
    'Have a look at what is behind the bar. On the night you can order from your table with the code on it, so '
    'you do not have to get up during a set.':
        'Echa un ojo a lo que hay en la barra. La noche del show puedes pedir desde tu mesa con el código que '
        'tiene, para no levantarte a media rutina.',
    'See the menu': 'Ver el menú',
    # The bar's board (api/tables_views.py, templates/embed/tables.html)
    'Tables': 'Mesas',
    'Table': 'Mesa',
    '{0} waiting': '{0} esperando',
    'Nothing waiting': 'Nada esperando',
    'Nothing ordered': 'Sin pedidos',
    'just now': 'ahora mismo',
    '{0} min ago': 'hace {0} min',
    'Delivered': 'Entregado',
    'This page refreshes itself. A table disappears once it is marked delivered.':
        'Esta página se actualiza sola. Una mesa desaparece al marcarla como entregada.',
    'Bringing someone?': '¿Vienes con alguien?',
    'These nights fill up. Send this to whoever you want to bring and they can reserve their own free seat.':
        'Estas noches se llenan. Manda esto a quien quieras traer y aparta su lugar gratis.',
    'Invite on WhatsApp': 'Invitar por WhatsApp',
    'Copy the link': 'Copiar el enlace',
    'Link copied': 'Enlace copiado',
    'Bringing someone? Send them this and they can get their own ticket:':
        '¿Vienes con alguien? Mándale esto y puede comprar su propio boleto:',
    'Our next headliner:': 'Nuestro próximo show estelar:',
    'Our next headliner: {0}, {1}.': 'Nuestro próximo show estelar: {0}, {1}.',
    'Tickets {0}:': 'Boletos {0}:',
    'Open mic bookers who then paid for a show': 'Quienes reservaron un open mic y luego pagaron un show',
    'booked an open mic': 'reservaron un open mic',
    'later bought a paid show': 'luego compraron un show de pago',
    'From the next-headliner link: {0} clicks on the order page and {1} from the email, {2} and {3} paid orders.':
        'Del enlace al próximo show estelar: {0} clics en la página del pedido y {1} desde el correo, {2} y {3} compras.',
    'Bringing someone? Send them this and they can reserve their own free seat:':
        '¿Vienes con alguien? Mándale esto y aparta su lugar gratis:',
    'I am going to the open mic at Iguana Comedy. Entry is free, reserve a seat here: {0}':
        'Voy al open mic de Iguana Comedy. La entrada es gratis, aparta tu lugar aquí: {0}',

    # La cuenta de la mesa pagada desde el teléfono del cliente, y su QR.
    'Your bill': 'Tu cuenta',
    'Drinks': 'Bebidas',
    'Tip for your waiter': 'Propina para tu mesero',
    '{0}% is what the house suggests. Change it or leave none, it is up to you.':
        '{0}% es lo que sugiere la casa. Cámbialo o déjalo en cero, tú decides.',
    'None': 'Sin propina',
    'Total': 'Total',
    'Continue to card': 'Continuar con la tarjeta',
    'Pay now': 'Pagar ahora',
    'Pay by card': 'Pagar con tarjeta',
    'One moment': 'Un momento',
    'That did not go through. Please try again.': 'No se pudo cobrar. Inténtalo otra vez, por favor.',
    'The card is handled by Stripe. Iguana Comedy never sees your card number.':
        'El cobro lo procesa Stripe. Iguana Comedy nunca ve el número de tu tarjeta.',
    'This bill has closed.': 'Esta cuenta ya está cerrada.',
    'Ask your waiter to show the code again.': 'Pídele a tu mesero que te muestre el código otra vez.',
    'Nothing to pay': 'No hay nada que pagar',
    'This table has no open bill. Ask your waiter if you think that is wrong.':
        'Esta mesa no tiene cuenta abierta. Si crees que es un error, pregúntale a tu mesero.',
    'There is nothing to pay on this table.': 'Esta mesa no tiene nada que pagar.',
    'Card payment is not available right now.': 'El pago con tarjeta no está disponible ahora mismo.',
    'Paid': 'Pagado',
    'Not paid': 'Sin pagar',
    'Includes {0} tip': 'Incluye {0} de propina',
    'Show this to your waiter on the way out. Thanks for coming.':
        'Enséñale esto a tu mesero al salir. Gracias por venir.',
    'Nothing was charged. Ask your waiter to show the code again.':
        'No se cobró nada. Pídele a tu mesero que te muestre el código otra vez.',
    'Show QR to pay': 'Mostrar QR para pagar',
    'Hide QR': 'Ocultar QR',
    'They scan this to pay the whole bill by card': 'Escanean esto para pagar toda la cuenta con tarjeta',
    'Paid by card': 'Pagado con tarjeta',
    # /drop/ (api/drop_views.py)
    'Documents for Iguana Comedy': 'Documentos para Iguana Comedy',
    'Documents for account setup': 'Documentos para abrir las cuentas',
    'PIN': 'PIN',
    'Open': 'Abrir',
    'That PIN is not right.': 'Ese PIN no es correcto.',
    'Too many wrong PINs. Try again in {0} minutes.': 'Demasiados PIN incorrectos. Intenta de nuevo en {0} minutos.',
    'Choose what you are sending.': 'Elige qué estás enviando.',
    'Add a file or write a note.': 'Agrega un archivo o escribe una nota.',
    'Received: {0}. Thank you.': 'Recibido: {0}. Gracias.',
    'Files sent here are stored privately and cannot be opened or listed from this page, by you or anyone else.':
        'Los archivos que envíes aquí se guardan en privado y nadie puede abrirlos ni verlos desde esta página, tampoco tú.',
    'Card for ad billing': 'Tarjeta para pagar los anuncios',
    'Photos of the front and back. When the card is replaced, upload the new one here and it takes over.':
        'Fotos del frente y del reverso. Cuando cambien la tarjeta, suban la nueva aquí y esa es la que se usa.',
    'What are you sending?': '¿Qué estás enviando?',
    'Choose one': 'Elige uno',
    'Files (photos or PDFs, up to 60 MB in total)': 'Archivos (fotos o PDF, hasta 60 MB en total)',
    'Note (optional): logins, answers, links': 'Nota (opcional): accesos, respuestas, enlaces',
    'Send': 'Enviar',
    'What is needed': 'Lo que se necesita',
    'received': 'recibido',
    'received, needs attention': 'recibido, falta algo',
    'still needed': 'todavía falta',
    'Constancia de situación fiscal': 'Constancia de situación fiscal',
    'The PDF from the SAT, issued in the last 3 months. It carries the RFC and razón social.':
        'El PDF del SAT, emitido en los últimos 3 meses. Incluye el RFC y la razón social.',
    "Legal representative's ID": 'Identificación del representante legal',
    'INE (both sides) or passport, as photos or a PDF.': 'INE (por ambos lados) o pasaporte, en fotos o PDF.',
    'Proof of address': 'Comprobante de domicilio',
    'A utility bill or bank statement at the fiscal address, from the last 3 months.':
        'Un recibo de luz, agua o teléfono, o un estado de cuenta, del domicilio fiscal y de los últimos 3 meses.',
    'Acta constitutiva': 'Acta constitutiva',
    'Only if the business is a company (persona moral).': 'Solo si el negocio es una persona moral.',
    'Existing accounts': 'Cuentas que ya existen',
    'Logins for the YouTube channel and TikTok @iguanacomedy, if they are the club’s, and any Google account the club already uses.':
        'Los accesos del canal de YouTube y de TikTok @iguanacomedy, si son del club, y cualquier cuenta de Google que el club ya use.',
    'Logo and banner': 'Logo y portada',
    'Optional. The site logo is used if nothing is sent.': 'Opcional. Si no se envía nada, se usa el logo del sitio.',
    'Comedian permissions': 'Permisos de los comediantes',
    'Signed OKs from comedians to post and monetize clips of their sets.':
        'Autorizaciones firmadas de los comediantes para publicar y monetizar clips de sus rutinas.',
    'Anything else': 'Cualquier otra cosa',
    'Answers, notes, links to footage.': 'Respuestas, notas, enlaces a los videos.',
    # /comic/ (api/comic_views.py): comedians send their photo, clips and dates
    'Comedians: send us your photo and clips': 'Comediantes: mándanos tu foto y tus clips',
    'Comedians who want a show at Iguana Comedy: send your photo, your clips and the dates you would like.':
        'Comediantes que quieren un show en Iguana Comedy: manden su foto, sus clips y las fechas que les gustarían.',
    'Want a show at Iguana Comedy?': '¿Quieres un show en Iguana Comedy?',
    'Send us your photo, a few clips and the dates you would like. The photo is what we make the flyer from, and we cut the clips into the ads, so the better they are the fuller the room.':
        'Mándanos tu foto, algunos clips y las fechas que te gustarían. Con la foto hacemos el flyer y con los clips hacemos los anuncios, así que entre mejores sean, más se llena la sala.',
    'Your files are kept private and only the Iguana team sees them.':
        'Tus archivos se guardan en privado y solo los ve el equipo de Iguana.',
    'Please fix this:': 'Corrige esto, por favor:',
    '{0} is larger than {1} MB.': '{0} pesa más de {1} MB.',
    'Send up to {0} photos.': 'Manda hasta {0} fotos.',
    'Uploading, {0}% done. Keep this page open.': 'Subiendo, va en {0}%. No cierres esta página.',
    'The upload did not finish. Check your connection and send it again, or write to hello@iguanacomedy.com.':
        'La subida no terminó. Revisa tu conexión y vuelve a enviarlo, o escríbenos a hello@iguanacomedy.com.',
    'Trouble uploading or sending? Write to us and we will help:':
        '¿Problemas para subir o enviar? Escríbenos y te ayudamos:',
    'Questions about your show?': '¿Dudas sobre tu show?',
    'Fill in the fields marked with an asterisk.': 'Llena los campos marcados con asterisco.',
    'About you': 'Sobre ti',
    'Your name': 'Tu nombre',
    'Stage name, if different': 'Nombre artístico, si es otro',
    'Phone or WhatsApp': 'Teléfono o WhatsApp',
    'Where you are based': 'Dónde vives',
    'Languages you perform in': 'Idiomas en los que haces comedia',
    'English': 'Inglés',
    'Spanish': 'Español',
    'Other': 'Otro',
    'Short bio': 'Bio corta',
    'In English or Spanish, whichever you prefer. A few lines we can use on the event page.':
        'En español o en inglés, como prefieras. Unas líneas que podamos usar en la página del evento.',
    'Links to more of your work': 'Enlaces a más de tu trabajo',
    'YouTube, a special, a podcast, press.': 'YouTube, un especial, un podcast, prensa.',
    'Photos for the flyer': 'Fotos para el flyer',
    'Your best photos': 'Tus mejores fotos',
    'Up to {0} high resolution photos: JPG, PNG, HEIC or WebP, {1} MB each. A clear, well lit shot of you works best.':
        'Hasta {0} fotos en alta resolución: JPG, PNG, HEIC o WebP, de {1} MB cada una. Funciona mejor una foto clara y bien iluminada de ti.',
    'Clips': 'Clips',
    'MP4 or MOV, up to {0} MB each. We will cut and adjust them for the ads, so send the raw clip rather than a finished edit if you have it.':
        'MP4 o MOV, hasta {0} MB cada uno. Los vamos a cortar y ajustar para los anuncios, así que si lo tienes, manda el clip sin editar en lugar de la versión final.',
    'About 30 seconds': 'Unos 30 segundos',
    'About 1 minute': 'Como 1 minuto',
    'A longer set, 2 to 5 minutes': 'Una rutina más larga, de 2 a 5 minutos',
    'No clip to upload? Put a link to one under Links above.':
        '¿No tienes un clip para subir? Pon un enlace a uno en Enlaces, más arriba.',
    'The show you want': 'El show que quieres',
    'Dates you would like, in order of preference': 'Fechas que te gustarían, en orden de preferencia',
    'Date': 'Fecha',
    'Add another date': 'Agregar otra fecha',
    'Availability notes': 'Notas sobre tu disponibilidad',
    'When you are in the area, days that do not work, anything flexible.':
        'Cuándo andas por la zona, qué días no puedes, qué es flexible.',
    'Show name, if it has one': 'Nombre del show, si tiene',
    'Expected draw': 'Cuánta gente esperas',
    'Followers, how many people usually come to see you, where you have sold out.':
        'Seguidores, cuánta gente suele ir a verte, dónde has agotado boletos.',
    'Ticket price you have in mind': 'El precio de boleto que tienes en mente',
    'Do you bring your own opener or guests?': '¿Traes tu propio abridor o invitados?',
    'Anything else we should know': 'Algo más que debamos saber',
    'Iguana Comedy may use these photos and clips, edited or as they are, to promote my show on its site, in ads and on social media.':
        'Iguana Comedy puede usar estas fotos y clips, editados o tal como están, para promocionar mi show en su sitio, en anuncios y en redes sociales.',
    'Large clips can take a few minutes to upload on a phone. Wifi is faster.':
        'Los clips grandes pueden tardar unos minutos en subir desde el celular. Con wifi es más rápido.',
    'One of the dates is not a date. Use the date picker.': 'Una de las fechas no es válida. Usa el selector de fecha.',
    'Choose dates from today on.': 'Elige fechas de hoy en adelante.',
    'Choose dates within the next 18 months.': 'Elige fechas dentro de los próximos 18 meses.',
    'Write your name.': 'Escribe tu nombre.',
    'Write an email address we can reach you at.': 'Escribe un correo donde podamos contactarte.',
    'Write your bio and notes in words, a sentence or two is plenty.':
        'Escribe tu bio y tus notas con palabras; una o dos frases bastan.',
    'Add at least one photo of you. It is what the flyer is made from.':
        'Agrega al menos una foto tuya. Con ella hacemos el flyer.',
    '{0} is not a photo we can use. Send JPG, PNG, HEIC or WebP.': '{0} no es una foto que podamos usar. Manda JPG, PNG, HEIC o WebP.',
    '{0} is not a video we can use. Send MP4 or MOV.': '{0} no es un video que podamos usar. Manda MP4 o MOV.',
    'Send at least one clip, or a link to one.': 'Manda al menos un clip, o un enlace a uno.',
    'Tick the box that lets us use your photos and clips to promote the show.':
        'Marca la casilla que nos permite usar tus fotos y clips para promocionar el show.',
    'Too many submissions from here. Try again later, or write to hello@iguanacomedy.com.':
        'Demasiados envíos desde aquí. Intenta más tarde o escribe a hello@iguanacomedy.com.',
    'We cannot take uploads right now. Write to hello@iguanacomedy.com and we will sort it out.':
        'Ahora mismo no podemos recibir archivos. Escribe a hello@iguanacomedy.com y lo resolvemos.',
    'Thank you for sending your material to Iguana Comedy. We received {0} photo(s) and {1} clip(s).':
        'Gracias por mandar tu material a Iguana Comedy. Recibimos {0} foto(s) y {1} clip(s).',
    'Dates you asked about: {0}.': 'Fechas que pediste: {0}.',
    'We will look at everything and write back to this address. We may cut and adjust your clips for the ads and use your photo for the flyer.':
        'Vamos a revisar todo y te escribimos a este correo. Puede que cortemos y ajustemos tus clips para los anuncios y usemos tu foto para el flyer.',
    'To add or change anything, or if a file did not go through, reply to this email or write to hello@iguanacomedy.com.':
        'Si quieres agregar o cambiar algo, o si algún archivo no llegó, responde a este correo o escríbenos a hello@iguanacomedy.com.',
    'We got your photos and clips': 'Recibimos tus fotos y tus clips',
    'Thank you': 'Gracias',
    'Thank you, we have it all': 'Gracias, ya tenemos todo',
    'Your photos, clips and dates reached us. We will look at everything and be in touch by email or WhatsApp.':
        'Nos llegaron tus fotos, clips y fechas. Vamos a revisar todo y te contactamos por correo o WhatsApp.',
    'We sent you a copy by email. To add or change anything, reply to it.':
        'Te mandamos una copia por correo. Si quieres agregar o cambiar algo, respóndelo.',
    # /chat/ (api/chat_views.py, templates/embed/chat.html): the owner's chat with the agent that runs the site.
    'Chat': 'Chat',
    'Ask for anything on the site: a fix, a new show, a question about bookings. The agent works in its own copy of the code, runs the tests, pushes to GitHub and deploys. It can do anything you could do yourself, so say exactly what you want.':
        'Pide lo que sea del sitio: un arreglo, un show nuevo, una pregunta sobre las reservas. El agente trabaja en su propia copia del código, corre las pruebas, sube los cambios a GitHub y los publica. Puede hacer todo lo que tú podrías hacer, así que di exactamente lo que quieres.',
    'Conversation': 'Conversación',
    'New conversation': 'Conversación nueva',
    'The agent is busy with another conversation. A new message waits until it finishes.':
        'El agente está ocupado con otra conversación. Un mensaje nuevo espera hasta que termine.',
    'What should the agent do?': '¿Qué debe hacer el agente?',
    'Ctrl+Enter sends': 'Ctrl+Enter envía',
    'Send': 'Enviar',
    'Waiting for the agent…': 'Esperando al agente…',
    'Working…': 'Trabajando…',
    'Stopped.': 'Detenido.',
    'Failed': 'Falló',
    'Stop': 'Detener',
    '{0} steps': '{0} pasos',
    'Could not send. Check the connection and try again.': 'No se pudo enviar. Revisa la conexión e inténtalo de nuevo.',
    'Not allowed': 'No permitido',
    'Write a message first': 'Escribe un mensaje primero',
    'That message is too long': 'Ese mensaje es demasiado largo',
    'Wait for the current reply to finish, or stop it': 'Espera a que termine la respuesta actual, o detenla',
}


def normalize(lang):
    """Anything Spanish ('es', 'es-MX', 'ES') becomes 'es'; everything else is English."""
    return 'es' if str(lang or '').strip().lower().startswith('es') else 'en'


def tr(lang, text, *params):
    template = ES.get(text, text) if normalize(lang) == 'es' else text
    return template.format(*params) if params else template


def locale_from_request(request):
    """The language a browser call belongs to: the explicit parameter, then our own header, then the page that
    made the call. Some SDK methods take no locale argument, and the referring /es/ or /en/ path is the only
    signal they carry."""
    explicit = request.GET.get('locale') or request.headers.get('X-Iguana-Locale', '')
    if explicit:
        return normalize(explicit)
    referer = request.headers.get('Referer', '')
    try:
        first = urlparse(referer).path.strip('/').split('/')[0]
    except ValueError:
        first = ''
    return normalize(first)


def lang_from_request(request):
    """The browser's preferred language, for pages with no order or page locale to follow (door check-in)."""
    return normalize(request.headers.get('Accept-Language', ''))
