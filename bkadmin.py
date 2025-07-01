# -*- coding: utf-8 -*-
import asyncio
import logging
import random
import re
from datetime import datetime, timedelta
from typing import Dict, Any

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.filters.state import StateFilter
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
from sqlalchemy.exc import SQLAlchemyError

# Настройка логирования
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)
logging.getLogger("aiogram").setLevel(logging.DEBUG)

# Конфигурация бота
BOT_TOKEN = "YOUR_ADMIN_BOT_TOKEN"  # Замените на токен вашего админ-бота
MAIN_BOT_TOKEN = "7774081383:AAGCn5ayceHhXVJ9p02n1qlJj9GUSzqYiGY"  # Токен основного бота
ADMIN_CHAT_ID = 7566465615
ADMIN_USERNAME = "@win_betuz"
CHANNEL_LINK = "https://t.me/WINBETPROMO"

# Инициализация админ-бота и диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Подключение к базе данных (совместной с основным ботом)
engine = create_engine("sqlite:///betting.db", echo=False)
Base = declarative_base()

# Модели базы данных (идентичны основному боту)
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True)
    username = Column(String)
    phone = Column(String)
    balance = Column(Float, default=0.0)
    language = Column(String, default="ru")
    referral_id = Column(Integer)
    referral_earnings = Column(Float, default=0.0)
    total_winnings = Column(Float, default=0.0)
    game_count = Column(Integer, default=0)
    is_banned = Column(Boolean, default=False)
    deposit_count = Column(Integer, default=0)
    total_deposits = Column(Float, default=0.0)
    withdrawal_count = Column(Integer, default=0)
    total_withdrawals = Column(Float, default=0.0)
    last_daily = Column(DateTime)
    always_win = Column(Boolean, default=False)
    total_bets = Column(Float, default=0.0)
    promos = relationship("UserPromoCode", back_populates="user")
    tasks = relationship("UserTask", back_populates="user")

class PromoCode(Base):
    __tablename__ = "promo_codes"
    id = Column(Integer, primary_key=True)
    code = Column(String, unique=True)
    amount = Column(Float)
    uses_remaining = Column(Integer)
    created_by = Column(Integer)
    users = relationship("UserPromoCode", back_populates="promo_code")

class UserPromoCode(Base):
    __tablename__ = "user_promo_codes"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    promo_code_id = Column(Integer, ForeignKey("promo_codes.id"))
    user = relationship("User", back_populates="promos")
    promo_code = relationship("PromoCode", back_populates="users")

class Task(Base):
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True)
    task_type = Column(String)
    reward = Column(Float)
    link = Column(String)
    min_followers = Column(Integer, default=0)
    active = Column(Boolean, default=True)
    users = relationship("UserTask", back_populates="task")

class UserTask(Base):
    __tablename__ = "user_tasks"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    task_id = Column(Integer, ForeignKey("tasks.id"))
    status = Column(String, default="pending")
    submission = Column(String)
    user = relationship("User", back_populates="tasks")
    task = relationship("Task", back_populates="users")

class WithdrawRequest(Base):
    __tablename__ = "withdraw_requests"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer)
    amount = Column(Float)
    method = Column(String)
    details = Column(String)
    status = Column(String, default="pending")
    timestamp = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(engine)
logger.debug("Таблицы базы данных созданы")
Session = sessionmaker(bind=engine)

# Переводы (для админ-бота)
TRANSLATIONS = {
    "ru": {
        "welcome_admin": "Добро пожаловать, админ {}! Выберите действие:",
        "not_admin": "❌ У вас нет прав администратора!",
        "ban_user": "👤 Введите Telegram ID пользователя для бана:",
        "unban_user": "👤 Введите Telegram ID пользователя для разбана:",
        "user_banned": "✅ Пользователь {} заблокирован!",
        "user_unbanned": "✅ Пользователь {} разблокирован!",
        "user_not_found": "❌ Пользователь с ID {} не найден!",
        "set_always_win": "👤 Введите Telegram ID пользователя для установки always_win:",
        "always_win_set": "✅ Режим always_win установлен для пользователя {}!",
        "create_promo": "🎁 Введите данные промокода (код, сумма, кол-во использований):",
        "promo_created": "✅ Промокод {} создан! Сумма: {}, Использований: {}",
        "promo_invalid": "❌ Неверный формат данных промокода!",
        "error": "❌ Произошла ошибка! Попробуйте позже.",
        "approve_deposit": "✅ Пополнение на {} сум для {} одобрено! Новый баланс: {:.2f} сум",
        "decline_deposit": "❌ Пополнение на {} сум для {} отклонено!",
        "approve_withdraw": "✅ Вывод на {} сум для {} одобрен! Новый баланс: {:.2f} сум",
        "decline_withdraw": "❌ Вывод на {} сум для {} отклонён!",
        "approve_task": "✅ Задание для {} одобрено! Награда: {} сум, Новый баланс: {:.2f} сум",
        "decline_task": "❌ Задание для {} отклонено!",
        "user_info": "👤 Информация о пользователе:\nID: {}\nИмя: {}\nБаланс: {:.2f} сум\nПополнений: {}\nСумма пополнений: {:.2f} сум\nВыводов: {}\nСумма выводов: {:.2f} сум\nВыигрышей: {:.2f} сум\nИгр: {}\nЗабанен: {}\nAlways Win: {}",
        "get_user_info": "👤 Введите Telegram ID пользователя для получения информации:"
    },
    "en": {
        "welcome_admin": "Welcome, admin {}! Choose an action:",
        "not_admin": "❌ You do not have admin privileges!",
        "ban_user": "👤 Enter the Telegram ID of the user to ban:",
        "unban_user": "👤 Enter the Telegram ID of the user to unban:",
        "user_banned": "✅ User {} has been banned!",
        "user_unbanned": "✅ User {} has been unbanned!",
        "user_not_found": "❌ User with ID {} not found!",
        "set_always_win": "👤 Enter the Telegram ID of the user to set always_win:",
        "always_win_set": "✅ Always_win mode set for user {}!",
        "create_promo": "🎁 Enter promo code details (code, amount, uses):",
        "promo_created": "✅ Promo code {} created! Amount: {}, Uses: {}",
        "promo_invalid": "❌ Invalid promo code data format!",
        "error": "❌ An error occurred! Try again later.",
        "approve_deposit": "✅ Deposit of {} UZS for {} approved! New balance: {:.2f} UZS",
        "decline_deposit": "❌ Deposit of {} UZS for {} declined!",
        "approve_withdraw": "✅ Withdrawal of {} UZS for {} approved! New balance: {:.2f} UZS",
        "decline_withdraw": "❌ Withdrawal of {} UZS for {} declined!",
        "approve_task": "✅ Task for {} approved! Reward: {} UZS, New balance: {:.2f} UZS",
        "decline_task": "❌ Task for {} declined!",
        "user_info": "👤 User Info:\nID: {}\nName: {}\nBalance: {:.2f} UZS\nDeposits: {}\nTotal Deposits: {:.2f} UZS\nWithdrawals: {}\nTotal Withdrawals: {:.2f} UZS\nWinnings: {:.2f} UZS\nGames: {}\nBanned: {}\nAlways Win: {}",
        "get_user_info": "👤 Enter the Telegram ID of the user to get info:"
    }
}

# Клавиатуры
def get_admin_menu(language: str) -> ReplyKeyboardMarkup:
    translations = TRANSLATIONS.get(language, TRANSLATIONS["ru"])
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🚫 Забанить пользователя"), KeyboardButton(text="✅ Разбанить пользователя")],
            [KeyboardButton(text="🎁 Создать промокод"), KeyboardButton(text="🔮 Установить always_win")],
            [KeyboardButton(text="📊 Информация о пользователе")]
        ],
        resize_keyboard=True
    )

# Состояния FSM для админ-бота
class AdminState(StatesGroup):
    ban_user = State()
    unban_user = State()
    set_always_win = State()
    create_promo = State()
    get_user_info = State()

# Проверка, является ли пользователь админом
async def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_CHAT_ID or str(user_id) == str(ADMIN_CHAT_ID)

# Обработчик команды /start для админ-бота
@dp.message(Command("start"))
async def admin_start_command(message: types.Message, state: FSMContext):
    logger.debug(f"Получена команда /start от {message.from_user.id}")
    if not await is_admin(message.from_user.id):
        await message.answer(TRANSLATIONS["ru"]["not_admin"], parse_mode="HTML")
        return
    language = "ru"  # Админ-бот использует русский по умолчанию
    translations = TRANSLATIONS[language]
    await message.answer(
        translations["welcome_admin"].format(message.from_user.username or "Admin"),
        parse_mode="HTML",
        reply_markup=get_admin_menu(language)
    )
    await state.clear()

# Обработчик бана пользователя
@dp.message(lambda message: message.text == "🚫 Забанить пользователя")
async def ban_user_command(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await message.answer(TRANSLATIONS["ru"]["not_admin"], parse_mode="HTML")
        return
    language = "ru"
    translations = TRANSLATIONS[language]
    await message.answer(
        translations["ban_user"],
        parse_mode="HTML"
    )
    await state.set_state(AdminState.ban_user)

@dp.message(StateFilter(AdminState.ban_user))
async def process_ban_user(message: types.Message, state: FSMContext):
    session = Session()
    try:
        language = "ru"
        translations = TRANSLATIONS[language]
        try:
            user_id = int(message.text)
        except ValueError:
            await message.answer(
                translations["ban_user"],
                parse_mode="HTML"
            )
            return
        user = session.query(User).filter_by(telegram_id=user_id).first()
        if not user:
            await message.answer(
                translations["user_not_found"].format(user_id),
                parse_mode="HTML",
                reply_markup=get_admin_menu(language)
            )
            await state.clear()
            return
        user.is_banned = True
        session.commit()
        await message.answer(
            translations["user_banned"].format(user_id),
            parse_mode="HTML",
            reply_markup=get_admin_menu(language)
        )
        await bot.send_message(
            chat_id=user_id,
            text="❌ Вы были заблокированы администратором!",
            parse_mode="HTML"
        )
        await state.clear()
    except Exception as e:
        session.rollback()
        logger.error(f"Ошибка в process_ban_user: {str(e)}", exc_info=True)
        await message.answer(
            translations["error"],
            parse_mode="HTML",
            reply_markup=get_admin_menu(language)
        )
        await state.clear()
    finally:
        session.close()

# Обработчик разбана пользователя
@dp.message(lambda message: message.text == "✅ Разбанить пользователя")
async def unban_user_command(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await message.answer(TRANSLATIONS["ru"]["not_admin"], parse_mode="HTML")
        return
    language = "ru"
    translations = TRANSLATIONS[language]
    await message.answer(
        translations["unban_user"],
        parse_mode="HTML"
    )
    await state.set_state(AdminState.unban_user)

@dp.message(StateFilter(AdminState.unban_user))
async def process_unban_user(message: types.Message, state: FSMContext):
    session = Session()
    try:
        language = "ru"
        translations = TRANSLATIONS[language]
        try:
            user_id = int(message.text)
        except ValueError:
            await message.answer(
                translations["unban_user"],
                parse_mode="HTML"
            )
            return
        user = session.query(User).filter_by(telegram_id=user_id).first()
        if not user:
            await message.answer(
                translations["user_not_found"].format(user_id),
                parse_mode="HTML",
                reply_markup=get_admin_menu(language)
            )
            await state.clear()
            return
        user.is_banned = False
        session.commit()
        await message.answer(
            translations["user_unbanned"].format(user_id),
            parse_mode="HTML",
            reply_markup=get_admin_menu(language)
        )
        await bot.send_message(
            chat_id=user_id,
            text="✅ Вы были разблокированы администратором!",
            parse_mode="HTML",
            reply_markup=get_main_menu(user.language)
        )
        await state.clear()
    except Exception as e:
        session.rollback()
        logger.error(f"Ошибка в process_unban_user: {str(e)}", exc_info=True)
        await message.answer(
            translations["error"],
            parse_mode="HTML",
            reply_markup=get_admin_menu(language)
        )
        await state.clear()
    finally:
        session.close()

# Обработчик установки always_win
@dp.message(lambda message: message.text == "🔮 Установить always_win")
async def set_always_win_command(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await message.answer(TRANSLATIONS["ru"]["not_admin"], parse_mode="HTML")
        return
    language = "ru"
    translations = TRANSLATIONS[language]
    await message.answer(
        translations["set_always_win"],
        parse_mode="HTML"
    )
    await state.set_state(AdminState.set_always_win)

@dp.message(StateFilter(AdminState.set_always_win))
async def process_set_always_win(message: types.Message, state: FSMContext):
    session = Session()
    try:
        language = "ru"
        translations = TRANSLATIONS[language]
        try:
            user_id = int(message.text)
        except ValueError:
            await message.answer(
                translations["set_always_win"],
                parse_mode="HTML"
            )
            return
        user = session.query(User).filter_by(telegram_id=user_id).first()
        if not user:
            await message.answer(
                translations["user_not_found"].format(user_id),
                parse_mode="HTML",
                reply_markup=get_admin_menu(language)
            )
            await state.clear()
            return
        user.always_win = True
        session.commit()
        await message.answer(
            translations["always_win_set"].format(user_id),
            parse_mode="HTML",
            reply_markup=get_admin_menu(language)
        )
        await bot.send_message(
            chat_id=user_id,
            text="🔮 Ваш режим always_win активирован администратором!",
            parse_mode="HTML"
        )
        await state.clear()
    except Exception as e:
        session.rollback()
        logger.error(f"Ошибка в process_set_always_win: {str(e)}", exc_info=True)
        await message.answer(
            translations["error"],
            parse_mode="HTML",
            reply_markup=get_admin_menu(language)
        )
        await state.clear()
    finally:
        session.close()

# Обработчик создания промокода
@dp.message(lambda message: message.text == "🎁 Создать промокод")
async def create_promo_command(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await message.answer(TRANSLATIONS["ru"]["not_admin"], parse_mode="HTML")
        return
    language = "ru"
    translations = TRANSLATIONS[language]
    await message.answer(
        translations["create_promo"],
        parse_mode="HTML"
    )
    await state.set_state(AdminState.create_promo)

@dp.message(StateFilter(AdminState.create_promo))
async def process_create_promo(message: types.Message, state: FSMContext):
    session = Session()
    try:
        language = "ru"
        translations = TRANSLATIONS[language]
        try:
            code, amount, uses = message.text.split()
            amount = float(amount)
            uses = int(uses)
            if amount <= 0 or uses <= 0:
                raise ValueError
        except ValueError:
            await message.answer(
                translations["promo_invalid"],
                parse_mode="HTML"
            )
            return
        promo = PromoCode(
            code=code,
            amount=amount,
            uses_remaining=uses,
            created_by=message.from_user.id
        )
        session.add(promo)
        session.commit()
        await message.answer(
            translations["promo_created"].format(code, amount, uses),
            parse_mode="HTML",
            reply_markup=get_admin_menu(language)
        )
        await state.clear()
    except Exception as e:
        session.rollback()
        logger.error(f"Ошибка в process_create_promo: {str(e)}", exc_info=True)
        await message.answer(
            translations["error"],
            parse_mode="HTML",
            reply_markup=get_admin_menu(language)
        )
        await state.clear()
    finally:
        session.close()

# Обработчик получения информации о пользователе
@dp.message(lambda message: message.text == "📊 Информация о пользователе")
async def get_user_info_command(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await message.answer(TRANSLATIONS["ru"]["not_admin"], parse_mode="HTML")
        return
    language = "ru"
    translations = TRANSLATIONS[language]
    await message.answer(
        translations["get_user_info"],
        parse_mode="HTML"
    )
    await state.set_state(AdminState.get_user_info)

@dp.message(StateFilter(AdminState.get_user_info))
async def process_get_user_info(message: types.Message, state: FSMContext):
    session = Session()
    try:
        language = "ru"
        translations = TRANSLATIONS[language]
        try:
            user_id = int(message.text)
        except ValueError:
            await message.answer(
                translations["get_user_info"],
                parse_mode="HTML"
            )
            return
        user = session.query(User).filter_by(telegram_id=user_id).first()
        if not user:
            await message.answer(
                translations["user_not_found"].format(user_id),
                parse_mode="HTML",
                reply_markup=get_admin_menu(language)
            )
            await state.clear()
            return
        await message.answer(
            translations["user_info"].format(
                user.telegram_id,
                user.username or "User",
                user.balance,
                user.deposit_count,
                user.total_deposits,
                user.withdrawal_count,
                user.total_withdrawals,
                user.total_winnings,
                user.game_count,
                "Да" if user.is_banned else "Нет",
                "Да" if user.always_win else "Нет"
            ),
            parse_mode="HTML",
            reply_markup=get_admin_menu(language)
        )
        await state.clear()
    except Exception as e:
        session.rollback()
        logger.error(f"Ошибка в process_get_user_info: {str(e)}", exc_info=True)
        await message.answer(
            translations["error"],
            parse_mode="HTML",
            reply_markup=get_admin_menu(language)
        )
        await state.clear()
    finally:
        session.close()

# Обработчик одобрения пополнения
@dp.message(lambda message: message.text.startswith("/approve_deposit_"))
async def approve_deposit(message: types.Message):
    if not await is_admin(message.from_user.id):
        await message.answer(TRANSLATIONS["ru"]["not_admin"], parse_mode="HTML")
        return
    session = Session()
    try:
        language = "ru"
        translations = TRANSLATIONS[language]
        try:
            _, user_id, amount = message.text.split("_")
            user_id = int(user_id)
            amount = float(amount)
        except ValueError:
            await message.answer(
                translations["error"],
                parse_mode="HTML",
                reply_markup=get_admin_menu(language)
            )
            return
        user = session.query(User).filter_by(telegram_id=user_id).first()
        if not user:
            await message.answer(
                translations["user_not_found"].format(user_id),
                parse_mode="HTML",
                reply_markup=get_admin_menu(language)
            )
            return
        user.balance += amount
        user.deposit_count += 1
        user.total_deposits += amount
        session.commit()
        await message.answer(
            translations["approve_deposit"].format(amount, user.username or "User", user.balance),
            parse_mode="HTML",
            reply_markup=get_admin_menu(language)
        )
        await bot.send_message(
            chat_id=user_id,
            text=translations["deposit_success"].format(amount, user.balance),
            parse_mode="HTML",
            reply_markup=get_main_menu(user.language)
        )
    except Exception as e:
        session.rollback()
        logger.error(f"Ошибка в approve_deposit: {str(e)}", exc_info=True)
        await message.answer(
            translations["error"],
            parse_mode="HTML",
            reply_markup=get_admin_menu(language)
        )
    finally:
        session.close()

# Обработчик отклонения пополнения
@dp.message(lambda message: message.text.startswith("/decline_deposit_"))
async def decline_deposit(message: types.Message):
    if not await is_admin(message.from_user.id):
        await message.answer(TRANSLATIONS["ru"]["not_admin"], parse_mode="HTML")
        return
    session = Session()
    try:
        language = "ru"
        translations = TRANSLATIONS[language]
        try:
            _, user_id, amount = message.text.split("_")
            user_id = int(user_id)
            amount = float(amount)
        except ValueError:
            await message.answer(
                translations["error"],
                parse_mode="HTML",
                reply_markup=get_admin_menu(language)
            )
            return
        user = session.query(User).filter_by(telegram_id=user_id).first()
        if not user:
            await message.answer(
                translations["user_not_found"].format(user_id),
                parse_mode="HTML",
                reply_markup=get_admin_menu(language)
            )
            return
        await message.answer(
            translations["decline_deposit"].format(amount, user.username or "User"),
            parse_mode="HTML",
            reply_markup=get_admin_menu(language)
        )
        await bot.send_message(
            chat_id=user_id,
            text="❌ Ваш запрос на пополнение на {} сум был отклонён!".format(amount),
            parse_mode="HTML",
            reply_markup=get_main_menu(user.language)
        )
    except Exception as e:
        session.rollback()
        logger.error(f"Ошибка в decline_deposit: {str(e)}", exc_info=True)
        await message.answer(
            translations["error"],
            parse_mode="HTML",
            reply_markup=get_admin_menu(language)
        )
    finally:
        session.close()

# Обработчик одобрения вывода
@dp.message(lambda message: message.text.startswith("/approve_withdraw_"))
async def approve_withdraw(message: types.Message):
    if not await is_admin(message.from_user.id):
        await message.answer(TRANSLATIONS["ru"]["not_admin"], parse_mode="HTML")
        return
    session = Session()
    try:
        language = "ru"
        translations = TRANSLATIONS[language]
        try:
            _, user_id, amount = message.text.split("_")
            user_id = int(user_id)
            amount = float(amount)
        except ValueError:
            await message.answer(
                translations["error"],
                parse_mode="HTML",
                reply_markup=get_admin_menu(language)
            )
            return
        user = session.query(User).filter_by(telegram_id=user_id).first()
        if not user:
            await message.answer(
                translations["user_not_found"].format(user_id),
                parse_mode="HTML",
                reply_markup=get_admin_menu(language)
            )
            return
        withdraw_request = session.query(WithdrawRequest).filter_by(user_id=user_id, amount=amount, status="pending").first()
        if not withdraw_request:
            await message.answer(
                translations["error"],
                parse_mode="HTML",
                reply_markup=get_admin_menu(language)
            )
            return
        user.withdrawal_count += 1
        user.total_withdrawals += amount
        withdraw_request.status = "approved"
        session.commit()
        await message.answer(
            translations["approve_withdraw"].format(amount, user.username or "User", user.balance),
            parse_mode="HTML",
            reply_markup=get_admin_menu(language)
        )
        await bot.send_message(
            chat_id=user_id,
            text=translations["withdraw_success"].format(amount, user.balance),
            parse_mode="HTML",
            reply_markup=get_main_menu(user.language)
        )
    except Exception as e:
        session.rollback()
        logger.error(f"Ошибка в approve_withdraw: {str(e)}", exc_info=True)
        await message.answer(
            translations["error"],
            parse_mode="HTML",
            reply_markup=get_admin_menu(language)
        )
    finally:
        session.close()

# Обработчик отклонения вывода
@dp.message(lambda message: message.text.startswith("/decline_withdraw_"))
async def decline_withdraw(message: types.Message):
    if not await is_admin(message.from_user.id):
        await message.answer(TRANSLATIONS["ru"]["not_admin"], parse_mode="HTML")
        return
    session = Session()
    try:
        language = "ru"
        translations = TRANSLATIONS[language]
        try:
            _, user_id, amount = message.text.split("_")
            user_id = int(user_id)
            amount = float(amount)
        except ValueError:
            await message.answer(
                translations["error"],
                parse_mode="HTML",
                reply_markup=get_admin_menu(language)
            )
            return
        user = session.query(User).filter_by(telegram_id=user_id).first()
        if not user:
            await message.answer(
                translations["user_not_found"].format(user_id),
                parse_mode="HTML",
                reply_markup=get_admin_menu(language)
            )
            return
        withdraw_request = session.query(WithdrawRequest).filter_by(user_id=user_id, amount=amount, status="pending").first()
        if not withdraw_request:
            await message.answer(
                translations["error"],
                parse_mode="HTML",
                reply_markup=get_admin_menu(language)
            )
            return
        user.balance += amount
        withdraw_request.status = "declined"
        session.commit()
        await message.answer(
            translations["decline_withdraw"].format(amount, user.username or "User"),
            parse_mode="HTML",
            reply_markup=get_admin_menu(language)
        )
        await bot.send_message(
            chat_id=user_id,
            text="❌ Ваш запрос на вывод на {} сум был отклонён! Баланс возвращён: {:.2f} сум".format(amount, user.balance),
            parse_mode="HTML",
            reply_markup=get_main_menu(user.language)
        )
    except Exception as e:
        session.rollback()
        logger.error(f"Ошибка в decline_withdraw: {str(e)}", exc_info=True)
        await message.answer(
            translations["error"],
            parse_mode="HTML",
            reply_markup=get_admin_menu(language)
        )
    finally:
        session.close()

# Обработчик одобрения задания
@dp.message(lambda message: message.text.startswith("/approve_task_"))
async def approve_task(message: types.Message):
    if not await is_admin(message.from_user.id):
        await message.answer(TRANSLATIONS["ru"]["not_admin"], parse_mode="HTML")
        return
    session = Session()
    try:
        language = "ru"
        translations = TRANSLATIONS[language]
        try:
            _, user_id, task_id = message.text.split("_")
            user_id = int(user_id)
            task_id = int(task_id)
        except ValueError:
            await message.answer(
                translations["error"],
                parse_mode="HTML",
                reply_markup=get_admin_menu(language)
            )
            return
        user = session.query(User).filter_by(telegram_id=user_id).first()
        task = session.query(Task).filter_by(id=task_id).first()
        user_task = session.query(UserTask).filter_by(user_id=user.id, task_id=task_id, status="pending").first()
        if not user or not task or not user_task:
            await message.answer(
                translations["user_not_found"].format(user_id),
                parse_mode="HTML",
                reply_markup=get_admin_menu(language)
            )
            return
        user_task.status = "completed"
        user.balance += task.reward
        session.commit()
        await message.answer(
            translations["approve_task"].format(user.username or "User", task.reward, user.balance),
            parse_mode="HTML",
            reply_markup=get_admin_menu(language)
        )
        await bot.send_message(
            chat_id=user_id,
            text=translations["task_approved"].format(task.reward, user.balance),
            parse_mode="HTML",
            reply_markup=get_main_menu(user.language)
        )
    except Exception as e:
        session.rollback()
        logger.error(f"Ошибка в approve_task: {str(e)}", exc_info=True)
        await message.answer(
            translations["error"],
            parse_mode="HTML",
            reply_markup=get_admin_menu(language)
        )
    finally:
        session.close()

# Обработчик отклонения задания
@dp.message(lambda message: message.text.startswith("/decline_task_"))
async def decline_task(message: types.Message):
    if not await is_admin(message.from_user.id):
        await message.answer(TRANSLATIONS["ru"]["not_admin"], parse_mode="HTML")
        return
    session = Session()
    try:
        language = "ru"
        translations = TRANSLATIONS[language]
        try:
            _, user_id, task_id = message.text.split("_")
            user_id = int(user_id)
            task_id = int(task_id)
        except ValueError:
            await message.answer(
                translations["error"],
                parse_mode="HTML",
                reply_markup=get_admin_menu(language)
            )
            return
        user = session.query(User).filter_by(telegram_id=user_id).first()
        user_task = session.query(UserTask).filter_by(user_id=user.id, task_id=task_id, status="pending").first()
        if not user or not user_task:
            await message.answer(
                translations["user_not_found"].format(user_id),
                parse_mode="HTML",
                reply_markup=get_admin_menu(language)
            )
            return
        user_task.status = "declined"
        session.commit()
        await message.answer(
            translations["decline_task"].format(user.username or "User"),
            parse_mode="HTML",
            reply_markup=get_admin_menu(language)
        )
        await bot.send_message(
            chat_id=user_id,
            text="❌ Ваш запрос на выполнение задания был отклонён!",
            parse_mode="HTML",
            reply_markup=get_main_menu(user.language)
        )
    except Exception as e:
        session.rollback()
        logger.error(f"Ошибка в decline_task: {str(e)}", exc_info=True)
        await message.answer(
            translations["error"],
            parse_mode="HTML",
            reply_markup=get_admin_menu(language)
        )
    finally:
        session.close()

# Клавиатуры из основного бота (для совместимости)
def get_main_menu(language: str) -> ReplyKeyboardMarkup:
    translations = TRANSLATIONS.get(language, TRANSLATIONS["ru"])
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🎰 Слоты 🎰"), KeyboardButton(text="🎲 Кости 🎲")],
            [KeyboardButton(text="🃏 Блэкджек 🎴"), KeyboardButton(text="🪙 Орёл и Решка 🪙")],
            [KeyboardButton(text="💣 Мины 💣"), KeyboardButton(text="🎡 Рулетка 🎡")],
            [KeyboardButton(text="🎲 Больше/Меньше 7 🎲"), KeyboardButton(text="🎨 Угадай Цвет 🎨")],
            [KeyboardButton(text="👤 Профиль 📊"), KeyboardButton(text="💰 Баланс 💳")],
            [KeyboardButton(text="💸 Пополнить 📩"), KeyboardButton(text="💸 Вывести 💳")],
            [KeyboardButton(text="🎁 Ввести промокод"), KeyboardButton(text="🎁 Ежедневный бонус")],
            [KeyboardButton(text="📋 Задания")]
        ],
        resize_keyboard=True
    )

# Запуск админ-бота
async def main():
    try:
        logger.info("Запуск админ-бота...")
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {str(e)}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(main())