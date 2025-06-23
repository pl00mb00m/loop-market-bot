print("🚀 Iniciando el bot...")
import asyncio
import json
import datetime
import logging
import os
from html import escape
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton, Location, InputMediaPhoto,
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramBadRequest
from dotenv import load_dotenv

# ДОБАВЛЕНО для Webhooks с aiohttp
from aiohttp import web
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

# ДОБАВЛЕНО для генерации secret_token
import secrets # <-- ЭТА СТРОКА ДОБАВЛЕНА

# 📝 Configuración del registro (logging)
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[logging.StreamHandler()], force=True)
logger = logging.getLogger(__name__)

# 🔧 Cargar variables de entorno
load_dotenv()
print("🔍 Verificando variables de entorno...")
API_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
print(f"BOT_TOKEN: {'✅ configurado' if API_TOKEN else '❌ no configurado'}")
print(f"ADMIN_ID: {'✅ configurado' if ADMIN_ID else '❌ no configurado'}")

# ✅ Verificación de variables de entorno
if not API_TOKEN:
    logger.error("❌ ERROR: El token del bot (BOT_TOKEN) no está configurado en las variables de entorno.")
    exit(1)
if not ADMIN_ID:
    logger.warning("⚠️ ADVERTENCIA: El ID del administrador (ADMIN_ID) no está configurado.")
    ADMIN_ID = None # Asegurarse de que es None si no está configurado
else:
    try:
        ADMIN_ID = int(ADMIN_ID)
    except ValueError:
        logger.error("❌ ERROR: ADMIN_ID debe ser un número entero.")
        exit(1)

# 🌐 Configuración del Webhook para Render
WEBAPP_HOST = '0.0.0.0' # Для Render, слушать на всех интерфейсах
WEBAPP_PORT = os.getenv('PORT') # Render предоставляет порт через ENV

if not WEBAPP_PORT:
    logger.error("❌ ERROR: La variable de entorno PORT no está configurada por Render.")
    exit(1)
else:
    try:
        WEBAPP_PORT = int(WEBAPP_PORT)
    except ValueError:
        logger.error("❌ ERROR: PORT debe ser un número entero.")
        exit(1)

RENDER_EXTERNAL_HOSTNAME = os.getenv('RENDER_EXTERNAL_HOSTNAME')

# Изменено: Если RENDER_EXTERNAL_HOSTNAME не задан, мы не можем создать URL вебхука
if not RENDER_EXTERNAL_HOSTNAME:
    logger.error("❌ ERROR: La variable de entorno RENDER_EXTERNAL_HOSTNAME no está configurada. Necesaria para WEBHOOK_URL.")
    exit(1)
else:
    # Генерируем секретный токен для вебхука
    WEBHOOK_SECRET = secrets.token_urlsafe(32) # <-- ЭТА СТРОКА ДОБАВЛЕНА
    WEBHOOK_URL = f"https://{RENDER_EXTERNAL_HOSTNAME}/webhook/{WEBHOOK_SECRET}" # <-- ЭТА СТРОКА ИЗМЕНЕНА
    # Важно: WEBHOOK_PATH = /webhook/{WEBHOOK_SECRET}

# 🤖 Inicialización del bot y dispatcher
default_props = DefaultBotProperties(parse_mode=ParseMode.HTML)
bot = Bot(token=API_TOKEN, default=default_props)
storage = MemoryStorage() # Используем MemoryStorage, для больших ботов можно рассмотреть Redis
dp = Dispatcher(storage=storage)


# 📝 Diccionarios para almacenar данные (persistentes entre reinicios si se guarda/carga)
user_data_file = 'user_data.json'
listings_file = 'listings.json'
users_data = {}
listings = {}

async def load_user_data():
    global users_data
    if os.path.exists(user_data_file):
        with open(user_data_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            users_data = {int(k): v for k, v in data.items()}
            logger.info(f"✅ Datos de usuario cargados desde {user_data_file}")
    else:
        users_data = {}
        logger.info(f"🆕 {user_data_file} no encontrado, iniciando con datos de usuario vacíos.")

async def save_user_data():
    with open(user_data_file, 'w', encoding='utf-8') as f:
        json.dump(users_data, f, ensure_ascii=False, indent=4)
    logger.info(f"💾 Datos de usuario guardados en {user_data_file}")

async def load_listings():
    global listings
    if os.path.exists(listings_file):
        with open(listings_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            listings = {k: v for k, v in data.items()}
            # Convertir las fechas de expiración de nuevo a objetos datetime
            for listing_id, listing_info in listings.items():
                if 'expires_at' in listing_info and isinstance(listing_info['expires_at'], str):
                    try:
                        listing_info['expires_at'] = datetime.datetime.fromisoformat(listing_info['expires_at'])
                    except ValueError:
                        logger.error(f"❌ Error al parsear fecha para {listing_id}: {listing_info['expires_at']}")
                        listing_info['expires_at'] = None # O manejar el error de otra forma
            logger.info(f"✅ Anuncios cargados desde {listings_file}")
    else:
        listings = {}
        logger.info(f"🆕 {listings_file} no encontrado, iniciando con anuncios vacíos.")

async def save_listings():
    with open(listings_file, 'w', encoding='utf-8') as f:
        # Convertir objetos datetime a strings ISO para JSON
        json_serializable_listings = {}
        for listing_id, listing_info in listings.items():
            serializable_info = listing_info.copy()
            if 'expires_at' in serializable_info and isinstance(serializable_info['expires_at'], datetime.datetime):
                serializable_info['expires_at'] = serializable_info['expires_at'].isoformat()
            json_serializable_listings[listing_id] = serializable_info
        json.dump(json_serializable_listings, f, ensure_ascii=False, indent=4)
    logger.info(f"💾 Anuncios guardados en {listings_file}")


# 📚 Estados para FSM
class Form(StatesGroup):
    title = State()
    description = State()
    category = State()
    price = State()
    photos = State()
    location = State()
    contact = State()
    terms_agreed = State()
    confirm_publish = State()
    edit_field = State()
    edit_item_id = State()
    edit_title = State()
    edit_description = State()
    edit_category = State()
    edit_price = State()
    edit_photos = State()
    edit_location = State()
    edit_contact = State()
    confirm_delete = State()
    set_duration = State()


# ⌨️ Teclados
main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ Publicar Anuncio"), KeyboardButton(text="🔍 Mis Anuncios")],
        [KeyboardButton(text="⚙️ Configuración")]
    ],
    resize_keyboard=True,
    input_field_placeholder="Seleccione una opción"
)

# ... (Остальные клавиатуры остались без изменений) ...
def get_main_keyboard_admin():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Publicar Anuncio"), KeyboardButton(text="🔍 Mis Anuncios")],
            [KeyboardButton(text="⚙️ Configuración"), KeyboardButton(text="📊 Admin Panel")] # Добавлена кнопка админ-панели
        ],
        resize_keyboard=True,
        input_field_placeholder="Seleccione una opción"
    )


# ------------------------------ Funciones de ayuda ------------------------------
def generate_listing_id():
    """Genera un ID único basado en el timestamp."""
    return str(int(datetime.datetime.now().timestamp()))

def format_listing_message(listing_id, listing_info, include_contact=False):
    """Formatea la información del anuncio en un mensaje."""
    title = escape(listing_info.get('title', 'N/A'))
    description = escape(listing_info.get('description', 'N/A'))
    category = escape(listing_info.get('category', 'N/A'))
    price = listing_info.get('price', 'N/A')
    location_str = escape(listing_info.get('location_name', 'No especificada'))

    expires_at = listing_info.get('expires_at')
    expiry_info = ""
    if expires_at and isinstance(expires_at, datetime.datetime):
        remaining_time = expires_at - datetime.datetime.now()
        if remaining_time.total_seconds() > 0:
            days = remaining_time.days
            hours = remaining_time.seconds // 3600
            minutes = (remaining_time.seconds % 3600) // 60
            if days > 0:
                expiry_info = f"Vigencia: {days}d {hours}h {minutes}m"
            else:
                expiry_info = f"Vigencia: {hours}h {minutes}m"
        else:
            expiry_info = "Expirado"
    else:
        expiry_info = "Vigencia: Indefinido" # Fallback si no hay fecha o es inválida

    message_text = (
        f"<b>Anuncio #{listing_id}</b>\n"
        f"<b>Título:</b> {title}\n"
        f"<b>Descripción:</b> {description}\n"
        f"<b>Categoría:</b> {category}\n"
        f"<b>Precio:</b> ${price}\n"
        f"<b>Ubicación:</b> {location_str}\n"
        f"<i>{expiry_info}</i>"
    )

    if include_contact:
        contact = escape(listing_info.get('contact', 'No especificado'))
        message_text += f"\n<b>Contacto:</b> {contact}"
    
    return message_text

async def display_item_card(chat_id, listing_id, caller_is_edit=False, is_admin_view=False):
    """Muestra la tarjeta del anuncio con sus opciones."""
    listing = listings.get(listing_id)
    if not listing:
        await bot.send_message(chat_id, "❗ Anuncio no encontrado.")
        return

    photos = listing.get('photos', [])
    caption = format_listing_message(listing_id, listing, include_contact=True)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    
    # Botones para usuario/administrador
    if is_admin_view:
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(text="📝 Editar", callback_data=f"edit_listing:{listing_id}"),
            InlineKeyboardButton(text="❌ Eliminar", callback_data=f"delete_listing:{listing_id}")
        ])
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(text="⏳ Establecer vigencia", callback_data=f"set_duration:{listing_id}")
        ])
        keyboard.inline_keyboard.append([InlineKeyboardButton(text="⬅️ Volver al Panel Admin", callback_data="back_to_admin_panel")])
    elif caller_is_edit: # Si el usuario está editando su propio anuncio
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(text="📝 Editar", callback_data=f"edit_listing:{listing_id}"),
            InlineKeyboardButton(text="❌ Eliminar", callback_data=f"delete_listing:{listing_id}")
        ])
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(text="⏳ Establecer vigencia", callback_data=f"set_duration:{listing_id}")
        ])
        keyboard.inline_keyboard.append([InlineKeyboardButton(text="⬅️ Mis Anuncios", callback_data="my_listings")])

    else: # Vista pública del anuncio
        # Si es el propietario del anuncio, mostrar botones de edición
        if listing.get('user_id') == chat_id:
             keyboard.inline_keyboard.append([
                InlineKeyboardButton(text="📝 Editar", callback_data=f"edit_listing:{listing_id}"),
                InlineKeyboardButton(text="❌ Eliminar", callback_data=f"delete_listing:{listing_id}")
            ])
             keyboard.inline_keyboard.append([
                InlineKeyboardButton(text="⏳ Establecer vigencia", callback_data=f"set_duration:{listing_id}")
            ])
        
        # Botón para ir a la ubicación (si existe)
        if 'location_latitude' in listing and 'location_longitude' in listing:
            location_url = f"http://maps.google.com/maps?q={listing['location_latitude']},{listing['location_longitude']}"
            keyboard.inline_keyboard.append([
                InlineKeyboardButton(text="📍 Ver en Mapa", url=location_url)
            ])
        
        # Botón de contacto directo
        if listing.get('contact'):
            keyboard.inline_keyboard.append([
                InlineKeyboardButton(text="💬 Contactar", url=f"https://t.me/{listing['contact']}")
            ])
        
        keyboard.inline_keyboard.append([InlineKeyboardButton(text="⬅️ Volver", callback_data="back_to_main")])


    if photos:
        media = []
        for i, photo_id in enumerate(photos):
            if i == 0: # Primera foto con caption
                media.append(InputMediaPhoto(media=photo_id, caption=caption))
            else: # Resto de fotos sin caption
                media.append(InputMediaPhoto(media=photo_id))
        
        try:
            await bot.send_media_group(chat_id, media=media)
            # El teclado se envía con un mensaje separado si hay fotos,
            # ya que send_media_group no soporta reply_markup directamente.
            await bot.send_message(chat_id, "Opciones del anuncio:", reply_markup=keyboard)
        except TelegramBadRequest as e:
            logger.error(f"❌ Error al enviar grupo de fotos o mensaje: {e}")
            await bot.send_message(chat_id, caption, reply_markup=keyboard) # Enviar solo texto si falla
    else:
        await bot.send_message(chat_id, caption, reply_markup=keyboard)

def get_edit_field_keyboard(listing_id):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Título", callback_data=f"edit_field_type:{listing_id}:title")],
        [InlineKeyboardButton(text="📝 Descripción", callback_data=f"edit_field_type:{listing_id}:description")],
        [InlineKeyboardButton(text="📝 Categoría", callback_data=f"edit_field_type:{listing_id}:category")],
        [InlineKeyboardButton(text="📝 Precio", callback_data=f"edit_field_type:{listing_id}:price")],
        [InlineKeyboardButton(text="📸 Fotos", callback_data=f"edit_field_type:{listing_id}:photos")],
        [InlineKeyboardButton(text="📍 Ubicación", callback_data=f"edit_field_type:{listing_id}:location")],
        [InlineKeyboardButton(text="📞 Contacto", callback_data=f"edit_field_type:{listing_id}:contact")],
        [InlineKeyboardButton(text="⬅️ Volver al Anuncio", callback_data=f"view_listing_edit:{listing_id}")]
    ])
    return keyboard

def get_confirm_delete_keyboard(listing_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Sí, eliminar", callback_data=f"confirm_delete_yes:{listing_id}")],
        [InlineKeyboardButton(text="❌ No, cancelar", callback_data=f"confirm_delete_no:{listing_id}")]
    ])

def get_expires_at_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📅 3 días"), KeyboardButton(text="📅 5 días")],
            [KeyboardButton(text="🗓️ Sin fecha de caducidad")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

# ------------------------------ Handlers ------------------------------

@dp.message(Command("start"))
async def command_start_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    user_id = message.from_user.id
    username = message.from_user.username
    full_name = message.from_user.full_name

    if user_id not in users_data:
        users_data[user_id] = {
            'username': username,
            'full_name': full_name,
            'first_access': datetime.datetime.now().isoformat()
        }
        await save_user_data()
        logger.info(f"🆕 Nuevo usuario registrado: {user_id} ({full_name})")
        await message.answer(
            f"¡Hola {escape(message.from_user.full_name)}! 👋\n"
            "Bienvenido al bot de compra y venta. Aquí puedes publicar tus anuncios y encontrar lo que buscas.",
            reply_markup=main_keyboard
        )
        if ADMIN_ID and user_id != ADMIN_ID: # Оповестить админа о новом пользователе
            await bot.send_message(ADMIN_ID, f"🎉 Nuevo usuario: {full_name} (@{username if username else 'N/A'}) (ID: {user_id})")
    else:
        users_data[user_id]['username'] = username # Обновляем никнейм на случай изменения
        users_data[user_id]['full_name'] = full_name # Обновляем полное имя
        await save_user_data()
        await message.answer(
            f"¡Hola de nuevo {escape(message.from_user.full_name)}! 👋",
            reply_markup=main_keyboard if user_id != ADMIN_ID else get_main_keyboard_admin()
        )
    logger.info(f"➡️ Usuario {user_id} inició el bot.")


@dp.message(F.text == "➕ Publicar Anuncio")
async def start_new_listing(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(Form.title)
    await message.answer("¡Empecemos! ¿Cuál es el título de tu anuncio? (Ej: 'IPhone 15 Pro Max 256GB')")
    logger.info(f"➡️ Usuario {message.from_user.id} inició la publicación de un anuncio.")

@dp.message(Form.title)
async def process_title(message: Message, state: FSMContext):
    if len(message.text) > 100:
        await message.answer("❗ El título es demasiado largo. Por favor, que no exceda 100 caracteres.")
        return
    await state.update_data(title=message.text)
    await state.set_state(Form.description)
    await message.answer("Ahora, una descripción detallada. (Ej: 'Como nuevo, con garantía, incluye accesorios')")

@dp.message(Form.description)
async def process_description(message: Message, state: FSMContext):
    if len(message.text) > 1000:
        await message.answer("❗ La descripción es demasiado larga. Por favor, que no exceda 1000 caracteres.")
        return
    await state.update_data(description=message.text)
    await state.set_state(Form.category)
    await message.answer(
        "¿En qué categoría encaja tu anuncio?",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="📱 Electrónica"), KeyboardButton(text="👗 Moda")],
                [KeyboardButton(text="🏡 Hogar"), KeyboardButton(text="🚗 Vehículos")],
                [KeyboardButton(text="📚 Libros"), KeyboardButton(text="🏀 Deportes")],
                [KeyboardButton(text="💼 Servicios"), KeyboardButton(text="✨ Otros")]
            ],
            resize_keyboard=True, one_time_keyboard=True
        )
    )

@dp.message(Form.category, F.text.in_({"📱 Electrónica", "👗 Moda", "🏡 Hogar", "🚗 Vehículos", "📚 Libros", "🏀 Deportes", "💼 Servicios", "✨ Otros"}))
async def process_category(message: Message, state: FSMContext):
    await state.update_data(category=message.text)
    await state.set_state(Form.price)
    await message.answer("¿Cuál es el precio? (Ej: '150.50' o 'Negociable')", reply_markup=None) # Quitar teclado anterior

@dp.message(Form.category)
async def process_category_invalid(message: Message):
    await message.answer("❗ Por favor, seleccione una categoría de la lista.")

@dp.message(Form.price)
async def process_price(message: Message, state: FSMContext):
    price_text = message.text.replace(',', '.').strip()
    if price_text.lower() == 'negociable':
        await state.update_data(price='Negociable')
    else:
        try:
            price = float(price_text)
            if price <= 0:
                raise ValueError
            await state.update_data(price=f"{price:.2f}") # Formatear a 2 decimales
        except ValueError:
            await message.answer("❗ Formato de precio inválido. Por favor, introduzca un número (ej: '150.50') o 'Negociable'.")
            return
    await state.update_data(photos=[]) # Inicializar lista de fotos
    await state.set_state(Form.photos)
    await message.answer(
        "¡Perfecto! Ahora, envía hasta 10 fotos de tu artículo. Puedes enviar varias a la vez. Cuando termines, envía 'Listo'.",
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Listo")]], resize_keyboard=True)
    )

@dp.message(Form.photos, F.photo)
async def process_photos(message: Message, state: FSMContext):
    data = await state.get_data()
    photos = data.get('photos', [])
    
    if len(photos) >= 10:
        await message.answer("❗ Ya tienes el máximo de 10 fotos. Por favor, envía 'Listo'.")
        return
    
    # Tomar la ID de la foto de la mayor resolución
    file_id = message.photo[-1].file_id
    photos.append(file_id)
    await state.update_data(photos=photos)
    await message.answer(f"✅ Foto añadida. Tienes {len(photos)}/{10} fotos. Envía más o 'Listo'.")


@dp.message(Form.photos, F.text == "Listo")
async def process_photos_done(message: Message, state: FSMContext):
    data = await state.get_data()
    photos = data.get('photos', [])
    if not photos:
        await message.answer("❗ Por favor, envía al menos una foto antes de continuar, o continúa si no tienes fotos.")
        # Opcional: permitir continuar sin fotos, si es el caso
        # await message.answer("¿Estás seguro de que quieres continuar sin fotos? Si es así, envía 'Sí, sin fotos'.")
        # await state.set_state(Form.confirm_no_photos) # Nuevo estado si se permite sin fotos
        return

    await state.set_state(Form.location)
    await message.answer(
        "Ahora, por favor, comparte tu ubicación o escribe la zona. (Ej: 'Guayaquil', 'Samborondón', 'Quito')",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Compartir mi ubicación actual", request_location=True)]],
            resize_keyboard=True, one_time_keyboard=True
        )
    )

@dp.message(Form.location, F.location)
async def process_location_by_coords(message: Message, state: FSMContext):
    await state.update_data(
        location_latitude=message.location.latitude,
        location_longitude=message.location.longitude,
        location_name="Ubicación compartida por GPS" # Puedes intentar geocodificar para obtener nombre
    )
    await state.set_state(Form.contact)
    await message.answer(
        "¡Excelente! Ahora, ingresa tu usuario de Telegram para contacto. (Ej: @tu_usuario) o tu número de teléfono.",
        reply_markup=None # Remover teclado anterior
    )

@dp.message(Form.location)
async def process_location_by_text(message: Message, state: FSMContext):
    if len(message.text) > 100:
        await message.answer("❗ El nombre de la ubicación es demasiado largo. Por favor, que no exceda 100 caracteres.")
        return
    await state.update_data(location_name=message.text)
    await state.update_data(location_latitude=None, location_longitude=None) # Asegurarse que no hay coords si es texto
    await state.set_state(Form.contact)
    await message.answer(
        "¡Excelente! Ahora, ingresa tu usuario de Telegram para contacto. (Ej: @tu_usuario) o tu número de teléfono.",
        reply_markup=None
    )


@dp.message(Form.contact)
async def process_contact(message: Message, state: FSMContext):
    contact_info = message.text.strip()
    if not contact_info:
        await message.answer("❗ Por favor, ingrese su información de contacto.")
        return
    if len(contact_info) > 100:
        await message.answer("❗ La información de contacto es demasiado larga. Por favor, que no exceda 100 caracteres.")
        return
    await state.update_data(contact=contact_info)
    await state.set_state(Form.terms_agreed)
    await message.answer(
        "Antes de publicar, por favor, acepta nuestros términos y condiciones: [enlace a T&C](https://telegra.ph/T%C3%A9rminos-y-Condiciones-05-18) (Este es un ejemplo, reemplázalo con tus T&C reales).\n\n"
        "¿Aceptas los términos y condiciones?",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="✅ Acepto los términos")]],
            resize_keyboard=True, one_time_keyboard=True
        )
    )

@dp.message(Form.terms_agreed, F.text == "✅ Acepto los términos")
async def process_terms_agreed(message: Message, state: FSMContext):
    data = await state.get_data()
    
    # Generar un ID único para el anuncio
    listing_id = generate_listing_id()
    
    # Guardar todos los datos del formulario junto con el ID del usuario y la fecha
    listings[listing_id] = {
        'user_id': message.from_user.id,
        'username': message.from_user.username,
        'full_name': message.from_user.full_name,
        'published_at': datetime.datetime.now().isoformat(), # Fecha de publicación
        'status': 'active', # Estado inicial del anuncio
        **data # Desempaquetar todos los datos del formulario
    }
    
    # Establecer duración por defecto a 3 дня
    listings[listing_id]['expires_at'] = datetime.datetime.now() + datetime.timedelta(days=3)

    await save_listings() # Guardar los anuncios

    await state.set_state(Form.confirm_publish)
    await display_item_card(message.from_user.id, listing_id, caller_is_edit=False) # Mostrar el anuncio creado

    await message.answer(
        "¡Tu anuncio está casi listo! Confirma para publicarlo o puedes editarlo.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Publicar Anuncio", callback_data=f"publish_confirm:{listing_id}")],
            [InlineKeyboardButton(text="📝 Editar Anuncio", callback_data=f"edit_listing:{listing_id}")]
        ])
    )
    logger.info(f"📝 Anuncio {listing_id} creado por {message.from_user.id}, esperando confirmación.")

@dp.message(Form.terms_agreed)
async def process_terms_invalid(message: Message):
    await message.answer("❗ Por favor, debe aceptar los términos para continuar.")

@dp.callback_query(F.data.startswith("publish_confirm:"))
async def confirm_publish_listing(callback_query: CallbackQuery, state: FSMContext):
    await callback_query.answer()
    listing_id = callback_query.data.split(":")[1]

    if listing_id not in listings:
        await bot.send_message(callback_query.from_user.id, "❗ Anuncio no encontrado o ya publicado.")
        await state.clear()
        await callback_query.message.delete_reply_markup()
        return

    # Aquí podríamos hacer algo con el estado 'confirm_publish' si fuera necesario,
    # pero como ya está todo en `listings`, solo confirmamos.
    listings[listing_id]['status'] = 'active' # Aseguramos que el estado es activo
    await save_listings()

    await bot.send_message(
        callback_query.from_user.id,
        f"✅ ¡Tu anuncio #{listing_id} ha sido publicado exitosamente!\n"
        "Puedes verlo en '🔍 Mis Anuncios'.",
        reply_markup=main_keyboard if callback_query.from_user.id != ADMIN_ID else get_main_keyboard_admin()
    )
    await callback_query.message.delete_reply_markup() # Eliminar botones de confirmación
    await state.clear()
    logger.info(f"✅ Anuncio {listing_id} publicado por {callback_query.from_user.id}.")

# ------------------------------ Mis Anuncios ------------------------------

@dp.message(F.text == "🔍 Mis Anuncios")
@dp.callback_query(F.data == "my_listings")
async def show_my_listings(update: Message | CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = update.from_user.id
    user_listings = {lid: info for lid, info in listings.items() if info.get('user_id') == user_id}

    if isinstance(update, CallbackQuery):
        await update.answer()
        # await update.message.delete_reply_markup() # Opcional: удалить предыдущие кнопки

    if not user_listings:
        if isinstance(update, Message):
            await update.answer("No tienes anuncios publicados aún. ¡Publica uno con '➕ Publicar Anuncio'!", reply_markup=main_keyboard)
        else: # CallbackQuery
            await update.message.answer("No tienes anuncios publicados aún. ¡Publica uno con '➕ Publicar Anuncio'!", reply_markup=main_keyboard)
        logger.info(f"➡️ Usuario {user_id} no tiene anuncios.")
        return

    message_text = "Mis anuncios:\n"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])

    sorted_listings = sorted(user_listings.items(), key=lambda item: item[1].get('published_at', ''), reverse=True)

    for listing_id, info in sorted_listings:
        title = escape(info.get('title', 'N/A'))
        status_icon = "🟢" if info.get('status') == 'active' else "🔴" # Añadir icono de estado
        message_text += f"{status_icon} Anuncio #{listing_id}: {title}\n"
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(text=f"Ver Anuncio #{listing_id}", callback_data=f"view_listing_edit:{listing_id}")
        ])
    
    keyboard.inline_keyboard.append([InlineKeyboardButton(text="⬅️ Menú Principal", callback_data="back_to_main")])

    if isinstance(update, Message):
        await update.answer(message_text, reply_markup=keyboard)
    else: # CallbackQuery
        try:
            await update.message.edit_text(message_text, reply_markup=keyboard)
        except TelegramBadRequest: # Si el texto no cambió, solo actualizar el markup
            await update.message.answer(message_text, reply_markup=keyboard) # Enviar como nuevo mensaje si falla la edición
    logger.info(f"➡️ Usuario {user_id} vio sus anuncios.")

@dp.callback_query(F.data.startswith("view_listing_edit:"))
async def view_listing_from_edit(callback_query: CallbackQuery):
    await callback_query.answer()
    listing_id = callback_query.data.split(":")[1]
    await display_item_card(callback_query.from_user.id, listing_id, caller_is_edit=True)
    logger.info(f"➡️ Usuario {callback_query.from_user.id} viendo anuncio {listing_id} para edición.")


# ------------------------------ Edición de Anuncios ------------------------------

@dp.callback_query(F.data.startswith("edit_listing:"))
async def edit_listing(callback_query: CallbackQuery, state: FSMContext):
    await callback_query.answer()
    listing_id = callback_query.data.split(":")[1]
    
    if listing_id not in listings or listings[listing_id]['user_id'] != callback_query.from_user.id:
        if callback_query.from_user.id != ADMIN_ID: # Проверка админа
            await bot.send_message(callback_query.from_user.id, "❗ No tienes permiso para editar este anuncio.")
            return

    await state.update_data(selected_item_id=listing_id)
    await state.set_state(Form.edit_field)
    await callback_query.message.answer(
        f"¿Qué campo del anuncio #{listing_id} deseas editar?",
        reply_markup=get_edit_field_keyboard(listing_id)
    )
    logger.info(f"➡️ Usuario {callback_query.from_user.id} inició edición del anuncio {listing_id}.")


@dp.callback_query(F.data.startswith("edit_field_type:"))
async def ask_for_edit_value(callback_query: CallbackQuery, state: FSMContext):
    await callback_query.answer()
    _, listing_id, field_type = callback_query.data.split(":")
    
    await state.update_data(selected_item_id=listing_id, field_to_edit=field_type)

    if field_type == 'title':
        await state.set_state(Form.edit_title)
        await callback_query.message.answer(f"Ingresa el nuevo título para el anuncio #{listing_id}:")
    elif field_type == 'description':
        await state.set_state(Form.edit_description)
        await callback_query.message.answer(f"Ingresa la nueva descripción para el anuncio #{listing_id}:")
    elif field_type == 'category':
        await state.set_state(Form.edit_category)
        await callback_query.message.answer(
            f"Selecciona la nueva categoría para el anuncio #{listing_id}:",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="📱 Electrónica"), KeyboardButton(text="👗 Moda")],
                    [KeyboardButton(text="🏡 Hogar"), KeyboardButton(text="🚗 Vehículos")],
                    [KeyboardButton(text="📚 Libros"), KeyboardButton(text="🏀 Deportes")],
                    [KeyboardButton(text="💼 Servicios"), KeyboardButton(text="✨ Otros")]
                ],
                resize_keyboard=True, one_time_keyboard=True
            )
        )
    elif field_type == 'price':
        await state.set_state(Form.edit_price)
        await callback_query.message.answer(f"Ingresa el nuevo precio para el anuncio #{listing_id}: (Ej: '150.50' o 'Negociable')")
    elif field_type == 'photos':
        await state.update_data(photos=[]) # Resetear fotos para una nueva carga
        await state.set_state(Form.edit_photos)
        await callback_query.message.answer(
            f"Envía hasta 10 fotos nuevas para el anuncio #{listing_id}. Cuando termines, envía 'Listo'.\n"
            "Las fotos anteriores serán reemplazadas.",
            reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Listo")]], resize_keyboard=True)
        )
    elif field_type == 'location':
        await state.set_state(Form.edit_location)
        await callback_query.message.answer(
            f"Ingresa la nueva ubicación o comparte tu ubicación actual para el anuncio #{listing_id}:",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="Compartir mi ubicación actual", request_location=True)]],
                resize_keyboard=True, one_time_keyboard=True
            )
        )
    elif field_type == 'contact':
        await state.set_state(Form.edit_contact)
        await callback_query.message.answer(f"Ingresa la nueva información de contacto para el anuncio #{listing_id}: (Ej: @tu_usuario o tu número)")
    logger.info(f"➡️ Usuario {callback_query.from_user.id} seleccionó editar {field_type} para anuncio {listing_id}.")


# Handlers para los campos de edición específicos
@dp.message(Form.edit_title)
async def process_edit_title(message: Message, state: FSMContext):
    if len(message.text) > 100:
        await message.answer("❗ El título es demasiado largo. Por favor, que no exceda 100 caracteres.")
        return
    data = await state.get_data()
    listing_id = data.get('selected_item_id')
    listings[listing_id]['title'] = message.text
    await save_listings()
    logger.info(f"✅ Usuario {message.from_user.id} editó el título del artículo {listing_id}.")
    await display_item_card(message.from_user.id, listing_id, caller_is_edit=True)
    await state.clear()

@dp.message(Form.edit_description)
async def process_edit_description(message: Message, state: FSMContext):
    if len(message.text) > 1000:
        await message.answer("❗ La descripción es demasiado larga. Por favor, que no exceda 1000 caracteres.")
        return
    data = await state.get_data()
    listing_id = data.get('selected_item_id')
    listings[listing_id]['description'] = message.text
    await save_listings()
    logger.info(f"✅ Usuario {message.from_user.id} editó la descripción del artículo {listing_id}.")
    await display_item_card(message.from_user.id, listing_id, caller_is_edit=True)
    await state.clear()

@dp.message(Form.edit_category, F.text.in_({"📱 Electrónica", "👗 Moda", "🏡 Hogar", "🚗 Vehículos", "📚 Libros", "🏀 Deportes", "💼 Servicios", "✨ Otros"}))
async def process_edit_category(message: Message, state: FSMContext):
    data = await state.get_data()
    listing_id = data.get('selected_item_id')
    listings[listing_id]['category'] = message.text
    await save_listings()
    logger.info(f"✅ Usuario {message.from_user.id} editó la categoría del artículo {listing_id}.")
    await display_item_card(message.from_user.id, listing_id, caller_is_edit=True)
    await state.clear()

@dp.message(Form.edit_category)
async def process_edit_category_invalid(message: Message):
    await message.answer("❗ Por favor, seleccione una categoría de la lista.")

@dp.message(Form.edit_price)
async def process_edit_price(message: Message, state: FSMContext):
    price_text = message.text.replace(',', '.').strip()
    if price_text.lower() == 'negociable':
        data = await state.get_data()
        listing_id = data.get('selected_item_id')
        listings[listing_id]['price'] = 'Negociable'
    else:
        try:
            price = float(price_text)
            if price <= 0:
                raise ValueError
            data = await state.get_data()
            listing_id = data.get('selected_item_id')
            listings[listing_id]['price'] = f"{price:.2f}"
        except ValueError:
            await message.answer("❗ Formato de precio inválido. Por favor, introduzca un número (ej: '150.50') o 'Negociable'.")
            return
    await save_listings()
    logger.info(f"✅ Usuario {message.from_user.id} editó el precio del artículo {listing_id}.")
    await display_item_card(message.from_user.id, listing_id, caller_is_edit=True)
    await state.clear()

@dp.message(Form.edit_photos, F.photo)
async def process_edit_photos(message: Message, state: FSMContext):
    data = await state.get_data()
    photos = data.get('photos', [])
    
    if len(photos) >= 10:
        await message.answer("❗ Ya tienes el máximo de 10 fotos. Por favor, envía 'Listo'.")
        return
    
    file_id = message.photo[-1].file_id
    photos.append(file_id)
    await state.update_data(photos=photos)
    await message.answer(f"✅ Foto añadida. Tienes {len(photos)}/{10} fotos. Envía más o 'Listo'.")

@dp.message(Form.edit_photos, F.text == "Listo")
async def process_edit_photos_done(message: Message, state: FSMContext):
    data = await state.get_data()
    listing_id = data.get('selected_item_id')
    photos = data.get('photos', [])

    if not photos:
        await message.answer("❗ Por favor, envía al menos una foto antes de continuar con la edición de fotos.")
        return
    
    listings[listing_id]['photos'] = photos # Reemplazar fotos existentes
    await save_listings()
    logger.info(f"✅ Usuario {message.from_user.id} editó las fotos del artículo {listing_id}.")
    await display_item_card(message.from_user.id, listing_id, caller_is_edit=True)
    await state.clear()

@dp.message(Form.edit_location, F.location)
async def process_edit_location_by_coords(message: Message, state: FSMContext):
    data = await state.get_data()
    listing_id = data.get('selected_item_id')
    listings[listing_id]['location_latitude'] = message.location.latitude
    listings[listing_id]['location_longitude'] = message.location.longitude
    listings[listing_id]['location_name'] = "Ubicación compartida por GPS"
    await save_listings()
    logger.info(f"✅ Usuario {message.from_user.id} editó la ubicación (GPS) del artículo {listing_id}.")
    await display_item_card(message.from_user.id, listing_id, caller_is_edit=True)
    await state.clear()

@dp.message(Form.edit_location)
async def process_edit_location_by_text(message: Message, state: FSMContext):
    if len(message.text) > 100:
        await message.answer("❗ El nombre de la ubicación es demasiado largo. Por favor, que no exceda 100 caracteres.")
        return
    data = await state.get_data()
    listing_id = data.get('selected_item_id')
    listings[listing_id]['location_name'] = message.text
    listings[listing_id]['location_latitude'] = None # Resetear coords si se usa texto
    listings[listing_id]['location_longitude'] = None
    await save_listings()
    logger.info(f"✅ Usuario {message.from_user.id} editó la ubicación (texto) del artículo {listing_id}.")
    await display_item_card(message.from_user.id, listing_id, caller_is_edit=True)
    await state.clear()

@dp.message(Form.edit_contact)
async def process_edit_contact(message: Message, state: FSMContext):
    contact_info = message.text.strip()
    if not contact_info:
        await message.answer("❗ Por favor, ingrese su información de contacto.")
        return
    if len(contact_info) > 100:
        await message.answer("❗ La información de contacto es demasiado larga. Por favor, que no exceda 100 caracteres.")
        return
    data = await state.get_data()
    listing_id = data.get('selected_item_id')
    listings[listing_id]['contact'] = contact_info
    await save_listings()
    logger.info(f"✅ Usuario {message.from_user.id} editó el contacto del artículo {listing_id}.")
    await display_item_card(message.from_user.id, listing_id, caller_is_edit=True)
    await state.clear()

# ------------------------------ Eliminar Anuncios ------------------------------

@dp.callback_query(F.data.startswith("delete_listing:"))
async def confirm_delete_listing(callback_query: CallbackQuery, state: FSMContext):
    await callback_query.answer()
    listing_id = callback_query.data.split(":")[1]
    
    if listing_id not in listings or (listings[listing_id]['user_id'] != callback_query.from_user.id and callback_query.from_user.id != ADMIN_ID):
        await bot.send_message(callback_query.from_user.id, "❗ No tienes permiso para eliminar este anuncio.")
        return

    await state.update_data(selected_item_id=listing_id)
    await state.set_state(Form.confirm_delete)
    await callback_query.message.answer(
        f"¿Estás seguro de que quieres eliminar el anuncio #{listing_id}?",
        reply_markup=get_confirm_delete_keyboard(listing_id)
    )
    logger.info(f"➡️ Usuario {callback_query.from_user.id} inició proceso de eliminación para anuncio {listing_id}.")

@dp.callback_query(F.data.startswith("confirm_delete_yes:"))
async def execute_delete_listing(callback_query: CallbackQuery, state: FSMContext):
    await callback_query.answer()
    listing_id = callback_query.data.split(":")[1]

    if listing_id not in listings or (listings[listing_id]['user_id'] != callback_query.from_user.id and callback_query.from_user.id != ADMIN_ID):
        await bot.send_message(callback_query.from_user.id, "❗ No tienes permiso para eliminar este anuncio o ya fue eliminado.")
        await state.clear()
        return

    del listings[listing_id]
    await save_listings()
    await state.clear()
    await callback_query.message.edit_text(f"✅ Anuncio #{listing_id} eliminado exitosamente.")
    logger.info(f"❌ Usuario {callback_query.from_user.id} eliminó el anuncio {listing_id}.")
    
    # Después de eliminar, mostrar mis anuncios o menú principal
    await show_my_listings(callback_query, state) # Intenta mostrar список объявлений

@dp.callback_query(F.data.startswith("confirm_delete_no:"))
async def cancel_delete_listing(callback_query: CallbackQuery, state: FSMContext):
    await callback_query.answer()
    listing_id = callback_query.data.split(":")[1]
    await state.clear()
    await callback_query.message.edit_text(f"🚫 Eliminación del anuncio #{listing_id} cancelada.")
    logger.info(f"🚫 Usuario {callback_query.from_user.id} canceló eliminación del anuncio {listing_id}.")
    await display_item_card(callback_query.from_user.id, listing_id, caller_is_edit=True) # Mostrar снова карточку


# ------------------------------ Establecer vigencia ------------------------------

@dp.callback_query(F.data.startswith("set_duration:"))
async def set_duration_start(callback_query: CallbackQuery, state: FSMContext):
    await callback_query.answer()
    listing_id = callback_query.data.split(":")[1]
    
    if listing_id not in listings or (listings[listing_id]['user_id'] != callback_query.from_user.id and callback_query.from_user.id != ADMIN_ID):
        await bot.send_message(callback_query.from_user.id, "❗ No tienes permiso para editar este anuncio.")
        return

    await state.update_data(selected_item_id=listing_id)
    await state.set_state(Form.set_duration)
    await callback_query.message.answer(
        f"Selecciona la nueva vigencia para el anuncio #{listing_id}:",
        reply_markup=get_expires_at_keyboard()
    )
    logger.info(f"➡️ Usuario {callback_query.from_user.id} inició configuración de vigencia para anuncio {listing_id}.")

@dp.message(Form.set_duration, F.text.in_({"📅 3 días", "📅 5 días", "🗓️ Sin fecha de caducidad"}))
async def process_set_duration(message: Message, state: FSMContext):
    days = None
    if "3 días" in message.text:
        days = 3
    elif "5 días" in message.text:
        days = 5
    elif "Sin fecha de caducidad" in message.text:
        days = 0 # Usamos 0 para indicar sin expiración
    else:
        # Это не должно произойти, так как мы проверяем на F.text.in_
        await message.answer(
            "❗ Por favor, seleccione '📅 3 días', '📅 5 días' o '🗓️ Sin fecha de caducidad'.",
            reply_markup=get_expires_at_keyboard()
        )
        return

    data = await state.get_data()
    listing_id = data.get('selected_item_id')

    if days == 0:
        listings[listing_id]['expires_at'] = None # Удаляем срок действия
    else:
        expires_at = datetime.datetime.now() + datetime.timedelta(days=days)
        listings[listing_id]['expires_at'] = expires_at

    await save_listings()

    logger.info(f"✅ Usuario {message.from_user.id} editó la vigencia del artículo {listing_id}.")
    await display_item_card(message.from_user.id, listing_id, caller_is_edit=True)
    await state.clear()


@dp.message(Form.set_duration)
async def process_set_duration_invalid(message: Message):
    await message.answer(
        "❗ Por favor, seleccione '📅 3 días', '📅 5 días' o '🗓️ Sin fecha de caducidad'.",
        reply_markup=get_expires_at_keyboard()
    )


# ------------------------------ Admin Panel ------------------------------

@dp.message(F.text == "📊 Admin Panel")
async def show_admin_panel(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❗ No tienes permiso para acceder al panel de administración.")
        logger.warning(f"⚠️ Intento de acceso no autorizado al panel de administración por el usuario {message.from_user.id}.")
        return
    
    await state.clear()
    
    total_users = len(users_data)
    total_listings = len(listings)
    active_listings = sum(1 for li in listings.values() if li.get('status') == 'active')

    message_text = (
        "📊 Panel de Administración\n\n"
        f"Total de usuarios: {total_users}\n"
        f"Total de anuncios: {total_listings}\n"
        f"Anuncios activos: {active_listings}\n\n"
        "Seleccione una acción:"
    )

    admin_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Ver Usuarios", callback_data="admin_view_users")],
        [InlineKeyboardButton(text="📄 Ver Todos los Anuncios", callback_data="admin_view_all_listings")],
        [InlineKeyboardButton(text="⬅️ Menú Principal", callback_data="back_to_main")]
    ])
    await message.answer(message_text, reply_markup=admin_keyboard)
    logger.info(f"➡️ Usuario {message.from_user.id} accedió al Panel de Administración.")

@dp.callback_query(F.data == "back_to_admin_panel")
async def back_to_admin_panel_callback(callback_query: CallbackQuery, state: FSMContext):
    await callback_query.answer()
    await show_admin_panel(callback_query.message, state)


@dp.callback_query(F.data == "admin_view_users")
async def admin_view_users(callback_query: CallbackQuery):
    if callback_query.from_user.id != ADMIN_ID:
        await callback_query.answer("❗ No tienes permiso.", show_alert=True)
        return
    await callback_query.answer()

    if not users_data:
        await callback_query.message.edit_text("No hay usuarios registrados aún.")
        return

    message_text = "👥 Usuarios Registrados:\n\n"
    for user_id, info in users_data.items():
        username = info.get('username', 'N/A')
        full_name = info.get('full_name', 'N/A')
        first_access = info.get('first_access', 'N/A')
        message_text += (
            f"ID: <code>{user_id}</code>\n"
            f"Nombre: {escape(full_name)}\n"
            f"Usuario: @{escape(username) if username else 'N/A'}\n"
            f"Primer acceso: {first_access}\n\n"
        )
    
    await callback_query.message.edit_text(message_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Volver al Panel Admin", callback_data="back_to_admin_panel")]
    ]))
    logger.info(f"➡️ Admin {callback_query.from_user.id} vio la lista de usuarios.")

@dp.callback_query(F.data == "admin_view_all_listings")
async def admin_view_all_listings(callback_query: CallbackQuery):
    if callback_query.from_user.id != ADMIN_ID:
        await callback_query.answer("❗ No tienes permiso.", show_alert=True)
        return
    await callback_query.answer()

    if not listings:
        await callback_query.message.edit_text("No hay anuncios publicados aún.")
        return

    message_text = "📄 Todos los Anuncios:\n\n"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])

    sorted_listings = sorted(listings.items(), key=lambda item: item[1].get('published_at', ''), reverse=True)

    for listing_id, info in sorted_listings:
        title = escape(info.get('title', 'N/A'))
        status_icon = "🟢" if info.get('status') == 'active' else "🔴" 
        message_text += f"{status_icon} Anuncio #{listing_id}: {title} (Usuario: {info.get('user_id')})\n"
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(text=f"Ver Anuncio #{listing_id}", callback_data=f"admin_view_listing:{listing_id}")
        ])
    
    keyboard.inline_keyboard.append([InlineKeyboardButton(text="⬅️ Volver al Panel Admin", callback_data="back_to_admin_panel")])

    await callback_query.message.edit_text(message_text, reply_markup=keyboard)
    logger.info(f"➡️ Admin {callback_query.from_user.id} vio todos los anuncios.")


@dp.callback_query(F.data.startswith("admin_view_listing:"))
async def admin_view_listing_details(callback_query: CallbackQuery):
    if callback_query.from_user.id != ADMIN_ID:
        await callback_query.answer("❗ No tienes permiso.", show_alert=True)
        return
    await callback_query.answer()
    listing_id = callback_query.data.split(":")[1]
    await display_item_card(callback_query.from_user.id, listing_id, is_admin_view=True)
    logger.info(f"➡️ Admin {callback_query.from_user.id} viendo detalles de anuncio {listing_id}.")


# ------------------------------ Navegación general ------------------------------

@dp.callback_query(F.data == "back_to_main")
async def back_to_main_menu(callback_query: CallbackQuery, state: FSMContext):
    await callback_query.answer()
    await state.clear()
    await callback_query.message.edit_text(
        "Volviendo al menú principal.",
        reply_markup=main_keyboard if callback_query.from_user.id != ADMIN_ID else get_main_keyboard_admin()
    )
    logger.info(f"➡️ Usuario {callback_query.from_user.id} volvió al menú principal.")


@dp.message(F.text == "⚙️ Configuración")
async def show_settings(message: Message):
    await message.answer("🛠️ Opciones de configuración (funcionalidad no implementada): \n- Idioma \n- Notificaciones",
                         reply_markup=main_keyboard if message.from_user.id != ADMIN_ID else get_main_keyboard_admin())
    logger.info(f"➡️ Usuario {message.from_user.id} vio las opciones de configuración.")


@dp.message()
async def handle_unprocessed(message: Message, state: FSMContext):
    if message.from_user.is_bot:
        logger.warning(f"⚠️ Ignorando mensaje no procesado de bot: user_id={message.from_user.id}")
        return
    logger.warning(f"⚠️ Mensaje no procesado del usuario {message.from_user.id}: '{message.text}'")
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("❗ Acción no reconocida. Seleccione una opción del menú:", 
                             reply_markup=main_keyboard if message.from_user.id != ADMIN_ID else get_main_keyboard_admin())
    else:
        await message.answer(f"❗ Acción no reconocida. Por favor, continúe con el proceso actual o use /cancel para reiniciar.")


# --- ДОБАВЛЕНО/ИЗМЕНЕНО ДЛЯ ВЕБХУКОВ С AIOHTTP ---
async def on_startup_webhook(dispatcher: Dispatcher, bot: Bot):
    logger.info("🚀 Bot is starting with webhooks (aiohttp)...")
    print(f"WEBHOOK_URL: {WEBHOOK_URL}")
    print(f"WEBAPP_HOST: {WEBAPP_HOST}")
    print(f"WEBAPP_PORT: {WEBAPP_PORT}")
    # Удаляем старый вебхук на всякий случай
    await bot.delete_webhook(drop_pending_updates=True)
    # Установка нового вебхука
    await bot.set_webhook(WEBHOOK_URL, secret_token=WEBHOOK_SECRET) # <-- ЭТА СТРОКА ИЗМЕНЕНА
    logger.info("✅ Webhook set successfully.")
    if ADMIN_ID:
        try:
            await bot.send_message(ADMIN_ID, "✅ Бот успешно запущен и готов к работе!")
        except Exception as e:
            logger.error(f"❌ Не удалось отправить сообщение администратору о запуске: {e}")

async def on_shutdown_webhook(dispatcher: Dispatcher, bot: Bot):
    logger.info("🔴 Bot is shutting down, deleting webhook...")
    await bot.delete_webhook()
    logger.info("🗑️ Webhook deleted.")
    if ADMIN_ID:
        try:
            await bot.send_message(ADMIN_ID, "🔴 Бот остановлен.")
        except Exception as e:
            logger.error(f"❌ Не удалось отправить сообщение администратору об остановке: {e}")


# Функция main теперь не асинхронная, так как web.run_app() блокирующая
def main():
    logger.info("🚀 Iniciando la función principal...")
    # Загружаем данные при старте (нужно сделать их синхронными или вызвать asyncio.run внутри)
    # Так как load_user_data и load_listings асинхронные, их нужно выполнить до запуска веб-сервера
    asyncio.run(load_user_data())
    asyncio.run(load_listings())

    # Создаем веб-приложение aiohttp
    app = web.Application()

    # Регистрируем обработчик вебхуков
    webhook_requests_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        secret_token=WEBHOOK_SECRET # <-- ЭТА СТРОКА ИЗМЕНЕНА
    )
    # Путь для вебхука должен быть уникальным и содержать токен для безопасности
    webhook_requests_handler.register(app, path=f"/webhook/{WEBHOOK_SECRET}") # <-- ЭТА СТРОКА ИЗМЕНЕНА

    # Устанавливаем функции on_startup и on_shutdown для aiohttp приложения
    app.on_startup.append(lambda app: on_startup_webhook(dp, bot))
    app.on_shutdown.append(lambda app: on_shutdown_webhook(dp, bot))

    # Запускаем веб-приложение
    logger.info(f"🚀 Запускаем веб-сервер на {WEBAPP_HOST}:{WEBAPP_PORT}")
    web.run_app(app, host=WEBAPP_HOST, port=WEBAPP_PORT)


if __name__ == '__main__':
    main() # main() теперь синхронная