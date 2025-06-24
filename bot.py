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

# 📝 Logging configuration
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[logging.StreamHandler()])
logger = logging.getLogger(__name__)

# 🔧 Load environment variables
load_dotenv()
API_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")

if not API_TOKEN:
    logger.error("❌ BOT_TOKEN not set in environment variables.")
    exit(1)
if not ADMIN_ID:
    logger.error("❌ ADMIN_ID not set in environment variables.")
    exit(1)
try:
    ADMIN_ID = int(ADMIN_ID)
except ValueError:
    logger.error("❌ ADMIN_ID is not a valid integer.")
    exit(1)

# 🤖 Bot and Dispatcher initialization
bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())

# 📊 Global data structures
user_data = {}
listings = {}
categories = [
    "📦 ¡Kit de mudanza!", "🛋️ Muebles", "📱 Electrónica", "👗 Ropa", "👜 Accesorios",
    "📚 Libros", "🧸 Juguetes", "🔌 Electrodomésticos", "🏀 Deportes", "🌟 Otros"
]
cities = [
    "Quito", "Guayaquil", "Cuenca", "Santo Domingo", "Manta",
    "Portoviejo", "Ambato", "Riobamba", "Loja", "Ibarra",
    "Esmeraldas", "Babahoyo", "Latacunga", "Machala", "Quevedo",
    "Tulcán", "Salinas", "Baños", "Montañita", "Otavalo",
    "Puyo", "Tena", "Atacames", "San Vicente"
]
city_mapping = {city: city for city in cities}

# ⌨️ Keyboards
cancel_keyboard = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="❌ Cancelar")]],
    resize_keyboard=True
)

main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🧳 Dejar objetos"), KeyboardButton(text="🔍 Buscar objeto")],
        [KeyboardButton(text="📋 Mis anuncios")]
    ],
    resize_keyboard=True
)

def get_categories_keyboard(is_search=False):
    if is_search:
        counts = count_listings_by_category()
        keyboard = []
        row = []
        row.append(InlineKeyboardButton(text=f"♾ Solo Gratis ({counts.get('Gratis', 0)})", callback_data="search_category_Gratis"))
        keyboard.append(row)
        row = []
        for i, category in enumerate(categories):
            button_text = f"{category} ({counts.get(category.replace('📦 ', '').replace('🛋️ ', '').replace('📱 ', '').replace('👗 ', '').replace('👜 ', '').replace('📚 ', '').replace('🧸 ', '').replace('🔌 ', '').replace('🏀 ', '').replace('🌟 ', ''), 0)})"
            row.append(InlineKeyboardButton(text=button_text, callback_data=f"search_category_{category.replace('📦 ', '').replace('🛋️ ', '').replace('📱 ', '').replace('👗 ', '').replace('👜 ', '').replace('📚 ', '').replace('🧸 ', '').replace('🔌 ', '').replace('🏀 ', '').replace('🌟 ', '')}"))
            if (i + 1) % 2 == 0 or i == len(categories) - 1:
                keyboard.append(row)
                row = []
        keyboard.append([InlineKeyboardButton(text="⏭️ Omitir", callback_data="search_skip_category")])
        keyboard.append([InlineKeyboardButton(text="❌ Cancelar", callback_data="cancel")])
        return InlineKeyboardMarkup(inline_keyboard=keyboard)
    else:
        keyboard = [[KeyboardButton(text=category)] for category in categories]
        keyboard.append([KeyboardButton(text="❌ Cancelar")])
        return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_cities_keyboard():
    counts = count_listings_by_city()
    keyboard = []
    row = []
    for i, city in enumerate(cities):
        button_text = f"📍 {city} ({counts.get(city_mapping[city], 0)})"
        row.append(InlineKeyboardButton(text=button_text, callback_data=f"search_city_{city}"))
        if (i + 1) % 2 == 0 or i == len(cities) - 1:
            keyboard.append(row)
            row = []
    keyboard.append([InlineKeyboardButton(text="⏭️ Omitir", callback_data="search_skip_city")])
    keyboard.append([InlineKeyboardButton(text="❌ Cancelar", callback_data="cancel")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_expires_at_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📅 3 días"), KeyboardButton(text="📅 5 días")],
            [KeyboardButton(text="❌ Cancelar")]
        ],
        resize_keyboard=True
    )

def get_skip_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="⏭️ Omitir")],
            [KeyboardButton(text="❌ Cancelar")]
        ],
        resize_keyboard=True
    )

def get_location_type_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏙️ Solo ciudad")],
            [KeyboardButton(text="📍 Enviar geolocalización", request_location=True)],
            [KeyboardButton(text="❌ Cancelar")]
        ],
        resize_keyboard=True
    )

def get_edit_fields_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📋 Categoría"), KeyboardButton(text="✏️ Título")],
            [KeyboardButton(text="💰 Precio"), KeyboardButton(text="📸 Foto principal")],
            [KeyboardButton(text="📷 Fotos adicionales"), KeyboardButton(text="📝 Descripción")],
            [KeyboardButton(text="🏙️ Ciudad"), KeyboardButton(text="📍 Geolocalización")],
            [KeyboardButton(text="📞 Contacto"), KeyboardButton(text="📅 Vigencia")],
            [KeyboardButton(text="❌ Cancelar")]
        ],
        resize_keyboard=True
    )

def get_confirm_delete_keyboard(listing_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Sí", callback_data=f"confirm_delete_{listing_id}")],
        [InlineKeyboardButton(text="❌ No", callback_data="cancel")]
    ])

def get_item_card_keyboard(caller_is_search=False, caller_is_edit=False, current_index=0, total_results=0, listing_id=None):
    keyboard_buttons = []
    if caller_is_search:
        if total_results > 1:
            nav_buttons = []
            if current_index > 0:
                nav_buttons.append(InlineKeyboardButton(text="⬅️ Anterior", callback_data=f"search_prev_{current_index}"))
            if current_index < total_results - 1:
                nav_buttons.append(InlineKeyboardButton(text="Siguiente ➡️", callback_data=f"search_next_{current_index}"))
            if nav_buttons:
                keyboard_buttons.append(nav_buttons)
        keyboard_buttons.append([InlineKeyboardButton(text="🔙 Volver a resultados de búsqueda", callback_data="back_to_search_results")])
    elif caller_is_edit:
        keyboard_buttons.append([InlineKeyboardButton(text="🔄 Editar nuevamente", callback_data=f"edit_item_{listing_id}")])
        keyboard_buttons.append([InlineKeyboardButton(text="🗑 Eliminar", callback_data=f"delete_item_{listing_id}")])
    keyboard_buttons.append([InlineKeyboardButton(text="❌ Cancelar", callback_data="cancel")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

# 📋 States
class ItemForm(StatesGroup):
    item_category = State()
    item_title = State()
    item_description = State()
    item_photo = State()
    item_additional_photos = State()
    item_price_value = State()
    item_city = State()
    item_ask_geolocation = State()
    item_geolocation = State()
    item_contact = State()
    item_expires_at = State()

class EditForm(StatesGroup):
    select_item = State()
    choose_field = State()
    edit_category = State()
    edit_title = State()
    edit_description = State()
    edit_photo = State()
    edit_additional_photos = State()
    edit_price_value = State()
    edit_location_type = State()
    edit_city = State()
    edit_ask_geolocation = State()
    edit_geolocation = State()
    edit_contact = State()
    edit_expires_at = State()

class SearchForm(StatesGroup):
    keyword = State()
    category = State()
    city = State()

# 💾 Data handling functions
async def load_user_data():
    try:
        if os.path.exists('user_data.json'):
            with open('user_data.json', 'r', encoding='utf-8') as f:
                global user_data
                user_data = json.load(f)
                user_data = {int(k): v for k, v in user_data.items()}
            logger.info("✅ User data loaded successfully.")
        else:
            logger.info("ℹ️ user_data.json not found, starting with empty user_data.")
    except json.JSONDecodeError as e:
        logger.error(f"❌ JSON decode error in user_data.json: {e}")
        user_data = {}
    except Exception as e:
        logger.error(f"❌ Failed to load user_data: {e}")
        user_data = {}

async def save_user_data():
    try:
        with open('user_data.json', 'w', encoding='utf-8') as f:
            json.dump(user_data, f, ensure_ascii=False, indent=4, default=str)
        logger.debug("💾 User data saved.")
    except Exception as e:
        logger.error(f"❌ Failed to save user_data: {e}")

async def load_listings():
    try:
        if os.path.exists('listings.json'):
            with open('listings.json', 'r', encoding='utf-8') as f:
                global listings
                loaded_listings = json.load(f)
                listings = {}
                for k, v in loaded_listings.items():
                    try:
                        if v['category'] == "Calzado":
                            logger.info(f"ℹ️ Skipping listing {k} with category 'Calzado'")
                            if v['user_id'] in user_data and k in user_data[v['user_id']]['listings']:
                                user_data[v['user_id']]['listings'].remove(k)
                            continue
                        city = v.get('city')
                        if city in city_mapping.values():
                            v['city'] = city
                        else:
                            for short, full in city_mapping.items():
                                if city == short:
                                    v['city'] = full
                                    break
                        posted_at = datetime.datetime.fromisoformat(v['posted_at'].replace('Z', '+00:00'))
                        expires_at = datetime.datetime.fromisoformat(v['expires_at'].replace('Z', '+00:00'))
                        if 'is_free' not in v:
                            v['is_free'] = v['status'] == 'free'
                        listings[k] = {
                            **v,
                            'posted_at': posted_at,
                            'expires_at': expires_at
                        }
                    except (ValueError, KeyError) as e:
                        logger.warning(f"⚠️ Skipping invalid listing {k}: {e}")
                        continue
            await save_user_data()
            logger.info("✅ Listings loaded successfully.")
        else:
            logger.info("ℹ️ listings.json not found, starting with empty listings.")
    except json.JSONDecodeError as e:
        logger.error(f"❌ JSON decode error in listings.json: {e}")
        listings = {}
    except Exception as e:
        logger.error(f"❌ Failed to load listings: {e}")
        listings = {}

async def save_listings():
    try:
        with open('listings.json', 'w', encoding='utf-8') as f:
            json.dump(listings, f, ensure_ascii=False, indent=4, default=str)
        logger.debug("💾 Listings saved.")
    except Exception as e:
        logger.error(f"❌ Failed to save listings: {e}")

def generate_listing_id():
    return str(len(listings) + 1)

def count_listings_by_category():
    counts = {category.replace('📦 ', '').replace('🛋️ ', '').replace('📱 ', '').replace('👗 ', '').replace('👜 ', '').replace('📚 ', '').replace('🧸 ', '').replace('🔌 ', '').replace('🏀 ', '').replace('🌟 ', ''): 0 for category in categories}
    counts['Gratis'] = 0
    now = datetime.datetime.now()
    for item in listings.values():
        if item['expires_at'] > now:
            if item.get('is_free', False):
                counts['Gratis'] += 1
            if item['category'].replace('📦 ', '').replace('🛋️ ', '').replace('📱 ', '').replace('👗 ', '').replace('👜 ', '').replace('📚 ', '').replace('🧸 ', '').replace('🔌 ', '').replace('🏀 ', '').replace('🌟 ', '') in counts:
                counts[item['category'].replace('📦 ', '').replace('🛋️ ', '').replace('📱 ', '').replace('👗 ', '').replace('👜 ', '').replace('📚 ', '').replace('🧸 ', '').replace('🔌 ', '').replace('🏀 ', '').replace('🌟 ', '')] += 1
    return counts

def count_listings_by_city():
    counts = {city: 0 for city in city_mapping.values()}
    now = datetime.datetime.now()
    for item in listings.values():
        if item['expires_at'] > now and item['city'] in counts:
            counts[item['city']] += 1
    return counts

async def display_item_card(chat_id, listing_id, message_id=None, caller_is_search=False, caller_is_edit=False, current_index=0, total_results=0):
    item = listings.get(listing_id)
    if not item:
        logger.warning(f"⚠️ Attempt to display nonexistent listing ID: {listing_id}")
        return

    item_title = escape(item['title'])
    item_category = escape(item['category'])
    item_price = escape(str(item['price']))
    item_contact = escape(item['contact'])
    item_posted_at = item['posted_at'].strftime("%d.%m.%Y")
    item_expires_at = item['expires_at'].strftime("%d.%m.%Y")

    location_info = f"<b>📍 Ciudad:</b> {escape(item['city'])}"
    if item.get('latitude') is not None and item.get('longitude') is not None:
        location_info += f" (<a href='http://maps.google.com/maps?q={item['latitude']},{item['longitude']}'>Mostrar en el mapa</a>)"

    description_info = f"📝 Descripción: {escape(item.get('description', ''))}" if item.get('description') else ""
    bundle_note = "📦 Kit de objetos para mudanza" if item['category'] == "📦 ¡Kit de mudanza!" else ""

    title_prefix = "♾ ¡Gratis!" if item.get('is_free', False) else ""
    notification = ""
    if not caller_is_search and not caller_is_edit:
        notification = f"<b>✅ Anuncio #{item['id']} publicado exitosamente!</b>\n"
    elif caller_is_edit:
        notification = f"<b>✅ Anuncio #{item['id']} editado exitosamente!</b>\n"

    caption_text = (
        f"{notification}"
        f"<b>{title_prefix} {item_title}</b>\n"
        f"📋 Categoría: {item_category}\n"
        f"{bundle_note}\n"
        f"💰 Precio: {item_price}\n"
        f"{description_info}\n"
        f"{location_info}\n"
        f"📞 Contacto: {item_contact}\n"
        f"📅 Publicado: {item_posted_at}\n"
        f"⏰ Vence: {item_expires_at}\n"
    ).strip()

    photos = [item['photo_id']] + item.get('additional_photo_ids', [])
    media_group = []

    for i, photo_id in enumerate(photos):
        if i == 0:
            media_group.append(InputMediaPhoto(media=photo_id, caption=caption_text, parse_mode=ParseMode.HTML))
        else:
            media_group.append(InputMediaPhoto(media=photo_id))

    reply_markup = get_item_card_keyboard(caller_is_search, caller_is_edit, current_index, total_results, listing_id)

    try:
        if media_group:
            sent_messages = await bot.send_media_group(chat_id=chat_id, media=media_group)
            if reply_markup:
                await bot.send_message(chat_id=chat_id, text="⬆️⬆️ Anuncio completo arriba ⬆️⬆️", reply_markup=reply_markup)
        else:
            await bot.send_message(chat_id=chat_id, text=caption_text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    except TelegramBadRequest as e:
        logger.error(f"❌ Failed to send item card for {listing_id}: {e}")
        await bot.send_message(chat_id=chat_id, text="❗ Error al mostrar el anuncio.", reply_markup=main_keyboard)

async def display_search_results(message: Message, state: FSMContext):
    data = await state.get_data()
    results = data.get('search_results', [])
    user_id = message.from_user.id

    if not results:
        await message.answer("🔍 No se encontraron resultados de búsqueda. Inicie una nueva búsqueda.", reply_markup=main_keyboard)
        await state.clear()
        return

    keyboard_buttons = []
    for idx, listing_id in enumerate(results[:5]):
        item = listings[listing_id]
        button_text = f"#{item['id']} {'♾ ¡Gratis!' if item.get('is_free', False) else ''} {item['title']} ({item['price']})"
        keyboard_buttons.append([InlineKeyboardButton(text=button_text, callback_data=f"view_search_item_{listing_id}_{idx}")])
    if len(results) > 5:
        keyboard_buttons.append([InlineKeyboardButton(text="➡️ Mostrar más", callback_data="show_more_results")])
    keyboard_buttons.append([InlineKeyboardButton(text="❌ Cancelar", callback_data="cancel")])

    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    await message.reply(f"🛒 Anuncios encontrados: {len(results)}. Seleccione para ver:", reply_markup=reply_markup)

# 🤖 Handlers
@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if message.from_user.is_bot:
        logger.warning(f"⚠️ Ignoring command from bot: user_id={user_id}")
        return
    if user_id not in user_data:
        user_data[user_id] = {"listings": [], "favorites": [], "banned": False}
        await save_user_data()
    if user_data.get(user_id, {}).get('banned', False):
        await message.answer("🚫 Su cuenta está bloqueada. Contacte al administrador.")
        return
    await message.answer(
        "👋 ¡Bienvenido! Seleccione una acción:",
        reply_markup=main_keyboard
    )
    await state.clear()

@dp.message(F.text == "❌ Cancelar")
async def cancel_action(message: Message, state: FSMContext):
    if message.from_user.is_bot:
        logger.warning(f"⚠️ Ignoring command from bot: user_id={message.from_user.id}")
        return
    await message.answer("✅ Acción cancelada.", reply_markup=main_keyboard)
    await state.clear()

@dp.message(F.text == "🧳 Dejar objetos")
async def add_item_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if message.from_user.is_bot:
        logger.warning(f"⚠️ Ignoring command from bot: user_id={user_id}")
        return
    if user_data.get(user_id, {}).get('banned', False):
        await message.answer("🚫 Su cuenta está bloqueada.")
        return
    await message.answer(
        "📋 Seleccione la categoría para el objeto o '📦 ¡Kit de mudanza!' para un conjunto de objetos:",
        reply_markup=get_categories_keyboard()
    )
    await state.set_state(ItemForm.item_category)

@dp.message(ItemForm.item_category)
async def process_category(message: Message, state: FSMContext):
    category = message.text.strip()
    if category not in categories:
        await message.answer(
            "❗ Por favor, seleccione una categoría de las propuestas:",
            reply_markup=get_categories_keyboard()
        )
        return
    await state.update_data(item_category=category)
    title_prompt = "✏️ Ingrese el título del conjunto (hasta 50 caracteres):" if category == "📦 ¡Kit de mudanza!" else "✏️ Ingrese el título del objeto (hasta 50 caracteres):"
    await message.answer(
        title_prompt,
        reply_markup=cancel_keyboard
    )
    await state.set_state(ItemForm.item_title)

@dp.message(ItemForm.item_title)
async def process_title(message: Message, state: FSMContext):
    title = message.text.strip()
    if len(title) > 50:
        await message.answer(
            "❗ El título es demasiado largo. Ingrese hasta 50 caracteres:",
            reply_markup=cancel_keyboard
        )
        return
    await state.update_data(item_title=title)
    await message.answer(
        "📝 Ingrese la descripción del objeto (hasta 200 caracteres, opcional):",
        reply_markup=get_skip_keyboard()
    )
    await state.set_state(ItemForm.item_description)

@dp.message(ItemForm.item_description, F.text == "⏭️ Omitir")
async def skip_description(message: Message, state: FSMContext):
    await state.update_data(item_description="")
    await message.answer(
        "📸 Envíe la foto principal del objeto:",
        reply_markup=cancel_keyboard
    )
    await state.set_state(ItemForm.item_photo)

@dp.message(ItemForm.item_description)
async def process_description(message: Message, state: FSMContext):
    description = message.text.strip()
    if len(description) > 200:
        await message.answer(
            "❗ La descripción es demasiado larga. Ingrese hasta 200 caracteres o omita:",
            reply_markup=get_skip_keyboard()
        )
        return
    await state.update_data(item_description=description)
    await message.answer(
        "📸 Envíe la foto principal del objeto:",
        reply_markup=cancel_keyboard
    )
    await state.set_state(ItemForm.item_photo)

@dp.message(ItemForm.item_photo, F.photo)
async def process_photo(message: Message, state: FSMContext):
    photo_id = message.photo[-1].file_id
    await state.update_data(item_photo_id=photo_id)
    data = await state.get_data()
    max_photos = 9 if data.get('item_category') == "📦 ¡Kit de mudanza!" else 3
    await message.answer(
        f"📷 Envíe hasta {max_photos} fotos adicionales o omita:",
        reply_markup=get_skip_keyboard()
    )
    await state.set_state(ItemForm.item_additional_photos)

@dp.message(ItemForm.item_additional_photos, F.text == "⏭️ Omitir")
async def skip_additional_photos(message: Message, state: FSMContext):
    await state.update_data(item_additional_photo_ids=[])
    await message.answer(
        "💰 Indique el precio (en dólares) o 'Gratis':\nIngrese 0 para un anuncio gratuito o el monto (por ejemplo, 10.50).",
        reply_markup=cancel_keyboard
    )
    await state.set_state(ItemForm.item_price_value)

@dp.message(ItemForm.item_additional_photos, F.photo)
async def process_additional_photos(message: Message, state: FSMContext):
    data = await state.get_data()
    max_photos = 9 if data.get('item_category') == "📦 ¡Kit de mudanza!" else 3
    additional_photos = data.get('item_additional_photo_ids', [])
    if len(additional_photos) >= max_photos:
        await message.answer(
            f"📷 Se alcanzó el máximo ({max_photos} fotos adicionales). Presione '⏭️ Omitir'.",
            reply_markup=get_skip_keyboard()
        )
        return
    additional_photos.append(message.photo[-1].file_id)
    await state.update_data(item_additional_photo_ids=additional_photos)
    await message.answer(
        f"✅ Foto agregada ({len(additional_photos)}/{max_photos}). Agregue más o omita:",
        reply_markup=get_skip_keyboard()
    )

@dp.message(ItemForm.item_price_value)
async def process_price_value(message: Message, state: FSMContext):
    price_text = message.text.strip().lower()
    logger.debug(f"💰 Processing price input: '{price_text}'")
    if price_text == "gratis":
        await state.update_data(item_price="Gratis", item_status="free", is_free=True)
        await message.answer("🏙️ Indique la ciudad:", reply_markup=get_cities_keyboard())
        await state.set_state(ItemForm.item_city)
        return
    try:
        price = float(price_text)
        if price < 0:
            raise ValueError
        if price == 0:
            await state.update_data(item_price="Gratis", item_status="free", is_free=True)
        else:
            await state.update_data(item_price=f"{price:.2f}", item_status="sell", is_free=False)
        await message.answer("🏙️ Indique la ciudad:", reply_markup=get_cities_keyboard())
        await state.set_state(ItemForm.item_city)
    except ValueError:
        await message.answer(
            "❗ Ingrese un precio válido (número ≥ 0, por ejemplo, 10.50) o 'Gratis'.",
            reply_markup=cancel_keyboard
        )

@dp.message(ItemForm.item_city)
async def process_city(message: Message, state: FSMContext):
    city = message.text.strip()
    if city not in cities:
        await message.answer(
            "❗ Por favor, seleccione una ciudad de las propuestas:",
            reply_markup=get_cities_keyboard()
        )
        return
    await state.update_data(item_city=city_mapping[city])
    await message.answer(
        "📍 Indique la ubicación:",
        reply_markup=get_location_type_keyboard()
    )
    await state.set_state(ItemForm.item_ask_geolocation)

@dp.callback_query(F.data.startswith("search_city_"), ItemForm.item_city)
async def process_item_city_callback(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.is_bot:
        logger.warning(f"⚠️ Ignoring callback from bot: user_id={callback.from_user.id}")
        await callback.answer()
        return
    city = callback.data.replace("search_city_", "")
    logger.debug(f"📍 Item city selected: '{city}'")
    if city not in cities:
        await callback.message.answer(
            "❗ Error: ciudad no encontrada.",
            reply_markup=main_keyboard
        )
        await state.clear()
        await callback.message.delete()
        return
    await state.update_data(item_city=city_mapping[city])
    await callback.message.answer(
        "📍 Indique la ubicación:",
        reply_markup=get_location_type_keyboard()
    )
    await state.set_state(ItemForm.item_ask_geolocation)
    await callback.message.delete()
    await callback.answer()

@dp.callback_query(F.data == "search_skip_city", ItemForm.item_city)
async def skip_item_city_callback(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.is_bot:
        logger.warning(f"⚠️ Ignoring callback from bot: user_id={callback.from_user.id}")
        await callback.answer()
        return
    await state.update_data(item_city="")
    await callback.message.answer(
        "📍 Indique la ubicación:",
        reply_markup=get_location_type_keyboard()
    )
    await state.set_state(ItemForm.item_ask_geolocation)
    await callback.message.delete()
    await callback.answer()

@dp.message(ItemForm.item_ask_geolocation, F.text == "🏙️ Solo ciudad")
async def process_location_city_only(message: Message, state: FSMContext):
    await state.update_data(item_location_type="city")
    await message.answer(
        "📞 Ingrese la información de contacto (por ejemplo, número de teléfono):",
        reply_markup=cancel_keyboard
    )
    await state.set_state(ItemForm.item_contact)

@dp.message(ItemForm.item_ask_geolocation, F.location)
async def process_location_geolocation(message: Message, state: FSMContext):
    await state.update_data(
        item_location_type="geolocation",
        item_latitude=message.location.latitude,
        item_longitude=message.location.longitude
    )
    await message.answer(
        "📞 Ingrese la información de contacto (por ejemplo, número de teléfono):",
        reply_markup=cancel_keyboard
    )
    await state.set_state(ItemForm.item_contact)

@dp.message(ItemForm.item_contact)
async def process_contact(message: Message, state: FSMContext):
    contact = message.text.strip()
    if not contact:
        await message.answer(
            "❗ La información de contacto no puede estar vacía. Ingrese, por ejemplo, un número de teléfono:",
            reply_markup=cancel_keyboard
        )
        return
    await state.update_data(item_contact=contact)
    await message.answer(
        "📅 Indique el período de validez del anuncio:",
        reply_markup=get_expires_at_keyboard()
    )
    await state.set_state(ItemForm.item_expires_at)

@dp.message(ItemForm.item_expires_at)
async def process_expires_at(message: Message, state: FSMContext):
    try:
        days = int(message.text.replace("📅 ", "").replace(" días", "").replace(" día", ""))
        if days not in [3, 5]:
            raise ValueError
    except ValueError:
        await message.answer(
            "❗ Por favor, seleccione '📅 3 días' o '📅 5 días'.",
            reply_markup=get_expires_at_keyboard()
        )
        return

    data = await state.get_data()
    user_id = message.from_user.id
    expires_at = datetime.datetime.now() + datetime.timedelta(days=days)

    item = {
        'id': generate_listing_id(),
        'user_id': user_id,
        'category': data.get('item_category'),
        'title': data.get('item_title'),
        'description': data.get('item_description', ""),
        'photo_id': data.get('item_photo_id'),
        'additional_photo_ids': data.get('item_additional_photo_ids', []),
        'price': data.get('item_price'),
        'status': data.get('item_status'),
        'is_free': data.get('is_free', False),
        'location_type': data.get('item_location_type', 'city'),
        'city': data.get('item_city'),
        'latitude': data.get('item_latitude'),
        'longitude': data.get('item_longitude'),
        'contact': data.get('item_contact'),
        'posted_at': datetime.datetime.now(),
        'expires_at': expires_at,
        'views': 0
    }

    listings[item['id']] = item
    if user_id not in user_data:
        user_data[user_id] = {"listings": [], "favorites": [], "banned": False}
    user_data[user_id]['listings'].append(item['id'])
    await save_listings()
    await save_user_data()

    logger.info(f"✅ User {user_id} added item: {item['title']}")
    await display_item_card(user_id, item['id'])
    await message.answer("🎉 ¡Anuncio creado! Seleccione una acción:", reply_markup=main_keyboard)
    await state.clear()

@dp.message(F.text == "🔍 Buscar objeto")
async def search_item_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if message.from_user.is_bot:
        logger.warning(f"⚠️ Ignoring command from bot: user_id={user_id}")
        return
    logger.debug(f"🔍 Search started by user {user_id}: text='{message.text}'")
    if user_data.get(user_id, {}).get('banned', False):
        await message.answer("🚫 Estás bloqueado.")
        return
    await message.answer(
        "🔎 Ingrese una palabra clave para la búsqueda (por ejemplo, 'silla') o omita:",
        reply_markup=get_skip_keyboard()
    )
    await state.set_state(SearchForm.keyword)

@dp.message(SearchForm.keyword, F.text == "⏭️ Omitir")
async def skip_keyword(message: Message, state: FSMContext):
    if message.from_user.is_bot:
        logger.warning(f"⚠️ Ignoring command from bot: user_id={message.from_user.id}")
        return
    await state.update_data(keyword="")
    await message.answer(
        "📋 Seleccione una categoría para la búsqueda o omita:",
        reply_markup=get_categories_keyboard(is_search=True)
    )
    await state.set_state(SearchForm.category)

@dp.message(SearchForm.keyword)
async def process_keyword(message: Message, state: FSMContext):
    if message.from_user.is_bot:
        logger.warning(f"⚠️ Ignoring command from bot: user_id={message.from_user.id}")
        return
    keyword = message.text.strip()
    logger.debug(f"🔎 Search keyword: '{keyword}'")
    await state.update_data(keyword=keyword)
    await message.answer(
        "📋 Seleccione una categoría para la búsqueda o omita:",
        reply_markup=get_categories_keyboard(is_search=True)
    )
    await state.set_state(SearchForm.category)

@dp.callback_query(F.data.startswith("search_category_"), SearchForm.category)
async def process_search_category_callback(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.is_bot:
        logger.warning(f"⚠️ Ignoring callback from bot: user_id={callback.from_user.id}")
        await callback.answer()
        return
    category = callback.data.replace("search_category_", "")
    logger.debug(f"📋 Search category selected: '{category}'")
    valid_categories = [c.replace('📦 ', '').replace('🛋️ ', '').replace('📱 ', '').replace('👗 ', '').replace('👜 ', '').replace('📚 ', '').replace('🧸 ', '').replace('🔌 ', '').replace('🏀 ', '').replace('🌟 ', '') for c in categories] + ['Gratis']
    if category not in valid_categories:
        await callback.message.answer(
            "❗ Error: categoría no encontrada.",
            reply_markup=main_keyboard
        )
        await state.clear()
        await callback.message.delete()
        return
    await state.update_data(category=category)
    await callback.message.answer(
        "🏙️ Seleccione una ciudad para la búsqueda o omita:",
        reply_markup=get_cities_keyboard()
    )
    await state.set_state(SearchForm.city)
    await callback.message.delete()
    await callback.answer()

@dp.callback_query(F.data == "search_skip_category", SearchForm.category)
async def skip_category_callback(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.is_bot:
        logger.warning(f"⚠️ Ignoring callback from bot: user_id={callback.from_user.id}")
        await callback.answer()
        return
    await state.update_data(category="")
    await callback.message.answer(
        "🏙️ Seleccione una ciudad para la búsqueda o omitа:",
        reply_markup=get_cities_keyboard()
    )
    await state.set_state(SearchForm.city)
    await callback.message.delete()
    await callback.answer()

@dp.callback_query(F.data.startswith("search_city_"), SearchForm.city)
async def process_search_city_callback(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.is_bot:
        logger.warning(f"⚠️ Ignoring callback from bot: user_id={callback.from_user.id}")
        await callback.answer()
        return
    city = callback.data.replace("search_city_", "")
    logger.debug(f"📍 Search city selected: '{city}'")
    if city not in cities:
        await callback.message.answer(
            "❗ Error: ciudad no encontrada.",
            reply_markup=main_keyboard
        )
        await state.clear()
        await callback.message.delete()
        return
    await state.update_data(city=city_mapping[city])
    await perform_search(callback.message, state, chat_id=callback.message.chat.id)
    await callback.message.delete()
    await callback.answer()

@dp.callback_query(F.data == "search_skip_city", SearchForm.city)
async def skip_city_callback(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.is_bot:
        logger.warning(f"⚠️ Ignoring callback from bot: user_id={callback.from_user.id}")
        await callback.answer()
        return
    await state.update_data(city="")
    await perform_search(callback.message, state, chat_id=callback.message.chat.id)
    await callback.message.delete()
    await callback.answer()

async def perform_search(message: Message, state: FSMContext, chat_id: int):
    data = await state.get_data()
    keyword = data.get('keyword', "").lower()
    category = data.get('category', "")
    city = data.get('city', "")

    logger.debug(f"🔍 Performing search: keyword='{keyword}', category='{category}', city='{city}'")

    results = []
    for listing_id, item in listings.items():
        if item['expires_at'] > datetime.datetime.now():
            logger.debug(f"🔎 Checking listing #{listing_id}: title='{item['title']}', description='{item.get('description', '')}'")
            title_match = not keyword or keyword in item['title'].lower() or keyword in item.get('description', '').lower()
            category_match = (
                not category or
                (category == 'Gratis' and item.get('is_free', False)) or
                item['category'].replace('📦 ', '').replace('🛋️ ', '').replace('📱 ', '').replace('👗 ', '').replace('👜 ', '').replace('📚 ', '').replace('🧸 ', '').replace('🔌 ', '').replace('🏀 ', '').replace('🌟 ', '') == category
            )
            city_match = not city or item['city'] == city
            if title_match and category_match and city_match:
                logger.debug(f"✅ Listing #{listing_id} matches search criteria")
                results.append(listing_id)
            else:
                logger.debug(f"❌ Listing #{listing_id} does not match: title_match={title_match}, category_match={category_match}, city_match={city_match}")

    results.sort(key=lambda x: not listings[x].get('is_free', False))

    logger.debug(f"🛒 Search results: {len(results)} items found")

    if not results:
        await message.answer("🔍 No se encontraron resultados. Intente modificar la búsqueda.", reply_markup=main_keyboard)
        await state.clear()
        return

    await state.update_data(search_results=results, current_result_index=0)
    await display_item_card(chat_id, results[0], caller_is_search=True, current_index=0, total_results=len(results))

@dp.message(F.text == "📋 Mis anuncios")
async def show_my_listings(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if message.from_user.is_bot:
        logger.warning(f"⚠️ Ignoring command from bot: user_id={user_id}")
        return
    if user_data.get(user_id, {}).get('banned', False):
        await message.answer("🚫 Su cuenta está bloqueada.")
        return
    if user_id not in user_data or not user_data[user_id].get('listings'):
        await message.answer("📭 No tienes anuncios activos.", reply_markup=main_keyboard)
        return

    active_listings = [lid for lid in user_data[user_id]['listings'] if listings.get(lid) and listings[lid]['expires_at'] > datetime.datetime.now()]
    if not active_listings:
        await message.answer("📭 No tienes anuncios activos.", reply_markup=main_keyboard)
        return

    keyboard_buttons = []
    for listing_id in active_listings:
        item = listings[listing_id]
        button_text = f"🛒 #{item['id']} {'♾ ¡Gratis!' if item.get('is_free', False) else ''} {item['title']} (${item['price']})"
        keyboard_buttons.append([
            InlineKeyboardButton(text=button_text, callback_data=f"view_item_{listing_id}"),
            InlineKeyboardButton(text="🗑", callback_data=f"delete_item_{listing_id}")
        ])
    keyboard_buttons.append([InlineKeyboardButton(text="❌ Cancelar", callback_data="cancel")])

    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    await message.answer("📋 Seleccione un anuncio para ver:", reply_markup=reply_markup)
    await state.set_state(EditForm.select_item)

@dp.callback_query(F.data == "back_to_search_results")
async def back_to_search_results(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.is_bot:
        logger.warning(f"⚠️ Ignoring callback from bot: user_id={callback.from_user.id}")
        await callback.answer()
        return
    await callback.message.delete()
    await display_search_results(callback.message, state)
    await callback.answer()

@dp.callback_query(F.data.startswith("view_search_item_"))
async def view_search_item_callback(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.is_bot:
        logger.warning(f"⚠️ Ignoring callback from bot: user_id={callback.from_user.id}")
        await callback.answer()
        return
    parts = callback.data.split("_")
    listing_id = parts[3]
    index = int(parts[4])
    data = await state.get_data()
    results = data.get('search_results', [])

    if listing_id not in listings or listing_id not in results:
        await callback.message.answer("❗ Anuncio no encontrado.", reply_markup=main_keyboard)
        await state.clear()
        await callback.message.delete()
        return

    await state.update_data(current_result_index=index)
    await display_item_card(callback.message.chat.id, listing_id, caller_is_search=True, current_index=index, total_results=len(results))
    await callback.message.delete()
    await callback.answer()

@dp.callback_query(F.data.startswith("search_prev_"))
async def search_prev_callback(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.is_bot:
        logger.warning(f"⚠️ Ignoring callback from bot: user_id={callback.from_user.id}")
        await callback.answer()
        return
    current_index = int(callback.data.replace("search_prev_", ""))
    data = await state.get_data()
    results = data.get('search_results', [])

    if current_index <= 0 or not results:
        await callback.answer("⛔ Este es el primer anuncio.")
        return

    new_index = current_index - 1
    await state.update_data(current_result_index=new_index)
    await display_item_card(callback.message.chat.id, results[new_index], caller_is_search=True, current_index=new_index, total_results=len(results))
    await callback.message.delete()
    await callback.answer()

@dp.callback_query(F.data.startswith("search_next_"))
async def search_next_callback(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.is_bot:
        logger.warning(f"⚠️ Ignoring callback from bot: user_id={callback.from_user.id}")
        await callback.answer()
        return
    current_index = int(callback.data.replace("search_next_", ""))
    data = await state.get_data()
    results = data.get('search_results', [])

    if current_index >= len(results) - 1 or not results:
        await callback.answer("⛔ Este es el último anuncio.")
        return

    new_index = current_index + 1
    await state.update_data(current_result_index=new_index)
    await display_item_card(callback.message.chat.id, results[new_index], caller_is_search=True, current_index=new_index, total_results=len(results))
    await callback.message.delete()
    await callback.answer()

@dp.callback_query(F.data == "show_more_results")
async def show_more_results(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.is_bot:
        logger.warning(f"⚠️ Ignoring callback from bot: user_id={callback.from_user.id}")
        await callback.answer()
        return
    data = await state.get_data()
    results = data.get('search_results', [])
    current_page = data.get('search_page', 0)

    next_page = current_page + 1
    start_idx = next_page * 5
    if start_idx >= len(results):
        await callback.answer("⛔ No hay más resultados.")
        return

    keyboard_buttons = []
    for idx, listing_id in enumerate(results[start_idx:start_idx+5]):
        item = listings[listing_id]
        button_text = f"🛒 #{item['id']} {'♾ ¡Gratis!' if item.get('is_free', False) else ''} {item['title']} (${item['price']})"
        keyboard_buttons.append([InlineKeyboardButton(text=button_text, callback_data=f"view_search_item_{listing_id}_{start_idx+idx}")])
    if start_idx + 5 < len(results):
        keyboard_buttons.append([InlineKeyboardButton(text="➡️ Mostrar más", callback_data="show_more_results")])
    if next_page > 0:
        keyboard_buttons.append([InlineKeyboardButton(text="⬅️ Atrás", callback_data="show_prev_results")])
    keyboard_buttons.append([InlineKeyboardButton(text="❌ Cancelar", callback_data="cancel")])

    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    await callback.message.edit_text(f"🛒 Anuncios encontrados: {len(results)}. Seleccione para ver:", reply_markup=reply_markup)
    await state.update_data(search_page=next_page)
    await callback.answer()

@dp.callback_query(F.data == "show_prev_results")
async def show_prev_results(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.is_bot:
        logger.warning(f"⚠️ Ignoring callback from bot: user_id={callback.from_user.id}")
        await callback.answer()
        return
    data = await state.get_data()
    results = data.get('search_results', [])
    current_page = data.get('search_page', 0)

    prev_page = current_page - 1
    if prev_page < 0:
        await callback.answer("⛔ Esta es la primera página.")
        return

    start_idx = prev_page * 5
    keyboard_buttons = []
    for idx, listing_id in enumerate(results[start_idx:start_idx+5]):
        item = listings[listing_id]
        button_text = f"🛒 #{item['id']} {'♾ ¡Gratis!' if item.get('is_free', False) else ''} {item['title']} (${item['price']})"
        keyboard_buttons.append([InlineKeyboardButton(text=button_text, callback_data=f"view_search_item_{listing_id}_{start_idx+idx}")])
    if start_idx + 5 < len(results):
        keyboard_buttons.append([InlineKeyboardButton(text="➡️ Mostrar más", callback_data="show_more_results")])
    if prev_page > 0:
        keyboard_buttons.append([InlineKeyboardButton(text="⬅️ Atrás", callback_data="show_prev_results")])
    keyboard_buttons.append([InlineKeyboardButton(text="❌ Cancelar", callback_data="cancel")])

    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    await callback.message.edit_text(f"🛒 Anuncios encontrados: {len(results)}. Seleccione para ver:", reply_markup=reply_markup)
    await state.update_data(search_page=prev_page)
    await callback.answer()

@dp.callback_query(F.data == "cancel")
async def cancel_callback(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.is_bot:
        logger.warning(f"⚠️ Ignoring callback from bot: user_id={callback.from_user.id}")
        await callback.answer()
        return
    await callback.message.answer("✅ Acción cancelada.", reply_markup=main_keyboard)
    await state.clear()
    await callback.message.delete()

@dp.callback_query(F.data.startswith("view_item_"))
async def view_item_callback(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.is_bot:
        logger.warning(f"⚠️ Ignoring callback from bot: user_id={callback.from_user.id}")
        await callback.answer()
        return
    listing_id = callback.data.replace("view_item_", "")
    user_id = callback.from_user.id
    if listing_id not in listings or listings[listing_id]['user_id'] != user_id:
        await callback.message.answer("❗ Anuncio no encontrado o no le pertenece.", reply_markup=main_keyboard)
        await state.clear()
        await callback.message.delete()
        return

    await state.update_data(selected_item_id=listing_id)
    await display_item_card(callback.message.chat.id, listing_id, caller_is_edit=True)
    await callback.message.delete()

@dp.callback_query(F.data.startswith("edit_item_"))
async def edit_item_callback(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.is_bot:
        logger.warning(f"⚠️ Ignoring callback from bot: user_id={callback.from_user.id}")
        await callback.answer()
        return
    listing_id = callback.data.replace("edit_item_", "")
    user_id = callback.from_user.id
    if listing_id not in listings or listings[listing_id]['user_id'] != user_id:
        await callback.message.answer("❗ Anuncio no encontrado o no le pertenece.", reply_markup=main_keyboard)
        await state.clear()
        return

    await state.update_data(selected_item_id=listing_id)
    await callback.message.answer(
        "✏️ Seleccione el campo para editar:",
        reply_markup=get_edit_fields_keyboard()
    )
    await state.set_state(EditForm.choose_field)
    await callback.message.delete()

@dp.callback_query(F.data.startswith("delete_item_"))
async def delete_item_callback(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.is_bot:
        logger.warning(f"⚠️ Ignoring callback from bot: user_id={callback.from_user.id}")
        await callback.answer()
        return
    listing_id = callback.data.replace("delete_item_", "")
    user_id = callback.from_user.id
    if listing_id not in listings or listings[listing_id]['user_id'] != user_id:
        await callback.message.answer("❗ Anuncio no encontrado o no le pertenece.", reply_markup=main_keyboard)
        await state.clear()
        await callback.message.delete()
        return

    await state.update_data(selected_item_id=listing_id)
    item = listings[listing_id]
    await callback.message.answer(
        f"⚠️ ¿Está seguro de que desea eliminar el anuncio #{item['id']} {'♾ ¡Gratis!' if item.get('is_free', False) else ''} {item['title']}?",
        reply_markup=get_confirm_delete_keyboard(listing_id)
    )
    await callback.message.delete()

@dp.callback_query(F.data.startswith("confirm_delete_"))
async def confirm_delete_callback(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.is_bot:
        logger.warning(f"⚠️ Ignoring callback from bot: user_id={callback.from_user.id}")
        await callback.answer()
        return
    listing_id = callback.data.replace("confirm_delete_", "")
    user_id = callback.from_user.id
    if listing_id not in listings or listings[listing_id]['user_id'] != user_id:
        await callback.message.answer("❗ Anuncio no encontrado o no le pertenece.", reply_markup=main_keyboard)
        await state.clear()
        await callback.message.delete()
        return

    item = listings.pop(listing_id)
    user_data[user_id]['listings'].remove(listing_id)
    await save_listings()
    await save_user_data()

    logger.info(f"✅ User {user_id} deleted item {listing_id}: {item['title']}")
    await callback.message.answer(f"🗑 Anuncio #{item['id']} eliminado exitosamente.", reply_markup=main_keyboard)
    await state.clear()
    await callback.message.delete()

@dp.message(EditForm.choose_field)
async def process_choose_field(message: Message, state: FSMContext):
    if message.from_user.is_bot:
        logger.warning(f"⚠️ Ignoring command from bot: user_id={message.from_user.id}")
        return
    field = message.text.strip()
    valid_fields = [
        "📋 Categoría", "✏️ Título", "💰 Precio", "📸 Foto principal", "📷 Fotos adicionales",
        "📝 Descripción", "🏙️ Ciudad", "📍 Geolocalización", "📞 Contacto", "📅 Vigencia"
    ]
    if field not in valid_fields:
        await message.answer(
            "❗ Por favor, seleccione un campo de los propuestos:",
            reply_markup=get_edit_fields_keyboard()
        )
        return

    data = await state.get_data()
    listing_id = data.get('selected_item_id')
    if not listing_id or listing_id not in listings:
        await message.answer("❗ Error: anuncio no encontrado.", reply_markup=main_keyboard)
        await state.clear()
        return

    if field == "📋 Categoría":
        await message.answer(
            "📋 Seleccione una nueva categoría:",
            reply_markup=get_categories_keyboard()
        )
        await state.set_state(EditForm.edit_category)
    elif field == "✏️ Título":
        await message.answer(
            "✏️ Ingrese un nuevo título (hasta 50 caracteres):",
            reply_markup=cancel_keyboard
        )
        await state.set_state(EditForm.edit_title)
    elif field == "💰 Precio":
        await message.answer(
            "💰 Indique un nuevo precio (en dólares) о 'Gratis':\nIngrese 0 para un anuncio gratuito o el monto (por ejemplo, 10.50).",
            reply_markup=cancel_keyboard
        )
        await state.set_state(EditForm.edit_price_value)
    elif field == "📸 Foto principal":
        await message.answer(
            "📸 Envíe una nueva foto principal:",
            reply_markup=cancel_keyboard
        )
        await state.set_state(EditForm.edit_photo)
    elif field == "📷 Fotos adicionales":
        data = await state.get_data()
        max_photos = 9 if listings[listing_id]['category'] == "📦 ¡Kit de mudanza!" else 3
        await message.answer(
            f"📷 Envíe hasta {max_photos} nuevas fotos adicionales o omitа:",
            reply_markup=get_skip_keyboard()
        )
        await state.set_state(EditForm.edit_additional_photos)
    elif field == "📝 Descripción":
        await message.answer(
            "📝 Ingrese una nueva descripción (hasta 200 caracteres, opcional):",
            reply_markup=get_skip_keyboard()
        )
        await state.set_state(EditForm.edit_description)
    elif field == "🏙️ Ciudad":
        await message.answer(
            "🏙️ Seleccione una nueva ciudad:",
            reply_markup=get_cities_keyboard()
        )
        await state.set_state(EditForm.edit_city)
    elif field == "📍 Geolocalización":
        await message.answer(
            "📍 Indique una nueva ubicación:",
            reply_markup=get_location_type_keyboard()
        )
        await state.set_state(EditForm.edit_location_type)
    elif field == "📞 Contacto":
        await message.answer(
            "📞 Ingrese una nueva información de contacto (por ejemplo, número de teléfono):",
            reply_markup=cancel_keyboard
        )
        await state.set_state(EditForm.edit_contact)
    elif field == "📅 Vigencia":
        await message.answer(
            "📅 Indique un nuevo período de validez del anuncio:",
            reply_markup=get_expires_at_keyboard()
        )
        await state.set_state(EditForm.edit_expires_at)

@dp.message(EditForm.edit_category)
async def process_edit_category(message: Message, state: FSMContext):
    if message.from_user.is_bot:
        logger.warning(f"⚠️ Ignoring command from bot: user_id={message.from_user.id}")
        return
    category = message.text.strip()
    if category not in categories:
        await message.answer(
            "❗ Por favor, seleccione una categoría de las propuestas:",
            reply_markup=get_categories_keyboard()
        )
        return
    data = await state.get_data()
    listing_id = data.get('selected_item_id')

    listings[listing_id]['category'] = category
    await save_listings()

    logger.info(f"✅ User {message.from_user.id} edited category of item {listing_id} to '{category}'")
    await display_item_card(message.from_user.id, listing_id, caller_is_edit=True)
    await state.clear()

@dp.message(EditForm.edit_title)
async def process_edit_title(message: Message, state: FSMContext):
    if message.from_user.is_bot:
        logger.warning(f"⚠️ Ignoring command from bot: user_id={message.from_user.id}")
        return
    title = message.text.strip()
    if len(title) > 50:
        await message.answer(
            "❗ El título es demasiado largo. Ingrese hasta 50 caracteres:",
            reply_markup=cancel_keyboard
        )
        return
    data = await state.get_data()
    listing_id = data.get('selected_item_id')

    listings[listing_id]['title'] = title
    await save_listings()

    logger.info(f"✅ User {message.from_user.id} edited title of item {listing_id} to '{title}'")
    await display_item_card(message.from_user.id, listing_id, caller_is_edit=True)
    await state.clear()

@dp.message(EditForm.edit_description, F.text == "⏭️ Omitir")
async def skip_edit_description(message: Message, state: FSMContext):
    if message.from_user.is_bot:
        logger.warning(f"⚠️ Ignoring command from bot: user_id={message.from_user.id}")
        return
    data = await state.get_data()
    listing_id = data.get('selected_item_id')

    listings[listing_id]['description'] = ""
    await save_listings()

    logger.info(f"✅ User {message.from_user.id} cleared description of item {listing_id}")
    await display_item_card(message.from_user.id, listing_id, caller_is_edit=True)
    await state.clear()

@dp.message(EditForm.edit_description)
async def process_edit_description(message: Message, state: FSMContext):
    if message.from_user.is_bot:
        logger.warning(f"⚠️ Ignoring command from bot: user_id={message.from_user.id}")
        return
    description = message.text.strip()
    if len(description) > 200:
        await message.answer(
            "❗ La descripción es demasiado larga. Ingrese hasta 200 caracteres o omitа:",
            reply_markup=get_skip_keyboard()
        )
        return
    data = await state.get_data()
    listing_id = data.get('selected_item_id')

    listings[listing_id]['description'] = description
    await save_listings()

    logger.info(f"✅ User {message.from_user.id} edited description of item {listing_id}")
    await display_item_card(message.from_user.id, listing_id, caller_is_edit=True)
    await state.clear()

@dp.message(EditForm.edit_photo, F.photo)
async def process_edit_photo(message: Message, state: FSMContext):
    if message.from_user.is_bot:
        logger.warning(f"⚠️ Ignoring command from bot: user_id={message.from_user.id}")
        return
    photo_id = message.photo[-1].file_id
    data = await state.get_data()
    listing_id = data.get('selected_item_id')

    listings[listing_id]['photo_id'] = photo_id
    await save_listings()

    logger.info(f"✅ User {message.from_user.id} edited photo of item {listing_id}")
    await display_item_card(message.from_user.id, listing_id, caller_is_edit=True)
    await state.clear()

@dp.message(EditForm.edit_additional_photos, F.text == "⏭️ Omitir")
async def skip_edit_additional_photos(message: Message, state: FSMContext):
    if message.from_user.is_bot:
        logger.warning(f"⚠️ Ignoring command from bot: user_id={message.from_user.id}")
        return
    data = await state.get_data()
    listing_id = data.get('selected_item_id')

    listings[listing_id]['additional_photo_ids'] = []
    await save_listings()

    logger.info(f"✅ User {message.from_user.id} cleared additional photos of item {listing_id}")
    await display_item_card(message.from_user.id, listing_id, caller_is_edit=True)
    await state.clear()

@dp.message(EditForm.edit_additional_photos, F.photo)
async def process_edit_additional_photos(message: Message, state: FSMContext):
    if message.from_user.is_bot:
        logger.warning(f"⚠️ Ignoring command from bot: user_id={message.from_user.id}")
        return
    data = await state.get_data()
    listing_id = data.get('selected_item_id')
    max_photos = 9 if listings[listing_id]['category'] == "📦 ¡Kit de mudanza!" else 3
    additional_photos = data.get('edit_additional_photo_ids', [])

    if len(additional_photos) >= max_photos:
        await message.answer(
            f"📷 Se alcanzó el máximo ({max_photos} fotos adicionales). Presione '⏭️ Omitir'.",
            reply_markup=get_skip_keyboard()
        )
        return

    additional_photos.append(message.photo[-1].file_id)
    await state.update_data(edit_additional_photo_ids=additional_photos)
    await message.answer(
        f"✅ Foto agregada ({len(additional_photos)}/{max_photos}). Agregue más о omitа:",
        reply_markup=get_skip_keyboard()
    )

@dp.message(EditForm.edit_price_value)
async def process_edit_price_value(message: Message, state: FSMContext):
    if message.from_user.is_bot:
        logger.warning(f"⚠️ Ignoring command from bot: user_id={message.from_user.id}")
        return
    price_text = message.text.strip().lower()
    data = await state.get_data()
    listing_id = data.get('selected_item_id')

    if price_text == "gratis":
        listings[listing_id]['price'] = "Gratis"
        listings[listing_id]['status'] = "free"
        listings[listing_id]['is_free'] = True
        await save_listings()
        logger.info(f"✅ User {message.from_user.id} edited price of item {listing_id} to 'Gratis'")
        await display_item_card(message.from_user.id, listing_id, caller_is_edit=True)
        await state.clear()
        return

    try:
        price = float(price_text)
        if price < 0:
            raise ValueError
        if price == 0:
            listings[listing_id]['price'] = "Gratis"
            listings[listing_id]['status'] = "free"
            listings[listing_id]['is_free'] = True
        else:
            listings[listing_id]['price'] = f"{price:.2f}"
            listings[listing_id]['status'] = "sell"
            listings[listing_id]['is_free'] = False
        await save_listings()
        logger.info(f"✅ User {message.from_user.id} edited price of item {listing_id} to '{listings[listing_id]['price']}'")
        await display_item_card(message.from_user.id, listing_id, caller_is_edit=True)
        await state.clear()
    except ValueError:
        await message.answer(
            "❗ Ingrese un precio válido (número ≥ 0, por ejemplo, 10.50) о 'Gratis'.",
            reply_markup=cancel_keyboard
        )

@dp.message(EditForm.edit_location_type, F.text == "🏙️ Solo ciudad")
async def process_edit_location_city_only(message: Message, state: FSMContext):
    await state.update_data(edit_location_type="city")
    await message.answer(
        "🏙️ Seleccione una nueva ciudad:",
        reply_markup=get_cities_keyboard()
    )
    await state.set_state(EditForm.edit_city)

@dp.message(EditForm.edit_location_type, F.location)
async def process_edit_location_geolocation(message: Message, state: FSMContext):
    if message.from_user.is_bot:
        logger.warning(f"⚠️ Ignoring command from bot: user_id={message.from_user.id}")
        return
    data = await state.get_data()
    listing_id = data.get('selected_item_id')

    listings[listing_id]['location_type'] = "geolocation"
    listings[listing_id]['latitude'] = message.location.latitude
    listings[listing_id]['longitude'] = message.location.longitude
    await save_listings()

    logger.info(f"✅ User {message.from_user.id} edited geolocation of item {listing_id}")
    await display_item_card(message.from_user.id, listing_id, caller_is_edit=True)
    await state.clear()

@dp.message(EditForm.edit_city)
async def process_edit_city(message: Message, state: FSMContext):
    if message.from_user.is_bot:
        logger.warning(f"⚠️ Ignoring command from bot: user_id={message.from_user.id}")
        return
    city = message.text.strip()
    if city not in cities:
        await message.answer(
            "❗ Por favor, seleccione una ciudad de las propuestas:",
            reply_markup=get_cities_keyboard()
        )
        return
    data = await state.get_data()
    listing_id = data.get('selected_item_id')

    listings[listing_id]['city'] = city_mapping[city]
    listings[listing_id]['location_type'] = "city"
    listings[listing_id]['latitude'] = None
    listings[listing_id]['longitude'] = None
    await save_listings()

    logger.info(f"✅ User {message.from_user.id} edited city of item {listing_id} to '{city_mapping[city]}'")
    await display_item_card(message.from_user.id, listing_id, caller_is_edit=True)
    await state.clear()

@dp.message(EditForm.edit_contact)
async def process_edit_contact(message: Message, state: FSMContext):
    if message.from_user.is_bot:
        logger.warning(f"⚠️ Ignoring command from bot: user_id={message.from_user.id}")
        return
    contact = message.text.strip()
    if not contact:
        await message.answer(
            "❗ La información de contacto no puede estar vacía. Ingrese, por ejemplo, un número de teléfono:",
            reply_markup=cancel_keyboard
        )
        return
    data = await state.get_data()
    listing_id = data.get('selected_item_id')

    listings[listing_id]['contact'] = contact
    await save_listings()

    logger.info(f"✅ User {message.from_user.id} edited contact of item {listing_id}")
    await display_item_card(message.from_user.id, listing_id, caller_is_edit=True)
    await state.clear()

@dp.message(EditForm.edit_expires_at)
async def process_edit_expires_at(message: Message, state: FSMContext):
    if message.from_user.is_bot:
        logger.warning(f"⚠️ Ignoring command from bot: user_id={message.from_user.id}")
        return
    try:
        days = int(message.text.replace("📅 ", "").replace(" días", "").replace(" día", ""))
        if days not in [3, 5]:
            raise ValueError
    except ValueError:
        await message.answer(
            "❗ Por favor, seleccione '📅 3 días' о '📅 5 días'.",
            reply_markup=get_expires_at_keyboard()
        )
        return

    data = await state.get_data()
    listing_id = data.get('selected_item_id')
    expires_at = datetime.datetime.now() + datetime.timedelta(days=days)

    listings[listing_id]['expires_at'] = expires_at
    await save_listings()

    logger.info(f"✅ User {message.from_user.id} edited expiration of item {listing_id} to {expires_at}")
    await display_item_card(message.from_user.id, listing_id, caller_is_edit=True)
    await state.clear()

@dp.message()
async def handle_unprocessed(message: Message, state: FSMContext):
    if message.from_user.is_bot:
        logger.warning(f"⚠️ Ignoring unprocessed message from bot: user_id={message.from_user.id}")
        return
    logger.warning(f"⚠️ Unprocessed message from user {message.from_user.id}")
    await message.answer("❗ Comando no reconocido. Use el menú principal.", reply_markup=main_keyboard)

async def main():
    await load_user_data()
    await load_listings()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())