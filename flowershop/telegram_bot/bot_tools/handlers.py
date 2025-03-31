import os


import dateparser
from aiogram import Router, types, Dispatcher

from aiogram import Router, types, Bot

from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from asgiref.sync import sync_to_async
from shop.models import Bouquet, Customer, Order, Statistics, Consultation
from telegram_bot.bot_tools import keyboards
import asyncio


from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import dateparser
from dotenv import load_dotenv

router = Router()
load_dotenv()
TOKEN = os.getenv("TOKEN_BOT")
bot = Bot(token=TOKEN)


class CustomOccasionState(StatesGroup):
    waiting_for_custom_occasion = State()
    waiting_for_phone = State()
    waiting_for_price = State()
    waiting_for_contact_info = State()


class OrderState(StatesGroup):
    waiting_for_name = State()
    waiting_for_address = State()
    waiting_for_delivery_time = State()
    waiting_for_phone = State()


@router.message(CommandStart())
async def start_handler(message: types.Message):
    user_name = (
        message.from_user.username
        if message.from_user.username
        else message.from_user.first_name
    )
    text = f"Привет, {user_name} 🙋‍♀️! FlowerShop приветствует тебя. К какому событию готовимся? Выберите один из вариантов, либо укажите свой"
    await message.answer(text, reply_markup=keyboards.get_occasion_keyboard())


@router.callback_query(lambda c: c.data == "occasion_other")
async def handle_other_occasion(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите ваш повод:")
    await state.set_state(CustomOccasionState.waiting_for_custom_occasion)
    await callback.answer()


@router.message(CustomOccasionState.waiting_for_custom_occasion)
async def process_custom_occasion(message: types.Message, state: FSMContext):
    user_occasion = message.text
    text = f"Спасибо! Вы указали повод: *{user_occasion}* 💐"
    price_keyboard = keyboards.get_select_price()

    await message.answer(text, parse_mode="Markdown", reply_markup=price_keyboard)
    await state.set_state(CustomOccasionState.waiting_for_price)

    # Сохраняем повод в состоянии
    await state.update_data(occasion=user_occasion)


@router.callback_query(lambda c: c.data == "consultation")
async def request_consultation(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "Пожалуйста, введите ваше имя и номер телефона, и наш администратор свяжется с вами в течение 20 минут."
    )
    await state.set_state(
        CustomOccasionState.waiting_for_contact_info
    )  # Изменено состояние ожидания
    await callback.answer()


@router.message(CustomOccasionState.waiting_for_contact_info)
async def process_contact_info(message: types.Message, state: FSMContext):
    """Сохранение информации о запросе на консультацию"""
    contact_info = message.text.split()

    if len(contact_info) < 2:
        await message.answer(
            "Пожалуйста, укажите ваше имя и номер телефона в формате: Имя Номер."
        )
        return

    user_name = contact_info[0]
    user_phone = contact_info[1]

    # Создаем запись в модели Consultation
    consultation = await sync_to_async(Consultation.objects.create)(
        customer_name=user_name,  # Сохраняем имя клиента
        phone=user_phone,  # Сохраняем номер телефона
    )

    await message.answer(
        f"📝 Ваш запрос на консультацию успешно отправлен!\nИмя: {consultation.customer_name}\nТелефон: {consultation.phone}"
    )

    await state.clear()


@router.message(CustomOccasionState.waiting_for_phone)
async def process_phone(message: types.Message, state: FSMContext):
    phone_number = message.text
    await message.answer(
        f"Спасибо! Ваш номер {phone_number} принят. Ожидайте звонка от администратора."
    )
    await state.clear()


@router.callback_query(lambda c: c.data.startswith("occasion_"))
async def handle_occasion(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик для выбора стандартных поводов"""
    occasion_key = callback.data.replace("occasion_", "")
    bouquets = await sync_to_async(list)(Bouquet.objects.filter(occasion=occasion_key))

    if not bouquets:
        await callback.message.answer(
            "К сожалению, у нас пока нет букетов для этого случая 😔"
        )
        return

    # Запрос на выбор суммы
    await callback.message.answer(
        "На какую сумму рассчитываете?", reply_markup=keyboards.get_select_price()
    )
    await state.set_state(CustomOccasionState.waiting_for_price)
    await state.update_data(occasion=occasion_key)
    await callback.answer()


@router.callback_query(lambda c: c.data.startswith("price_"))
async def handle_price_selection(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик для выбора цены"""
    price_key = callback.data.replace("price_", "")

    # Получаем данные из состояния
    user_data = await state.get_data()
    user_occasion = user_data.get("occasion")

    # Определяем фильтр по цене
    if price_key == "nometter":
        price_filter = {}  # Без фильтрации по цене
    elif price_key == "over2000":
        price_filter = {"price__gt": 2000}  # Все букеты дороже 2000 руб.
    else:
        price_filter = {"price__lte": int(price_key)}

    # Фильтрация букетов
    STANDARD_OCCASIONS = ["birthday", "wedding", "school", "no_reason"]

    if user_occasion in STANDARD_OCCASIONS:
        # Фильтруем букеты по стандартному поводу
        bouquets = await sync_to_async(list)(
            Bouquet.objects.filter(occasion=user_occasion, **price_filter)
        )
    elif user_occasion and user_occasion not in ["wedding", "school"]:
        # Если пользователь ввел свой повод, исключаем школьные и свадебные букеты
        bouquets = await sync_to_async(list)(
            Bouquet.objects.filter(**price_filter).exclude(
                occasion__in=["wedding", "school"]
            )
        )
    else:
        # Если повод не указан, выбираем все букеты без фильтрации
        bouquets = await sync_to_async(list)(Bouquet.objects.filter(**price_filter))

    if not bouquets:
        await callback.message.answer(
            f"К сожалению, нет букетов для повода {user_occasion} в этом диапазоне 😔"
        )
        return

    # Отправка подходящих букетов
    for bouquet in bouquets:
        text = f"🌸 *{bouquet.name}*\n{bouquet.description}\n💰 Цена: {bouquet.price} руб.\n✨*{bouquet.essence_bouquet}*"
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ Выбрать этот букет",
                        callback_data=f"bouquet_{bouquet.id}",
                    )
                ]
            ]
        )
        if bouquet.image:
            image_path = bouquet.image.path
            if os.path.exists(image_path):
                img_input = FSInputFile(image_path)
                await callback.message.answer_photo(
                    img_input,
                    caption=text,
                    parse_mode="Markdown",
                    reply_markup=keyboard,
                )
            else:
                await callback.message.answer(
                    f"Изображение для букета {bouquet.name} не найдено!"
                )
        else:
            await callback.message.answer(
                text, parse_mode="Markdown", reply_markup=keyboard
            )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🌸 Заказать консультацию", callback_data="consultation"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Посмотреть всю коллекцию", callback_data="all_bouquet"
                )
            ],
        ]
    )
    text = "*Хотите что-то еще более уникальное?*\nПодберите другой букет из нашей коллекции или закажите консультацию флориста"
    await callback.message.answer(text, parse_mode="Markdown", reply_markup=keyboard)
    await callback.answer()


@router.callback_query(lambda c: c.data == "all_bouquet")
async def show_all_bouquets(callback: types.CallbackQuery):
    bouquets = await sync_to_async(list)(Bouquet.objects.all())
    for bouquet in bouquets:
        text = (
            f"🌸 *{bouquet.name}*\n{bouquet.description}\n💰 Цена: {bouquet.price} руб."
        )
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ Выбрать этот букет",
                        callback_data=f"bouquet_{bouquet.id}",
                    )
                ]
            ]
        )
        if bouquet.image:
            image_path = bouquet.image.path
            if os.path.exists(image_path):
                img_input = FSInputFile(image_path)
                await callback.message.answer_photo(
                    img_input,
                    caption=text,
                    parse_mode="Markdown",
                    reply_markup=keyboard,
                )
            else:
                await callback.message.answer(
                    f"Изображение для букета {bouquet.name} не найдено!"
                )
        else:
            await callback.message.answer(
                text, parse_mode="Markdown", reply_markup=keyboard
            )

    await callback.answer()


@router.callback_query(lambda c: c.data.startswith("bouquet_"))
async def handle_bouquet_selection(callback: types.CallbackQuery):
    """Обработчик для выбора букета"""
    bouquet_id = int(callback.data.replace("bouquet_", ""))
    try:
        bouquet = await sync_to_async(Bouquet.objects.get)(id=bouquet_id)
    except Bouquet.DoesNotExist:
        await callback.message.answer("Этот букет больше недоступен 😔")
        return

    text = f"🎉 Вы выбрали букет *{bouquet.name}*! 💐\n💰 Цена: {bouquet.price} руб."
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🛒 Оформить заказ", callback_data=f"order_{bouquet.id}"
                )
            ],
        ]
    )
    await callback.message.answer(text, parse_mode="Markdown", reply_markup=keyboard)
    await callback.answer()


@router.callback_query(lambda c: c.data == "view_collection")
async def view_collection(callback: types.CallbackQuery):
    bouquets = await sync_to_async(list)(Bouquet.objects.all())
    if not bouquets:
        await callback.message.answer("К сожалению, пока нет доступных букетов 😔")
        return
    for bouquet in bouquets:
        text = (
            f"🌸 *{bouquet.name}*\n{bouquet.description}\n💰 Цена: {bouquet.price} руб."
        )
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ Выбрать этот букет",
                        callback_data=f"bouquet_{bouquet.id}",
                    )
                ]
            ]
        )
        if bouquet.image:
            image_path = bouquet.image.path
            if os.path.exists(image_path):
                img_input = FSInputFile(image_path)
                await callback.message.answer_photo(
                    img_input,
                    caption=text,
                    parse_mode="Markdown",
                    reply_markup=keyboard,
                )
            else:
                await callback.message.answer(
                    f"Изображение для букета {bouquet.name} не найдено!"
                )
        else:
            await callback.message.answer(
                text, parse_mode="Markdown", reply_markup=keyboard
            )
    await callback.answer()


# Обработчик начала оформления заказа
@router.callback_query(lambda c: c.data.startswith("order_"))
async def start_order(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик начала оформления заказа"""

    bouquet_id = int(callback.data.replace("order_", ""))

    # Получаем пользователя по Telegram ID
    user, created = await sync_to_async(Customer.objects.get_or_create)(
        tg_id=callback.from_user.id
    )

    # Сохраняем букет в данные пользователя
    selected_bouquet = await sync_to_async(Bouquet.objects.get)(id=bouquet_id)

    # Сохраняем данные в FSM
    await state.update_data(user_id=user.id, bouquet_id=selected_bouquet.id)

    # Запрашиваем имя
    await callback.message.answer("Введите ваше имя:")
    await state.set_state(OrderState.waiting_for_name)

    await callback.answer()


# Обработчик ввода имени
@router.message(OrderState.waiting_for_name)
async def process_name(message: types.Message, state: FSMContext):
    """Сохранение имени и запрос адреса"""
    await sync_to_async(Customer.objects.filter(tg_id=message.from_user.id).update)(
        name=message.text
    )

    await message.answer("Спасибо! Теперь введите ваш адрес для доставки:")
    await state.set_state(OrderState.waiting_for_address)


# Обработчик ввода адреса
@router.message(OrderState.waiting_for_address)
async def process_address(message: types.Message, state: FSMContext):
    """Сохранение адреса и запрос даты/времени"""
    await state.update_data(address=message.text)
    await message.answer(
        "Спасибо! Теперь введите дату и время доставки (например, 10.04.2025 15:30):"
    )
    await state.set_state(OrderState.waiting_for_delivery_time)


@router.message(OrderState.waiting_for_delivery_time)
async def process_delivery_time(message: types.Message, state: FSMContext):
    delivery_time = message.text.strip()

    # Проверяем, что указаны и дата, и время
    if len(delivery_time.split()) == 1:
        await message.answer(
            "Пожалуйста, укажите не только дату, но и точное время доставки (например, 10.04.2025 15:30)."
        )
        return  # Состояние не меняем, бот ждёт новый ввод

    # Пытаемся распарсить дату и время
    parsed_date = dateparser.parse(delivery_time, languages=["ru"])

    # Если не удалось распарсить дату
    if not parsed_date:
        await message.answer(
            "Дата или время указаны неверно. Пожалуйста, введите дату и время в формате: 10.04.2025 15:30."
        )
        return  # Состояние остаётся OrderState.waiting_for_delivery_time

    # Если всё хорошо, сохраняем дату и время
    await state.update_data(delivery_time=parsed_date)

    # Переходим к следующему шагу
    await message.answer("Спасибо! Теперь введите ваш номер телефона:")
    await state.set_state(OrderState.waiting_for_phone)

async def send_order_notifications(user, bouquet, user_data, phone):
    """Отправка уведомлений курьеру и менеджеру"""
    courier_chat_id = os.getenv("COURIER_CHAT_ID")
    manager_chat_id = os.getenv("MANAGER_CHAT_ID")
    text = (
            f"📦 Новый заказ!\n"
            f"👤 Клиент: {user.name}\n"
            f"💐 Букет: {bouquet.name}\n"
            f"📦 Адрес: {user_data['address']}\n"
            f"🕒 Время доставки: {user_data['delivery_time']}\n"
            f"📱 Телефон: {phone}"
        )

        # Отправляем уведомления
    await bot.send_message(chat_id=courier_chat_id, text=text)
    await bot.send_message(chat_id=manager_chat_id, text=text)


@router.message(OrderState.waiting_for_phone)
async def process_phone(message: types.Message, state: FSMContext):
    """Сохранение номера телефона и финальное подтверждение заказа"""
    user_data = await state.get_data()

    if "delivery_time" not in user_data or not user_data["delivery_time"]:
        await message.answer("Ошибка: Время доставки не указано! Укажите время перед оформлением заказа.")
        return
    user = await sync_to_async(Customer.objects.get)(id=user_data["user_id"])
    bouquet = await sync_to_async(Bouquet.objects.get)(id=user_data["bouquet_id"])

    order = await sync_to_async(Order.objects.create)(
        customer=user,
        bouquet=bouquet,
        address=user_data["address"],
        delivery_time=user_data["delivery_time"],
        status="new",
    )

    await sync_to_async(Statistics.objects.create)(
        customer_name=user,
        bouquet_name=bouquet,
        quantity=1,
    )

    await message.answer(
        f"✅ Ваш заказ оформлен!\n💐 Букет: {bouquet.name}\n📦 Адрес: {user_data['address']}\n🕒 Время доставки: {user_data['delivery_time']}\n📱 Телефон: {message.text}"
    )

    asyncio.create_task(send_order_notifications(user, bouquet, user_data, message.text))
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Оформить повторный заказ", callback_data="repeat_order")]
        ]
    )
    await message.answer("Ваш заказ оформлен. Хотите оформить повторный заказ?", reply_markup=keyboard)
    await state.clear()


@router.callback_query(lambda c: c.data == "repeat_order")
async def repeat_order(callback_query: types.CallbackQuery, state: FSMContext):
    # Очистка всех данных, связанных с состоянием
    await state.set_data({})  # Это сбросит все данные состояния

    # Логика для начала нового заказа
    await callback_query.message.answer("Вы можете выбрать новый букет и оформить заказ снова.")

    # Отправляем информацию для повторного выбора
    await callback_query.message.answer("Выберите букет:", reply_markup=keyboards.get_occasion_keyboard())