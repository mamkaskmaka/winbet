import asyncio
import logging
import random
import re 
import string
import json
import html
from datetime import datetime, timedelta
from typing import Dict, Any
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, CommandStart, BaseFilter
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from sqlalchemy.orm import Session
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    ReplyKeyboardMarkup, 
    KeyboardButton, 
    InlineKeyboardMarkup, 
    InlineKeyboardButton,
    Message,
    CallbackQuery,
    ChatMember
)
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
from sqlalchemy.exc import SQLAlchemyError


# Пользовательский фильтр для команд с регулярными выражениями
class RegexpCommandsFilter(BaseFilter):
    def __init__(self, regexp_commands: list[str]):
        self.regexp_commands = regexp_commands

    async def __call__(self, message: Message) -> bool | dict:
        if message.text is None:
            return False
        for regexp in self.regexp_commands:
            match = re.match(regexp, message.text)
            if match:
                return {"regexp_command": match}
        return False

# Настройка логирования
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
# Конфигурация бота
BOT_TOKEN = "7774081383:AAGCn5ayceHhXVJ9p02n1qlJj9GUSzqYiGY"  # Ваш токен
ADMIN_CHAT_ID = 7566465615  # Ваш ID в Telegram
ADMIN_USERNAME = "@win_betuz"
CHANNEL_LINK = "https://t.me/WINBETPROMO"

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Множество для отслеживания обработанных сообщений
processed_messages = set()

# Настройка базы данных
engine = create_engine("sqlite:///betting.db", echo=False)
Base = declarative_base()

# Модели базы данных
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

# Переводы
TRANSLATIONS = {
    "ru": {
        "welcome": "Добро пожаловать, {}! Присоединяйтесь к нашему каналу: {}\nВыберите язык:",
        "welcome_back": "С возвращением, {}! Ваш баланс: {:.2f} сум",
        "language_selected": "Язык установлен: Русский",
        "enter_phone": "📱 Пожалуйста, отправьте свой номер телефона, нажав кнопку ниже:",
        "registration_success": "Регистрация завершена!\nID: {}\nБот: @{}\nВаш реферальный код: {}\nПриглашайте друзей и получайте бонусы!",
        "welcome_bonus": "🎉 Вы получили приветственный бонус: {:.2f} сум!",
        "referral_bonus": "🎉 Вы получили бонус {} сум за приглашение {}!",
        "new_user_notification": "Новый пользователь!\nID: {}\nВнутренний ID: {}\nИмя: {}\nТелефон: {}\nЯзык: {}\nРеферал: {}",
        "balance": "💰 Ваш баланс: {:.2f} сум",
        "invalid_bet": "❌ Неверная сумма ставки! Минимальная ставка 1000 сум, ваш баланс: {:.2f} сум",
        "insufficient_balance": "❌ Недостаточно средств! Ваш баланс: {:.2f} сум",
        "bet_prompt": "💸 Введите сумму ставки (минимум 1000 сум, например, 1500.0):",
        "dice_start": "🎲 Выберите число от 1 до 6:",
        "dice_win": "🎉 Вы угадали! Выпало: {}. Вы выиграли: {:.2f} сум. Ваш баланс: {:.2f} сум",
        "dice_lose": "😔 Вы не угадали. Выпало: {}. Ваш баланс: {:.2f} сум",
        "slots_start": "🎰 Нажмите, чтобы крутить слоты!",
        "slots_result": "🎰 Результат: {}\n{} Ваш баланс: {:.2f} сум",
        "blackjack_start": "🃏 Ваши карты: {}. Сумма: {}\nХотите взять ещё карту?",
        "blackjack_win": "🎉 Вы выиграли: {:.2f} сум! Ваш баланс: {:.2f} сум",
        "blackjack_lose": "😔 Вы проиграли. Дилер: {}. Ваш баланс: {:.2f} сум",
        "blackjack_bust": "😔 Перебор! Сумма: {}. Ваш баланс: {:.2f} сум",
        "coinflip_start": "🪙 Выберите: Орёл или Решка?",
        "coinflip_win": "🎉 Вы угадали: {}! Вы выиграли: {:.2f} сум. Ваш баланс: {:.2f} сум",
        "coinflip_lose": "😔 Не угадали: {}. Ваш баланс: {:.2f} сум",
        "mines_start": "💣 Выберите ячейку на поле 3x3 (3 мины):",
        "mines_win": "✅ Безопасная ячейка! Текущий множитель: {:.2f}x. Баланс: {:.2f} сум",
        "mines_lose": "💥 Вы попали на мину! Ваш баланс: {:.2f} сум",
        "mines_cashout": "🎉 Вы забрали выигрыш! Множитель: {:.2f}x, Выигрыш: {:.2f} сум, Баланс: {:.2f} сум",
        "roulette_start": "🎡 Выберите цвет: Красное, Чёрное или Зелёное",
        "roulette_win": "🎉 Вы угадали: {}! Вы выиграли: {:.2f} сум. Ваш баланс: {:.2f} сум",
        "roulette_lose": "😔 Не угадали: {}. Ваш баланс: {:.2f} сум",
        "overunder_start": "🎲 Больше или Меньше 7?",
        "overunder_win": "🎉 Вы угадали! Сумма: {}. Вы выиграли: {:.2f} сум. Ваш баланс: {:.2f} сум",
        "overunder_lose": "😔 Не угадали. Сумма: {}. Ваш баланс: {:.2f} сум",
        "guesscolor_start": "🎨 Угадайте цвет: Красный, Синий, Жёлтый, Зелёный",
        "guesscolor_win": "🎉 Вы угадали: {}! Вы выиграли: {:.2f} сум. Ваш баланс: {:.2f} сум",
        "guesscolor_lose": "😔 Не угадали: {}. Ваш баланс: {:.2f} сум",
        "enter_promo": "🎁 Введите промокод:",
        "promo_success": "🎉 Промокод активирован! Вы получили: {:.2f} сум. Ваш баланс: {:.2f} сум",
        "promo_invalid": "❌ Неверный промокод или он уже использован!",
        "daily_bonus": "🎁 Вы получили ежедневный бонус: {:.2f} сум! Ваш баланс: {:.2f} сум",
        "daily_already_claimed": "❌ Вы уже получили ежедневный бонус сегодня!",
        "deposit_method": "💸 Выберите способ пополнения:",
        "deposit_amount": "💸 Введите сумму пополнения (минимум 1000 сум):",
        "deposit_details": "💸 Введите реквизиты для пополнения (например, номер карты или кошелька):",
        "deposit_success": "✅ Запрос на пополнение {} сум отправлен админу! Ваш баланс: {:.2f} сум",
        "withdraw_method": "💸 Выберите способ вывода:",
        "withdraw_amount": "💸 Введите сумму вывода (минимум 1000 сум):",
        "withdraw_details": "💸 Введите реквизиты для вывода (например, номер карты или кошелька):",
        "withdraw_success": "✅ Запрос на вывод {} сум отправлен админу! Ваш баланс: {:.2f} сум",
        "withdraw_bonus_restriction": "❌ Для вывода бонусного баланса сделайте депозит и прокрутите баланс на ставках с коэффициентом минимум 1.1!",
        "withdraw_no_bets": "❌ Сделайте ставку своим балансом с коэффициентом минимум 1.1!",
        "admin_deposit_request": "💸 Новый запрос на пополнение!\nID: {}\nИмя: {}\nСумма: {} сум\nМетод: {}\nРеквизиты: {}\n\nОдобрить: /approve_deposit_{}_{}\nОтклонить: /decline_deposit_{}_{}",
        "admin_withdraw_request": "💸 Новый запрос на вывод!\nID: {}\nИмя: {}\nСумма: {} сум\nМетод: {}\nРеквизиты: {}\n\nОдобрить: /approve_withdraw_{}_{}\nОтклонить: /decline_withdraw_{}_{}",
        "admin_deposit_approve": "✅ Пополнение на {} сум для {} одобрено! Новый баланс: {:.2f} сум",
        "admin_deposit_decline": "❌ Пополнение на {} сум для {} отклонено!",
        "admin_withdraw_approve": "✅ Вывод на {} сум для {} одобрен! Новый баланс: {:.2f} сум",
        "admin_withdraw_decline": "❌ Вывод на {} сум для {} отклонён!",
        "profile": "👤 Профиль:\nID: {}\nПополнений: {}\nСумма пополнений: {:.2f} сум\nВыводов: {}\nСумма выводов: {:.2f} сум\nВыигрышей: {:.2f} сум\nБаланс: {:.2f} сум",
        "tasks_menu": "📋 Доступные задания:\n1. Подписка на Telegram-канал: 700 сум\n2. Подписка на Instagram: 1000 сум\n3. Репост поста/видео: 3000 сум\n4. Подписка на канал WINBETPROMO: 500 сум\nВыберите задание:",
        "task_telegram_sub": "📩 Подпишитесь на канал {} и нажмите 'Проверить подписку'.",
        "task_instagram_sub": "📸 Подпишитесь на Instagram {} и отправьте ваш ник для проверки.",
        "task_repost": "📢 Сделайте репост {} и отправьте ссылку на историю.",
        "task_check_subscription": "🔍 Проверить подписку",
        "task_submit_nickname": "📩 Отправьте ваш Instagram ник",
        "task_submit_repost": "📩 Отправьте ссылку на репост",
        "task_success": "✅ Задание выполнено! Вы получили {} сум. Ваш баланс: {:.2f} сум",
        "task_already_completed": "❌ Вы уже выполнили это задание!",
        "task_invalid_submission": "❌ Неверные данные! Отправьте корректный ник или ссылку.",
        "task_instagram_low_followers": "❌ Ваш Instagram аккаунт имеет менее 20 подписчиков!",
        "task_not_subscribed": "❌ Вы не подписаны на канал! Подпишитесь и попробуйте снова.",
        "admin_task_request": "📋 Новый запрос на задание!\nПользователь: {}\nИмя: {}\nТип задания: {}\nОтправка: {}\nНаграда: {} сум\nID задания: {}\nID пользователя: {}",
        "task_submit": "📋 Отправьте данные для проверки задания (например, ваш Instagram ник):",
        "task_already_submitted": "❌ Вы уже отправили это задание на проверку!",
        "tasks_none": "❌ Нет доступных заданий на данный момент!",
        "error": "❌ Произошла ошибка! Попробуйте позже.",
        "admin_menu": "👨‍💻 Админ-панель Выберите действие:",
        "admin_stats": "📊 Статистика бота:\nПользователей: {}\nАктивных: {}\nБаланс системы: {:.2f} сум",
        "admin_user_info": "👤 Информация о пользователе:\nID: {}\nИмя: {}\nБаланс: {:.2f} сум\nПополнений: {}\nВыводов: {}\nРефералов: {}",
        "admin_user_not_found": "❌ Пользователь не найден!",
        "admin_balance_changed": "✅ Баланс пользователя {} изменен на {:.2f} сум. Новый баланс: {:.2f} сум",
        "admin_promocode_created": "🎟 Создан промокод: {}\nСумма: {:.2f} сум\nАктиваций: {}",
        "admin_promocode_list": "📋 Список активных промокодов:\n{}",
        "admin_broadcast_started": "📢 Рассылка начата! Охват: {} пользователей",
        "admin_broadcast_completed": "✅ Рассылка завершена!\nОтправлено: {}\nНе удалось: {}",
        "admin_help": (
            "📚 Справка по админ-командам:\n"
            "/add_balance [id] [sum] - Пополнить баланс\n"
            "/withdraw_balance [id] [sum] - Снять средства\n"
            "/create_promocode [sum] [uses] - Создать промокод\n"
            "/user_info [id] - Информация о пользователе\n"
            "/broadcast - Сделать рассылку\n"
            "/stats - Статистика бота"
        ),
        "broadcast_prompt": "📢 Введите текст для рассылки всем пользователям:",
        "deposit_prompt": "💳 Введите ID пользователя и сумму пополнения (например, 123456789 1000):",
        "withdraw_prompt": "💸 Введите ID пользователя и сумму для вывода (например, 123456789 1000):",
        "promocode_prompt": "🎟 Введите сумму и количество активаций для промокода (например, 5000 10):",
        "not_admin": "❌ У вас нет прав администратора!"
    },
    "en": {
        "welcome": "Welcome, {}! Join our channel: {}\nChoose a language:",
        "welcome_back": "Welcome back, {}! Your balance: {:.2f} UZS",
        "language_selected": "Language set: English",
        "enter_phone": "📱 Please send your phone number by clicking the button below:",
        "registration_success": "Registration completed!\nID: {}\nBot: @{}\nYour referral code: {}\nInvite friends and earn bonuses!",
        "welcome_bonus": "🎉 You received a welcome bonus: {:.2f} UZS!",
        "referral_bonus": "🎉 You received a bonus of {} UZS for inviting {}!",
        "new_user_notification": "New user!\nID: {}\nInternal ID: {}\nName: {}\nPhone: {}\nLanguage: {}\nReferral: {}",
        "balance": "💰 Your balance: {:.2f} UZS",
        "invalid_bet": "❌ Invalid bet amount! Minimum bet is 1000 UZS, your balance: {:.2f} UZS",
        "insufficient_balance": "❌ Insufficient funds! Your balance: {:.2f} UZS",
        "bet_prompt": "💸 Enter the bet amount (minimum 1000 UZS, e.g., 1500.0):",
        "dice_start": "🎲 Choose a number from 1 to 6:",
        "dice_win": "🎉 You guessed it! Rolled: {}. You won: {:.2f} UZS. Your balance: {:.2f} UZS",
        "dice_lose": "😔 You didn't guess it. Rolled: {}. Your balance: {:.2f} UZS",
        "slots_start": "🎰 Press to spin the slots!",
        "slots_result": "🎰 Result: {}\n{} Your balance: {:.2f} UZS",
        "blackjack_start": "🃏 Your cards: {}. Total: {}\nWould you like to hit?",
        "blackjack_win": "🎉 You won: {:.2f} UZS! Your balance: {:.2f} UZS",
        "blackjack_lose": "😔 You lost. Dealer: {}. Your balance: {:.2f} UZS",
        "blackjack_bust": "😔 Bust! Total: {}. Your balance: {:.2f} UZS",
        "coinflip_start": "🪙 Choose: Heads or Tails?",
        "coinflip_win": "🎉 You guessed it: {}! You won: {:.2f} UZS. Your balance: {:.2f} UZS",
        "coinflip_lose": "😔 You didn't guess it: {}. Your balance: {:.2f} UZS",
        "mines_start": "💣 Choose a cell on the 3x3 grid (3 mines):",
        "mines_win": "✅ Safe cell! Current multiplier: {:.2f}x. Balance: {:.2f} UZS",
        "mines_lose": "💥 You hit a mine! Your balance: {:.2f} UZS",
        "mines_cashout": "🎉 You cashed out! Multiplier: {:.2f}x, Winnings: {:.2f} UZS, Balance: {:.2f} UZS",
        "roulette_start": "🎡 Choose a color: Red, Black, or Green",
        "roulette_win": "🎉 You guessed it: {}! You won: {:.2f} UZS. Your balance: {:.2f} UZS",
        "roulette_lose": "😔 You didn't guess it: {}. Your balance: {:.2f} UZS",
        "overunder_start": "🎲 Over or Under 7?",
        "overunder_win": "🎉 You guessed it! Sum: {}. You won: {:.2f} UZS. Your balance: {:.2f} UZS",
        "overunder_lose": "😔 You didn't guess it. Sum: {}. Your balance: {:.2f} UZS",
        "guesscolor_start": "🎨 Guess the color: Red, Blue, Yellow, Green",
        "guesscolor_win": "🎉 You guessed it: {}! You won: {:.2f} UZS. Your balance: {:.2f} UZS",
        "guesscolor_lose": "😔 You didn't guess it: {}. Your balance: {:.2f} UZS",
        "enter_promo": "🎁 Enter promo code:",
        "promo_success": "🎉 Promo code activated! You received: {:.2f} UZS. Your balance: {:.2f} UZS",
        "promo_invalid": "❌ Invalid promo code or already used!",
        "daily_bonus": "🎁 You received a daily bonus: {:.2f} UZS! Your balance: {:.2f} UZS",
        "daily_already_claimed": "❌ You already claimed the daily bonus today!",
        "deposit_method": "💸 Choose deposit method:",
        "deposit_amount": "💸 Enter deposit amount (minimum 1000 UZS):",
        "deposit_details": "💸 Enter deposit details (e.g., card or wallet number):",
        "deposit_success": "✅ Deposit request for {} UZS sent to admin! Your balance: {:.2f} UZS",
        "withdraw_method": "💸 Choose withdrawal method:",
        "withdraw_amount": "💸 Enter withdrawal amount (minimum 1000 UZS):",
        "withdraw_details": "💸 Enter withdrawal details (e.g., card or wallet number):",
        "withdraw_success": "✅ Withdrawal request for {} UZS sent to admin! Your balance: {:.2f} UZS",
        "withdraw_bonus_restriction": "❌ To withdraw bonus balance, make a deposit and wager with a minimum odds of 1.1!",
        "withdraw_no_bets": "❌ Place a bet with your balance with minimum odds of 1.1!",
        "admin_deposit_request": "💸 New deposit request!\nID: {}\nName: {}\nAmount: {} UZS\nMethod: {}\nDetails: {}\n\nApprove: /approve_deposit_{}_{}\nDecline: /decline_deposit_{}_{}",
        "admin_withdraw_request": "💸 New withdrawal request!\nID: {}\nName: {}\nAmount: {} UZS\nMethod: {}\nDetails: {}\n\nApprove: /approve_withdraw_{}_{}\nDecline: /decline_withdraw_{}_{}",
        "admin_deposit_approve": "✅ Deposit of {} UZS for {} approved! New balance: {:.2f} UZS",
        "admin_deposit_decline": "❌ Deposit of {} UZS for {} declined!",
        "admin_withdraw_approve": "✅ Withdrawal of {} UZS for {} approved! New balance: {:.2f} UZS",
        "admin_withdraw_decline": "❌ Withdrawal of {} UZS for {} declined!",
        "profile": "👤 Profile:\nID: {}\nDeposits: {}\nTotal Deposits: {:.2f} UZS\nWithdrawals: {}\nTotal Withdrawals: {:.2f} UZS\nWinnings: {:.2f} UZS\nBalance: {:.2f} UZS",
        "tasks_menu": "📋 Available tasks:\n1. Subscribe to Telegram channel: 700 UZS\n2. Subscribe to Instagram: 1000 UZS\n3. Repost post/video: 3000 UZS\n4. Subscribe to WINBETPROMO channel: 500 UZS\nChoose a task:",
        "task_telegram_sub": "📩 Subscribe to the channel {} and click 'Check Subscription'.",
        "task_instagram_sub": "📸 Follow Instagram {} and send your username for verification.",
        "task_repost": "📢 Repost {} and send the link to the story.",
        "task_check_subscription": "🔍 Check Subscription",
        "task_submit_nickname": "📩 Send your Instagram username",
        "task_submit_repost": "📩 Send the repost link",
        "task_success": "✅ Task completed! You received {} UZS. Your balance: {:.2f} UZS",
        "task_already_completed": "❌ You already completed this task!",
        "task_invalid_submission": "❌ Invalid data! Send a valid username or link.",
        "task_instagram_low_followers": "❌ Your Instagram account has fewer than 20 followers!",
        "task_not_subscribed": "❌ You are not subscribed to the channel! Subscribe and try again.",
        "admin_task_request": "📋 New task request!\nUser: {}\nName: {}\nTask type: {}\nSubmission: {}\nReward: {} UZS\nTask ID: {}\nUser ID: {}",
        "task_submit": "📋 Submit the task details (e.g., your Instagram username):",
        "task_already_submitted": "❌ You have already submitted this task for review!",
        "tasks_none": "❌ No tasks available at the moment!",
        "error": "❌ An error occurred! Please try again later.",
        "admin_menu": "👨‍💻 Admin Panel\nChoose action:",
        "admin_stats": "📊 Bot statistics:\nUsers: {}\nActive: {}\nSystem balance: {:.2f} UZS",
        "admin_user_info": "👤 User info:\nID: {}\nName: {}\nBalance: {:.2f} UZS\nDeposits: {}\nWithdrawals: {}\nReferrals: {}",
        "admin_user_not_found": "❌ User not found!",
        "admin_balance_changed": "✅ User {} balance changed by {:.2f} UZS. New balance: {:.2f} UZS",
        "admin_promocode_created": "🎟 Promo code created: {}\nAmount: {:.2f} UZS\nActivations: {}",
        "admin_promocode_list": "📋 Active promo codes list:\n{}",
        "admin_broadcast_started": "📢 Broadcast started! Reach: {} users",
        "admin_broadcast_completed": "✅ Broadcast completed!\nSent: {}\nFailed: {}",
        "admin_help": (
            "📚 Admin commands help:\n"
            "/add_balance [id] [sum] - Add balance\n"
            "/withdraw_balance [id] [sum] - Withdraw funds\n"
            "/create_promocode [sum] [uses] - Create promo code\n"
            "/user_info [id] - Get user info\n"
            "/broadcast - Make broadcast\n"
            "/stats - Bot statistics"
        ),
        "broadcast_prompt": "📢 Enter the text for broadcasting to all users:",
        "deposit_prompt": "💳 Enter user ID and deposit amount (e.g., 123456789 1000):",
        "withdraw_prompt": "💸 Enter user ID and withdrawal amount (e.g., 123456789 1000):",
        "promocode_prompt": "🎟 Enter amount and number of activations for the promo code (e.g., 5000 10):",
        "not_admin": "❌ You do not have admin privileges!"
    }
}
# Клавиатуры
def get_language_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Русский 🇷🇺"), KeyboardButton(text="English 🇬🇧")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def get_phone_keyboard(language: str) -> ReplyKeyboardMarkup:
    translations = TRANSLATIONS.get(language, TRANSLATIONS["ru"])
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=translations["enter_phone"], request_contact=True)]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

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

def get_tasks_menu(language: str) -> InlineKeyboardMarkup:
    translations = TRANSLATIONS.get(language, TRANSLATIONS["ru"])
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Подписка на Telegram (700 сум)", callback_data="task_telegram_sub")],
        [InlineKeyboardButton(text="Подписка на Instagram (1000 сум)", callback_data="task_instagram_sub")],
        [InlineKeyboardButton(text="Репост (3000 сум)", callback_data="task_repost")],
        [InlineKeyboardButton(text="Подписка на WINBETPROMO (500 сум)", callback_data="task_winbetpromo_sub")]
    ])

def get_task_check_keyboard(task_id: int, language: str) -> InlineKeyboardMarkup:
    translations = TRANSLATIONS.get(language, TRANSLATIONS["ru"])
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=translations["task_check_subscription"], callback_data=f"check_task_{task_id}")]
    ])

def get_task_submit_keyboard(task_id: int, language: str, submit_type: str) -> InlineKeyboardMarkup:
    translations = TRANSLATIONS.get(language, TRANSLATIONS["ru"])
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=translations[f"task_submit_{submit_type}"], callback_data=f"submit_task_{task_id}")]
    ])

def get_dice_keyboard(language: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="1"), KeyboardButton(text="2"), KeyboardButton(text="3")],
            [KeyboardButton(text="4"), KeyboardButton(text="5"), KeyboardButton(text="6")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def get_slots_keyboard(language: str) -> InlineKeyboardMarkup:
    translations = TRANSLATIONS.get(language, TRANSLATIONS["ru"])
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎰 Крутить", callback_data="spin")]
    ])

def get_blackjack_hit_keyboard(language: str) -> ReplyKeyboardMarkup:
    translations = TRANSLATIONS.get(language, TRANSLATIONS["ru"])
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Да" if language == "ru" else "Yes"),
             KeyboardButton(text="Нет" if language == "ru" else "No")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def get_coinflip_keyboard(language: str) -> ReplyKeyboardMarkup:
    translations = TRANSLATIONS.get(language, TRANSLATIONS["ru"])
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Орёл" if language == "ru" else "Heads"),
             KeyboardButton(text="Решка" if language == "ru" else "Tails")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def get_mines_keyboard(grid: list, multiplier: float, game_over: bool = False, language: str = "ru") -> InlineKeyboardMarkup:
    translations = TRANSLATIONS.get(language, TRANSLATIONS["ru"])
    buttons = []
    for i in range(3):
        row = []
        for j in range(3):
            idx = i * 3 + j
            text = "💣" if game_over and grid[idx] == 1 else "✅" if grid[idx] == 2 else "⬜"
            row.append(InlineKeyboardButton(text=text, callback_data=f"mines_{idx}" if not game_over and grid[idx] == 0 else "none"))
        buttons.append(row)
    if not game_over:
        buttons.append([InlineKeyboardButton(text=f"Забрать ({multiplier:.2f}x)", callback_data="mines_cashout")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_roulette_keyboard(language: str) -> ReplyKeyboardMarkup:
    translations = TRANSLATIONS.get(language, TRANSLATIONS["ru"])
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Красное" if language == "ru" else "Red"),
             KeyboardButton(text="Чёрное" if language == "ru" else "Black")],
            [KeyboardButton(text="Зелёное" if language == "ru" else "Green")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def get_overunder_keyboard(language: str) -> ReplyKeyboardMarkup:
    translations = TRANSLATIONS.get(language, TRANSLATIONS["ru"])
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Больше" if language == "ru" else "Over"),
             KeyboardButton(text="Меньше" if language == "ru" else "Under")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def get_guesscolor_keyboard(language: str) -> ReplyKeyboardMarkup:
    translations = TRANSLATIONS.get(language, TRANSLATIONS["ru"])
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Красный" if language == "ru" else "Red"),
             KeyboardButton(text="Синий" if language == "ru" else "Blue")],
            [KeyboardButton(text="Жёлтый" if language == "ru" else "Yellow"),
             KeyboardButton(text="Зелёный" if language == "ru" else "Green")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def get_balance_menu(language: str) -> ReplyKeyboardMarkup:
    translations = TRANSLATIONS.get(language, TRANSLATIONS["ru"])
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💸 Пополнить 📩"), KeyboardButton(text="💸 Вывести 💳")],
            [KeyboardButton(text="🔙 Назад")]
        ],
        resize_keyboard=True
    )

def get_deposit_method_keyboard(language: str) -> ReplyKeyboardMarkup:
    translations = TRANSLATIONS.get(language, TRANSLATIONS["ru"])
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Банковская карта 💳" if language == "ru" else "Bank Card 💳"),
             KeyboardButton(text="Электронный кошелёк 💸" if language == "ru" else "E-Wallet 💸")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def get_withdraw_method_keyboard(language: str) -> ReplyKeyboardMarkup:
    translations = TRANSLATIONS.get(language, TRANSLATIONS["ru"])
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Банковская карта 💳" if language == "ru" else "Bank Card 💳"),
             KeyboardButton(text="Электронный кошелёк 💸" if language == "ru" else "E-Wallet 💸")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

# Состояния FSM
class RegisterState(StatesGroup):
    language = State()
    phone = State()

class GameState(StatesGroup):
    bet = State()
    dice_choice = State()
    slots_spin = State()
    blackjack_hit = State()
    coinflip_choice = State()
    mines_cell = State()
    roulette_choice = State()
    overunder_choice = State()
    guesscolor_choice = State()

class TransactionState(StatesGroup):
    deposit_method = State()
    deposit_amount = State()
    deposit_details = State()
    withdraw_method = State()
    withdraw_amount = State()
    withdraw_details = State()
    promo_code = State()

class TaskState(StatesGroup):
    select_task = State()
    submit_task = State()

# Проверка подписки на канал
async def check_channel_subscription(user_id: int, channel_username: str) -> bool:
    try:
        channel = await bot.get_chat(channel_username)
        member = await bot.get_chat_member(channel.id, user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception as e:
        logger.error(f"Ошибка проверки подписки: {str(e)}")
        return False

# Проверка шанса выигрыша
def get_win_chance(user: User, admin_id: int) -> float:
    if user.telegram_id == admin_id or user.always_win:
        return 1.0
    if user.deposit_count == 0:
        return 0.1
    return 0.3

# Обработчик команды /start
@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    logger.debug(f"Получена команда /start от {message.from_user.id}")
    session = Session()
    try:
        user = session.query(User).filter_by(telegram_id=message.from_user.id).first()
        referral_id = None
        if message.text.startswith("/start ") and len(message.text.split()) > 1:
            try:
                referral_id = int(message.text.split()[1])
            except ValueError:
                pass
        if user:
            translations = TRANSLATIONS.get(user.language, TRANSLATIONS["ru"])
            await bot.send_message(
                chat_id=message.chat.id,
                text=translations["welcome_back"].format(user.username or "User", user.balance),
                parse_mode="HTML",
                reply_markup=get_main_menu(user.language)
            )
            await state.clear()
        else:
            await state.update_data(referral_id=referral_id)
            await bot.send_message(
                chat_id=message.chat.id,
                text=TRANSLATIONS["ru"]["welcome"].format(message.from_user.username or "User", CHANNEL_LINK),
                parse_mode="HTML",
                reply_markup=get_language_keyboard()
            )
            await state.set_state(RegisterState.language)
    except Exception as e:
        session.rollback()
        logger.error(f"Ошибка в cmd_start: {str(e)}", exc_info=True)
        await bot.send_message(
            chat_id=message.chat.id,
            text=TRANSLATIONS["ru"]["error"],
            parse_mode="HTML"
        )
        await state.clear()
    finally:
        session.close()
        logger.debug("Session closed")

# Обработчик выбора языка
@dp.message(RegisterState.language)
async def process_language(message: Message, state: FSMContext):
    logger.debug(f"Получен выбор языка от {message.from_user.id}: {message.text}")
    session = Session()
    try:
        language = "ru" if message.text == "Русский 🇷🇺" else "en" if message.text == "English 🇬🇧" else None
        if not language:
            await bot.send_message(
                chat_id=message.chat.id,
                text=TRANSLATIONS["ru"]["welcome"].format(message.from_user.username or "User", CHANNEL_LINK),
                parse_mode="HTML",
                reply_markup=get_language_keyboard()
            )
            return
        await state.update_data(language=language)
        translations = TRANSLATIONS.get(language, TRANSLATIONS["ru"])
        await bot.send_message(
            chat_id=message.chat.id,
            text=translations["language_selected"],
            parse_mode="HTML",
            reply_markup=get_phone_keyboard(language)
        )
        await state.set_state(RegisterState.phone)
    except Exception as e:
        session.rollback()
        logger.error(f"Ошибка в process_language: {str(e)}", exc_info=True)
        await bot.send_message(
            chat_id=message.chat.id,
            text=TRANSLATIONS["ru"]["error"],
            parse_mode="HTML"
        )
    finally:
        session.close()
        logger.debug("Session closed")

# Обработчик номера телефона
@dp.message(lambda message: message.contact is not None, RegisterState.phone)
async def process_phone(message: types.Message, state: FSMContext, bot: Bot):
    logger.debug(f"Получен номер телефона от {message.from_user.id}")
    session = Session()
    try:
        telegram_id = message.from_user.id
        username = message.from_user.username or "User"
        phone = message.contact.phone_number
        data = await state.get_data()
        language = data.get("language", "ru")
        referral_id = data.get("referral_id")
        translations = TRANSLATIONS.get(language, TRANSLATIONS["ru"])
        
        logger.debug(f"Данные пользователя: telegram_id={telegram_id}, username={username}, phone={phone}, language={language}, referral_id={referral_id}")
        
        # Проверяем, существует ли пользователь
        user = session.query(User).filter_by(telegram_id=telegram_id).first()
        
        if user:
            # Пользователь существует, обновляем данные
            logger.debug(f"Пользователь {telegram_id} уже существует, обновляем данные")
            user.phone = phone
            user.language = language
            user.username = username
            session.commit()
            
            # Отправляем сообщение о возвращении
            await message.answer(
                translations["welcome_back"].format(username, user.balance),
                parse_mode="HTML",
                reply_markup=get_main_menu(language)
            )
        else:
            # Создаём нового пользователя
            logger.debug(f"Создаём нового пользователя: {telegram_id}")
            new_user = User(
                telegram_id=telegram_id,
                username=username,
                phone=phone,
                balance=5000.0,  # Приветственный бонус
                language=language,
                referral_id=referral_id,
                referral_earnings=0.0,
                total_winnings=0.0,
                game_count=0,
                is_banned=False,
                deposit_count=0,
                total_deposits=0.0,
                withdrawal_count=0,
                total_withdrawals=0.0,
                last_daily=None,
                always_win=False,
                total_bets=0.0
            )
            session.add(new_user)
            session.commit()
            
            # Обработка реферального бонуса
            if referral_id:
                referrer = session.query(User).filter_by(telegram_id=referral_id).first()
                if referrer:
                    bonus = 1000.0
                    referrer.balance += bonus
                    referrer.referral_earnings += bonus
                    new_user.balance += bonus
                    session.commit()
                    await bot.send_message(
                        chat_id=referrer.telegram_id,
                        text=translations["referral_bonus"].format(bonus, new_user.username),
                        parse_mode="HTML"
                    )
                    await message.answer(
                        translations["referral_bonus"].format(bonus, referrer.username),
                        parse_mode="HTML"
                    )
            
            # Отправляем сообщение о регистрации
            bot_username = (await bot.get_me()).username
            await message.answer(
                translations["registration_success"].format(telegram_id, bot_username, telegram_id),
                parse_mode="HTML",
                reply_markup=get_main_menu(language)
            )
            # Отправляем сообщение о приветственном бонусе
            await message.answer(
                translations["welcome_bonus"].format(5000.0) + "\n🎁 Бонус 100% на первое пополнение!",
                parse_mode="HTML"
            )
            # Отправляем уведомление администратору
            try:
                await bot.send_message(
                    chat_id=ADMIN_CHAT_ID,
                    text=translations["new_user_notification"].format(
                        telegram_id,
                        new_user.id,
                        username,
                        phone,
                        language,
                        "None" if referral_id is None else referral_id
                    ),
                    parse_mode="HTML"
                )
                logger.debug(f"Уведомление о новом пользователе {telegram_id} отправлено администратору")
            except Exception as admin_error:
                logger.error(f"Ошибка при отправке уведомления администратору: {str(admin_error)}")
        
        await state.clear()
    except Exception as e:
        session.rollback()
        logger.error(f"Ошибка в process_phone: {str(e)}", exc_info=True)
        await message.answer(
            TRANSLATIONS.get("error", "❌ Произошла ошибка! Попробуйте позже."),
            parse_mode="HTML",
            reply_markup=get_main_menu(language if 'language' in locals() else "ru")
        )
        await state.clear()
    finally:
        session.close()
        logger.debug("Session closed")

# Класс состояний для админ-панели
class AdminState(StatesGroup):
    broadcast = State()       # Для рассылки сообщений
    deposit = State()         # Для пополнения баланса
    withdraw = State()        # Для вывода средств
    promocode = State()       # Для создания промокодов
    activate_promocode = State()  # Для активации промокодов

@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    logger.debug(f"Получена команда /admin от {message.from_user.id}")
    if message.from_user.id != ADMIN_CHAT_ID:
        await message.answer(TRANSLATIONS["ru"]["not_admin"])
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="💳 Пополнение", callback_data="admin_deposit")],
        [InlineKeyboardButton(text="💸 Снятие", callback_data="admin_withdraw")],
        [InlineKeyboardButton(text="🎟 Промокод", callback_data="admin_promocode")]
    ])
    await message.answer(TRANSLATIONS["ru"]["admin_menu"], reply_markup=keyboard)

# Обработчик админских callback-запросов
@dp.callback_query(lambda c: c.data.startswith("admin_"))
async def admin_callback(query: CallbackQuery, state: FSMContext):
    if query.from_user.id != ADMIN_CHAT_ID:
        await query.answer(TRANSLATIONS["ru"]["not_admin"], show_alert=True)
        return
    action = query.data.split("_")[1]
    translations = TRANSLATIONS["ru"]
    
    if action == "broadcast":
        await query.message.answer(translations["broadcast_prompt"], parse_mode="HTML")
        await state.set_state(AdminState.broadcast)
    elif action == "deposit":
        await query.message.answer(translations["deposit_prompt"], parse_mode="HTML")
        await state.set_state(AdminState.deposit)
    elif action == "withdraw":
        await query.message.answer(translations["withdraw_prompt"], parse_mode="HTML")
        await state.set_state(AdminState.withdraw)
    elif action == "promocode":
        await query.message.answer(translations["promocode_prompt"], parse_mode="HTML")
        await state.set_state(AdminState.promocode)
    await query.answer()

# Обработчик рассылки
@dp.message(AdminState.broadcast)
async def process_broadcast(message: types.Message, state: FSMContext, bot: Bot):
    if message.from_user.id != ADMIN_CHAT_ID:
        await message.answer(TRANSLATIONS["ru"]["not_admin"], parse_mode="HTML")
        return
    session = Session()
    try:
        users = session.query(User).all()
        success_count = 0
        for user in users:
            try:
                await bot.send_message(user.telegram_id, message.text, parse_mode="HTML")
                success_count += 1
                await asyncio.sleep(0.05)  # Задержка для избежания лимитов Telegram
            except Exception as e:
                logger.error(f"Ошибка при отправке пользователю {user.telegram_id}: {str(e)}")
        await message.answer(
            TRANSLATIONS["ru"]["admin_broadcast_completed"].format(success_count, len(users) - success_count),
            parse_mode="HTML"
        )
    except Exception as e:
        session.rollback()
        logger.error(f"Ошибка в process_broadcast: {str(e)}", exc_info=True)
        await message.answer(TRANSLATIONS["ru"]["error"], parse_mode="HTML")
    finally:
        session.close()
        await state.clear()

# Обработчик пополнения баланса
@dp.message(AdminState.deposit)
async def process_deposit(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_CHAT_ID:
        await message.answer(TRANSLATIONS["ru"]["not_admin"], parse_mode="HTML")
        return
    session = Session()
    try:
        parts = message.text.split()
        if len(parts) != 2 or not parts[0].isdigit() or not parts[1].replace(".", "").isdigit():
            await message.answer("❌ Неверный формат. Пример: 123456789 1000", parse_mode="HTML")
            return
        telegram_id, amount = int(parts[0]), float(parts[1])
        user = session.query(User).filter_by(telegram_id=telegram_id).first()
        if not user:
            await message.answer("❌ Пользователь не найден", parse_mode="HTML")
            return
        user.balance += amount
        user.deposit_count += 1
        user.total_deposits += amount
        session.commit()
        await message.answer(
            TRANSLATIONS["ru"]["admin_deposit_approve"].format(amount, user.username or "User", user.balance),
            parse_mode="HTML"
        )
        await bot.send_message(
            chat_id=user.telegram_id,
            text=TRANSLATIONS[user.language]["deposit_success"].format(amount, user.balance),
            parse_mode="HTML",
            reply_markup=get_main_menu(user.language)
        )
    except Exception as e:
        session.rollback()
        logger.error(f"Ошибка в process_deposit: {str(e)}", exc_info=True)
        await message.answer(TRANSLATIONS["ru"]["error"], parse_mode="HTML")
    finally:
        session.close()
        await state.clear()

# Обработчик снятия баланса
@dp.message(AdminState.withdraw)
async def process_withdraw(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_CHAT_ID:
        await message.answer(TRANSLATIONS["ru"]["not_admin"], parse_mode="HTML")
        return
    session = Session()
    try:
        parts = message.text.split()
        if len(parts) != 2 or not parts[0].isdigit() or not parts[1].replace(".", "").isdigit():
            await message.answer("❌ Неверный формат. Пример: 123456789 1000", parse_mode="HTML")
            return
        telegram_id, amount = int(parts[0]), float(parts[1])
        user = session.query(User).filter_by(telegram_id=telegram_id).first()
        if not user:
            await message.answer("❌ Пользователь не найден", parse_mode="HTML")
            return
        if user.balance < amount:
            await message.answer(
                f"❌ Недостаточно средств на балансе пользователя {user.username or 'User'}!",
                parse_mode="HTML"
            )
            return
        user.balance -= amount
        user.withdrawal_count += 1
        user.total_withdrawals += amount
        session.commit()
        await message.answer(
            TRANSLATIONS["ru"]["admin_withdraw_approve"].format(amount, user.username or "User", user.balance),
            parse_mode="HTML"
        )
        await bot.send_message(
            chat_id=user.telegram_id,
            text=TRANSLATIONS[user.language]["withdraw_success"].format(amount, user.balance),
            parse_mode="HTML",
            reply_markup=get_main_menu(user.language)
        )
    except Exception as e:
        session.rollback()
        logger.error(f"Ошибка в process_withdraw: {str(e)}", exc_info=True)
        await message.answer(TRANSLATIONS["ru"]["error"], parse_mode="HTML")
    finally:
        session.close()
        await state.clear()

# Обработчик создания промокода
@dp.message(AdminState.promocode)
async def process_promocode(message: types.Message, state: FSMContext):
    logger.debug(f"Processing promocode input: {message.text} from user {message.from_user.id}")
    session = Session()
    try:
        if message.from_user.id != ADMIN_CHAT_ID:
            await message.answer(TRANSLATIONS["ru"]["not_admin"])
            return
        user = session.query(User).filter_by(telegram_id=message.from_user.id).first()
        translations = TRANSLATIONS.get(user.language if user else "ru", TRANSLATIONS["ru"])
        try:
            amount, uses_remaining = map(float, message.text.split())
            if amount < 0 or uses_remaining < 0:
                logger.warning(f"Invalid input: amount={amount}, uses_remaining={uses_remaining}")
                await message.answer("❌ Сумма и количество использований должны быть положительными!")
                return
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
            promocode = PromoCode(code=code, amount=amount, uses_remaining=int(uses_remaining), created_by=message.from_user.id)
            session.add(promocode)
            session.commit()
            logger.info(f"Promo code created: code={code}, amount={amount}, uses_remaining={uses_remaining}")
            await message.answer(translations["admin_promocode_created"].format(code, amount, int(uses_remaining)))
            await state.clear()
        except ValueError:
            logger.warning(f"Invalid format for promocode input: {message.text}")
            await message.answer("❌ Неверный формат! Введите: <сумма> <количество использований>, например, 5000 10")
    except Exception as e:
        logger.error(f"Error creating promocode: {str(e)}")
        session.rollback()
        await message.answer(f"❌ Ошибка: {str(e)}")
    finally:
        session.close()

# Обработчик активации промокода
@dp.message(Command(commands=["promocode"]))
async def cmd_promocode(message: types.Message, state: FSMContext):
    translations = TRANSLATIONS["ru"]
    await message.answer(translations["enter_promo"], parse_mode="HTML")
    await state.set_state(TransactionState.promo_code)

@dp.message(TransactionState.promo_code)
async def process_promo_code(message: Message, state: FSMContext):
    logger.debug(f"Получен промокод от {message.from_user.id}: {message.text}")
    session = Session()
    try:
        user = session.query(User).filter_by(telegram_id=message.from_user.id).first()
        if not user or user.is_banned:
            await bot.send_message(
                chat_id=message.chat.id,
                text=TRANSLATIONS["ru"]["error"] if not user else "❌ Вы заблокированы! 🚫",
                parse_mode="HTML",
                reply_markup=get_main_menu("ru")
            )
            await state.clear()
            return
        translations = TRANSLATIONS.get(user.language, TRANSLATIONS["ru"])
        promo_code = message.text.strip()
        promo = session.query(PromoCode).filter_by(code=promo_code).first()
        if not promo or promo.uses_remaining <= 0:
            await bot.send_message(
                chat_id=message.chat.id,
                text=translations["promo_invalid"],
                parse_mode="HTML",
                reply_markup=get_main_menu(user.language)
            )
            await state.clear()
            return
        user_promo = session.query(UserPromoCode).filter_by(user_id=user.id, promo_code_id=promo.id).first()
        if user_promo:
            await bot.send_message(
                chat_id=message.chat.id,
                text=translations["promo_invalid"],
                parse_mode="HTML",
                reply_markup=get_main_menu(user.language)
            )
            await state.clear()
            return
        user.balance += promo.amount
        promo.uses_remaining -= 1
        user_promo = UserPromoCode(user_id=user.id, promo_code_id=promo.id)
        session.add(user_promo)
        session.commit()
        await bot.send_message(
            chat_id=message.chat.id,
            text=translations["promo_success"].format(promo.amount, user.balance),
            parse_mode="HTML",
            reply_markup=get_main_menu(user.language)
        )
        await state.clear()
    except Exception as e:
        session.rollback()
        logger.error(f"Ошибка в process_promo_code: {str(e)}", exc_info=True)
        await bot.send_message(
            chat_id=message.chat.id,
            text=translations["error"],
            parse_mode="HTML",
            reply_markup=get_main_menu(user.language)
        )
        await state.clear()
    finally:
        session.close()
        logger.debug("Session closed")

# Обработчик действий главного меню
@dp.message(lambda message: message.text in [
    "🎰 Слоты 🎰", "🎲 Кости 🎲", "🃏 Блэкджек 🎴", "🪙 Орёл и Решка 🪙",
    "💣 Мины 💣", "🎡 Рулетка 🎡", "🎲 Больше/Меньше 7 🎲", "🎨 Угадай Цвет 🎨",
    "👤 Профиль 📊", "💰 Баланс 💳", "💸 Пополнить 📩", "💸 Вывести 💳",
    "🎁 Ввести промокод", "🎁 Ежедневный бонус", "📋 Задания"
])
async def handle_menu_action(message: Message, state: FSMContext):
    message_key = f"{message.from_user.id}_{message.message_id}"
    logger.debug(f"Получено действие меню от {message.from_user.id}: {message.text}")
    if message_key in processed_messages:
        logger.debug(f"Игнорируется дубликат действия меню от {message.from_user.id}, message_id: {message.message_id}")
        return
    processed_messages.add(message_key)
    session = Session()
    try:
        user = session.query(User).filter_by(telegram_id=message.from_user.id).first()
        if not user or user.is_banned:
            await bot.send_message(
                chat_id=message.chat.id,
                text=(TRANSLATIONS["ru"]["error"] if not user else "❌ Вы заблокированы! 🚫"),
                parse_mode="HTML",
                reply_markup=get_main_menu("ru")
            )
            await state.clear()
            return
        translations = TRANSLATIONS.get(user.language, TRANSLATIONS["ru"])
        action = message.text
        if action == "📋 Задания":
            await bot.send_message(
                chat_id=message.chat.id,
                text=translations["tasks_menu"],
                parse_mode="HTML",
                reply_markup=get_tasks_menu(user.language)
            )
            await state.set_state(TaskState.select_task)
        elif action == "🎰 Слоты 🎰":
            await bot.send_message(chat_id=message.chat.id, text=translations["bet_prompt"], parse_mode="HTML")
            await state.set_state(GameState.bet)
            await state.update_data(game="slots")
        elif action == "🎲 Кости 🎲":
            await bot.send_message(chat_id=message.chat.id, text=translations["bet_prompt"], parse_mode="HTML")
            await state.set_state(GameState.bet)
            await state.update_data(game="dice")
        elif action == "🃏 Блэкджек 🎴":
            await bot.send_message(chat_id=message.chat.id, text=translations["bet_prompt"], parse_mode="HTML")
            await state.set_state(GameState.bet)
            await state.update_data(game="blackjack")
        elif action == "🪙 Орёл и Решка 🪙":
            await bot.send_message(chat_id=message.chat.id, text=translations["bet_prompt"], parse_mode="HTML")
            await state.set_state(GameState.bet)
            await state.update_data(game="coinflip")
        elif action == "💣 Мины 💣":
            await bot.send_message(chat_id=message.chat.id, text=translations["bet_prompt"], parse_mode="HTML")
            await state.set_state(GameState.bet)
            await state.update_data(game="mines")
        elif action == "🎡 Рулетка 🎡":
            await bot.send_message(chat_id=message.chat.id, text=translations["bet_prompt"], parse_mode="HTML")
            await state.set_state(GameState.bet)
            await state.update_data(game="roulette")
        elif action == "🎲 Больше/Меньше 7 🎲":
            await bot.send_message(chat_id=message.chat.id, text=translations["bet_prompt"], parse_mode="HTML")
            await state.set_state(GameState.bet)
            await state.update_data(game="overunder")
        elif action == "🎨 Угадай Цвет 🎨":
            await bot.send_message(chat_id=message.chat.id, text=translations["bet_prompt"], parse_mode="HTML")
            await state.set_state(GameState.bet)
            await state.update_data(game="guesscolor")
        elif action == "👤 Профиль 📊":
            await bot.send_message(chat_id=message.chat.id, text=translations["profile"].format(
                user.telegram_id,
                user.deposit_count,
                user.total_deposits,
                user.withdrawal_count,
                user.total_withdrawals,
                user.total_winnings,
                user.balance
            ), parse_mode="HTML")
        elif action == "💰 Баланс 💳":
            await bot.send_message(
                chat_id=message.chat.id,
                text=translations["balance"].format(user.balance),
                parse_mode="HTML",
                reply_markup=get_balance_menu(user.language)
            )
        elif action == "💸 Пополнить 📩":
            await bot.send_message(
                chat_id=message.chat.id,
                text="Для пополнения обратитесь к админу @win_betuz",
                parse_mode="HTML",
                reply_markup=get_main_menu(user.language)
            )
            await state.clear()
        elif action == "💸 Вывести 💳":
            if user.deposit_count == 0:
                await bot.send_message(
                    chat_id=message.chat.id,
                    text=translations["withdraw_bonus_restriction"],
                    parse_mode="HTML",
                    reply_markup=get_main_menu(user.language)
                )
                await state.clear()
                return
            if user.deposit_count > 0 and user.total_bets < user.total_deposits * 1.1:
                await bot.send_message(
                    chat_id=message.chat.id,
                    text=translations["withdraw_no_bets"],
                    parse_mode="HTML",
                    reply_markup=get_main_menu(user.language)
                )
                await state.clear()
                return
            await bot.send_message(
                chat_id=message.chat.id,
                text=translations["withdraw_method"],
                parse_mode="HTML",
                reply_markup=get_withdraw_method_keyboard(user.language)
            )
            await state.set_state(TransactionState.withdraw_method)
        elif action == "🎁 Ввести промокод":
            await bot.send_message(
                chat_id=message.chat.id,
                text=translations["enter_promo"],
                parse_mode="HTML"
            )
            await state.set_state(TransactionState.promo_code)
        elif action == "🎁 Ежедневный бонус":
            now = datetime.utcnow()
            if user.last_daily and (now - user.last_daily).days < 1:
                await bot.send_message(
                    chat_id=message.chat.id,
                    text=translations["daily_already_claimed"],
                    parse_mode="HTML",
                    reply_markup=get_main_menu(user.language)
                )
            else:
                bonus = 1000.0
                user.balance += bonus
                user.last_daily = now
                session.commit()
                await bot.send_message(
                    chat_id=message.chat.id,
                    text=translations["daily_bonus"].format(bonus, user.balance),
                    parse_mode="HTML",
                    reply_markup=get_main_menu(user.language)
                )
            await state.clear()
    except Exception as e:
        session.rollback()
        logger.error(f"Ошибка в handle_menu_action: {str(e)}", exc_info=True)
        await bot.send_message(
            chat_id=message.chat.id,
            text=translations["error"],
            parse_mode="HTML",
            reply_markup=get_main_menu(user.language)
        )
        await state.clear()
    finally:
        session.close()
        logger.debug("Session closed")

# Обработчик команды /setwin
@dp.message(RegexpCommandsFilter(regexp_commands=[r"/setwin_(\d+)"]))
async def set_win(message: Message, regexp_command: re.Match):
    logger.debug(f"Получена команда /setwin от {message.from_user.id}: {message.text}")
    if message.from_user.id != ADMIN_CHAT_ID:
        await bot.send_message(
            chat_id=message.chat.id,
            text=TRANSLATIONS["ru"]["not_admin"],
            parse_mode="HTML"
        )
        return
    session = Session()
    try:
        user_id = int(regexp_command.group(1))
        user = session.query(User).filter_by(telegram_id=user_id).first()
        if not user:
            await bot.send_message(
                chat_id=message.chat.id,
                text=TRANSLATIONS["ru"]["admin_user_not_found"],
                parse_mode="HTML"
            )
            return
        user.always_win = True
        session.commit()
        await bot.send_message(
            chat_id=message.chat.id,
            text=f"✅ Пользователь {user.username or 'User'} ({user.telegram_id}) теперь всегда выигрывает!",
            parse_mode="HTML"
        )
    except Exception as e:
        session.rollback()
        logger.error(f"Ошибка в set_win: {str(e)}", exc_info=True)
        await bot.send_message(
            chat_id=message.chat.id,
            text=TRANSLATIONS["ru"]["error"],
            parse_mode="HTML"
        )
    finally:
        session.close()
        logger.debug("Session closed")

# Обработчик команды /setlose
@dp.message(RegexpCommandsFilter(regexp_commands=[r"/setlose_(\d+)"]))
async def set_lose(message: Message, regexp_command: re.Match):
    logger.debug(f"Получена команда /setlose от {message.from_user.id}: {message.text}")
    if message.from_user.id != ADMIN_CHAT_ID:
        await bot.send_message(
            chat_id=message.chat.id,
            text=TRANSLATIONS["ru"]["not_admin"],
            parse_mode="HTML"
        )
        return
    session = Session()
    try:
        user_id = int(regexp_command.group(1))
        user = session.query(User).filter_by(telegram_id=user_id).first()
        if not user:
            await bot.send_message(
                chat_id=message.chat.id,
                text=TRANSLATIONS["ru"]["admin_user_not_found"],
                parse_mode="HTML"
            )
            return
        user.always_win = False
        session.commit()
        await bot.send_message(
            chat_id=message.chat.id,
            text=f"✅ Пользователь {user.username or 'User'} ({user.telegram_id}) теперь не всегда выигрывает!",
            parse_mode="HTML"
        )
    except Exception as e:
        session.rollback()
        logger.error(f"Ошибка в set_lose: {str(e)}", exc_info=True)
        await bot.send_message(
            chat_id=message.chat.id,
            text=TRANSLATIONS["ru"]["error"],
            parse_mode="HTML"
        )
    finally:
        session.close()
        logger.debug("Session closed")
# Обработчик ввода ставки
@dp.message(GameState.bet)
async def process_bet(message: Message, state: FSMContext):
    logger.debug(f"Получена ставка от {message.from_user.id}: {message.text}")
    session = Session()
    try:
        user = session.query(User).filter_by(telegram_id=message.from_user.id).first()
        if not user or user.is_banned:
            await bot.send_message(
                chat_id=message.chat.id,
                text=TRANSLATIONS["ru"]["error"] if not user else "❌ Вы заблокированы! 🚫",
                parse_mode="HTML",
                reply_markup=get_main_menu("ru")
            )
            await state.clear()
            return
        translations = TRANSLATIONS.get(user.language, TRANSLATIONS["ru"])
        try:
            bet = float(message.text.strip())
            if bet < 1000:
                await bot.send_message(
                    chat_id=message.chat.id,
                    text=translations["invalid_bet"].format(user.balance),
                    parse_mode="HTML"
                )
                return
            if bet > user.balance:
                await bot.send_message(
                    chat_id=message.chat.id,
                    text=translations["insufficient_balance"].format(user.balance),
                    parse_mode="HTML"
                )
                return
            user.balance -= bet
            user.total_bets += bet
            user.game_count += 1
            session.commit()
            await state.update_data(bet=bet)
            data = await state.get_data()
            game = data.get("game")
            if game == "dice":
                await bot.send_message(
                    chat_id=message.chat.id,
                    text=translations["dice_start"],
                    parse_mode="HTML",
                    reply_markup=get_dice_keyboard(user.language)
                )
                await state.set_state(GameState.dice_choice)
            elif game == "slots":
                await bot.send_message(
                    chat_id=message.chat.id,
                    text=translations["slots_start"],
                    parse_mode="HTML",
                    reply_markup=get_slots_keyboard(user.language)
                )
                await state.set_state(GameState.slots_spin)
            elif game == "blackjack":
                cards = [random.randint(1, 11), random.randint(1, 11)]
                total = sum(cards)
                await state.update_data(cards=cards, total=total)
                await bot.send_message(
                    chat_id=message.chat.id,
                    text=translations["blackjack_start"].format(", ".join(map(str, cards)), total),
                    parse_mode="HTML",
                    reply_markup=get_blackjack_hit_keyboard(user.language)
                )
                await state.set_state(GameState.blackjack_hit)
            elif game == "coinflip":
                await bot.send_message(
                    chat_id=message.chat.id,
                    text=translations["coinflip_start"],
                    parse_mode="HTML",
                    reply_markup=get_coinflip_keyboard(user.language)
                )
                await state.set_state(GameState.coinflip_choice)
            elif game == "mines":
                grid = [0] * 9
                mines = random.sample(range(9), 3)
                await state.update_data(grid=grid, mines=mines, multiplier=1.0, opened_cells=0)
                await bot.send_message(
                    chat_id=message.chat.id,
                    text=translations["mines_start"],
                    parse_mode="HTML",
                    reply_markup=get_mines_keyboard(grid, 1.0, False, user.language)
                )
                await state.set_state(GameState.mines_cell)
            elif game == "roulette":
                await bot.send_message(
                    chat_id=message.chat.id,
                    text=translations["roulette_start"],
                    parse_mode="HTML",
                    reply_markup=get_roulette_keyboard(user.language)
                )
                await state.set_state(GameState.roulette_choice)
            elif game == "overunder":
                await bot.send_message(
                    chat_id=message.chat.id,
                    text=translations["overunder_start"],
                    parse_mode="HTML",
                    reply_markup=get_overunder_keyboard(user.language)
                )
                await state.set_state(GameState.overunder_choice)
            elif game == "guesscolor":
                await bot.send_message(
                    chat_id=message.chat.id,
                    text=translations["guesscolor_start"],
                    parse_mode="HTML",
                    reply_markup=get_guesscolor_keyboard(user.language)
                )
                await state.set_state(GameState.guesscolor_choice)
        except ValueError:
            await bot.send_message(
                chat_id=message.chat.id,
                text=translations["bet_prompt"],
                parse_mode="HTML"
            )
    except Exception as e:
        session.rollback()
        logger.error(f"Ошибка в process_bet: {str(e)}", exc_info=True)
        await bot.send_message(
            chat_id=message.chat.id,
            text=translations["error"],
            parse_mode="HTML",
            reply_markup=get_main_menu(user.language)
        )
        await state.clear()
    finally:
        session.close()
        logger.debug("Session closed")

# Обработчик выбора задания
@dp.callback_query(lambda callback: callback.data.startswith("task_") or callback.data.startswith("check_task_") or callback.data.startswith("submit_task_"))
async def process_task_selection(callback: CallbackQuery, state: FSMContext):
    logger.debug(f"Получен выбор задания от {callback.from_user.id}: {callback.data}")
    session = Session()
    try:
        user = session.query(User).filter_by(telegram_id=callback.from_user.id).first()
        if not user or user.is_banned:
            await callback.message.edit_text(
                text=TRANSLATIONS["ru"]["error"] if not user else "❌ Вы заблокированы! 🚫",
                parse_mode="HTML",
                reply_markup=None
            )
            await bot.send_message(
                chat_id=callback.message.chat.id,
                text=TRANSLATIONS["ru"]["welcome_back"].format(user.username or "Player", user.balance),
                parse_mode="HTML",
                reply_markup=get_main_menu("ru")
            )
            await state.clear()
            await callback.answer()
            return
        translations = TRANSLATIONS.get(user.language, TRANSLATIONS["ru"])
        if callback.data.startswith("task_"):
            task_type = callback.data.split("_")[1]
            if task_type == "telegram_sub":
                task = session.query(Task).filter_by(task_type="telegram_sub", active=True).first()
                if not task:
                    task = Task(task_type="telegram_sub", reward=700.0, link="@SomeTelegramChannel", min_followers=0, active=True)
                    session.add(task)
                    session.commit()
                if session.query(UserTask).filter_by(user_id=user.id, task_id=task.id).first():
                    await callback.message.edit_text(
                        text=translations["task_already_completed"],
                        parse_mode="HTML",
                        reply_markup=None
                    )
                    await bot.send_message(
                        chat_id=callback.message.chat.id,
                        text=translations["welcome_back"].format(user.username or "Player", user.balance),
                        parse_mode="HTML",
                        reply_markup=get_main_menu(user.language)
                    )
                    await state.clear()
                    await callback.answer()
                    return
                await state.update_data(task_id=task.id, task_type="telegram_sub")
                await callback.message.edit_text(
                    text=translations["task_telegram_sub"].format(task.link),
                    parse_mode="HTML",
                    reply_markup=get_task_check_keyboard(task.id, user.language)
                )
            elif task_type == "instagram_sub":
                task = session.query(Task).filter_by(task_type="instagram_sub", active=True).first()
                if not task:
                    task = Task(task_type="instagram_sub", reward=1000.0, link="@SomeInstagramAccount", min_followers=20, active=True)
                    session.add(task)
                    session.commit()
                if session.query(UserTask).filter_by(user_id=user.id, task_id=task.id).first():
                    await callback.message.edit_text(
                        text=translations["task_already_completed"],
                        parse_mode="HTML",
                        reply_markup=None
                    )
                    await bot.send_message(
                        chat_id=callback.message.chat.id,
                        text=translations["welcome_back"].format(user.username or "Player", user.balance),
                        parse_mode="HTML",
                        reply_markup=get_main_menu(user.language)
                    )
                    await state.clear()
                    await callback.answer()
                    return
                await state.update_data(task_id=task.id, task_type="instagram_sub")
                await callback.message.edit_text(
                    text=translations["task_instagram_sub"].format(task.link),
                    parse_mode="HTML",
                    reply_markup=get_task_submit_keyboard(task.id, user.language, "nickname")
                )
            elif task_type == "repost":
                task = session.query(Task).filter_by(task_type="repost", active=True).first()
                if not task:
                    task = Task(task_type="repost", reward=3000.0, link="https://t.me/SomePostLink", min_followers=0, active=True)
                    session.add(task)
                    session.commit()
                if session.query(UserTask).filter_by(user_id=user.id, task_id=task.id).first():
                    await callback.message.edit_text(
                        text=translations["task_already_completed"],
                        parse_mode="HTML",
                        reply_markup=None
                    )
                    await bot.send_message(
                        chat_id=callback.message.chat.id,
                        text=translations["welcome_back"].format(user.username or "Player", user.balance),
                        parse_mode="HTML",
                        reply_markup=get_main_menu(user.language)
                    )
                    await state.clear()
                    await callback.answer()
                    return
                await state.update_data(task_id=task.id, task_type="repost")
                await callback.message.edit_text(
                                   text=translations["task_repost"].format(task.link),
                parse_mode="HTML",
                reply_markup=get_task_submit_keyboard(task.id, user.language, "repost")
            )
            elif task_type == "winbetpromo_sub":
                task = session.query(Task).filter_by(task_type="winbetpromo_sub", active=True).first()
                if not task:
                    task = Task(task_type="winbetpromo_sub", reward=500.0, link=CHANNEL_LINK, min_followers=0, active=True)
                    session.add(task)
                    session.commit()
                if session.query(UserTask).filter_by(user_id=user.id, task_id=task.id).first():
                    await callback.message.edit_text(
                        text=translations["task_already_completed"],
                        parse_mode="HTML",
                        reply_markup=None
                    )
                    await bot.send_message(
                        chat_id=callback.message.chat.id,
                        text=translations["welcome_back"].format(user.username or "Player", user.balance),
                        parse_mode="HTML",
                        reply_markup=get_main_menu(user.language)
                    )
                    await state.clear()
                    await callback.answer()
                    return
                await state.update_data(task_id=task.id, task_type="winbetpromo_sub")
                await callback.message.edit_text(
                    text=translations["task_telegram_sub"].format(task.link),
                    parse_mode="HTML",
                    reply_markup=get_task_check_keyboard(task.id, user.language)
                )
        elif callback.data.startswith("check_task_"):
            task_id = int(callback.data.split("_")[2])
            task = session.query(Task).filter_by(id=task_id).first()
            if not task:
                await callback.message.edit_text(
                    text=translations["error"],
                    parse_mode="HTML",
                    reply_markup=None
                )
                await bot.send_message(
                    chat_id=callback.message.chat.id,
                    text=translations["welcome_back"].format(user.username or "Player", user.balance),
                    parse_mode="HTML",
                    reply_markup=get_main_menu(user.language)
                )
                await state.clear()
                await callback.answer()
                return
            is_subscribed = await check_channel_subscription(callback.from_user.id, task.link)
            if not is_subscribed:
                await callback.message.edit_text(
                    text=translations["task_not_subscribed"],
                    parse_mode="HTML",
                    reply_markup=get_task_check_keyboard(task.id, user.language)
                )
                await callback.answer()
                return
            user_task = UserTask(user_id=user.id, task_id=task.id, status="pending")
            session.add(user_task)
            session.commit()
            await callback.message.edit_text(
                text=translations["task_success"].format(task.reward, user.balance + task.reward),
                parse_mode="HTML",
                reply_markup=None
            )
            user.balance += task.reward
            session.commit()
            await bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=translations["admin_task_request"].format(
                    user.telegram_id, user.username or "User", task.task_type, "Subscribed", task.reward, task.id, user.id
                ),
                parse_mode="HTML"
            )
            await bot.send_message(
                chat_id=callback.message.chat.id,
                text=translations["welcome_back"].format(user.username or "Player", user.balance),
                parse_mode="HTML",
                reply_markup=get_main_menu(user.language)
            )
            await state.clear()
        elif callback.data.startswith("submit_task_"):
            task_id = int(callback.data.split("_")[2])
            task = session.query(Task).filter_by(id=task_id).first()
            if not task:
                await callback.message.edit_text(
                    text=translations["error"],
                    parse_mode="HTML",
                    reply_markup=None
                )
                await bot.send_message(
                    chat_id=callback.message.chat.id,
                    text=translations["welcome_back"].format(user.username or "Player", user.balance),
                    parse_mode="HTML",
                    reply_markup=get_main_menu(user.language)
                )
                await state.clear()
                await callback.answer()
                return
            await state.update_data(task_id=task.id, task_type=task.task_type)
            await callback.message.edit_text(
                text=translations["task_submit"],
                parse_mode="HTML",
                reply_markup=None
            )
            await state.set_state(TaskState.submit_task)
        await callback.answer()
    except Exception as e:
        session.rollback()
        logger.error(f"Ошибка в process_task_selection: {str(e)}", exc_info=True)
        await callback.message.edit_text(
            text=translations["error"],
            parse_mode="HTML",
            reply_markup=None
        )
        await bot.send_message(
            chat_id=callback.message.chat.id,
            text=translations["welcome_back"].format(user.username or "Player", user.balance),
            parse_mode="HTML",
            reply_markup=get_main_menu(user.language)
        )
        await state.clear()
        await callback.answer()
    finally:
        session.close()
        logger.debug("Session closed")

# Обработчик отправки данных для задания
@dp.message(TaskState.submit_task)
async def process_task_submission(message: Message, state: FSMContext):
    logger.debug(f"Получены данные задания от {message.from_user.id}: {message.text}")
    session = Session()
    try:
        user = session.query(User).filter_by(telegram_id=message.from_user.id).first()
        if not user or user.is_banned:
            await bot.send_message(
                chat_id=message.chat.id,
                text=TRANSLATIONS["ru"]["error"] if not user else "❌ Вы заблокированы! 🚫",
                parse_mode="HTML",
                reply_markup=get_main_menu("ru")
            )
            await state.clear()
            return
        translations = TRANSLATIONS.get(user.language, TRANSLATIONS["ru"])
        data = await state.get_data()
        task_id = data.get("task_id")
        task_type = data.get("task_type")
        task = session.query(Task).filter_by(id=task_id).first()
        if not task:
            await bot.send_message(
                chat_id=message.chat.id,
                text=translations["error"],
                parse_mode="HTML",
                reply_markup=get_main_menu(user.language)
            )
            await state.clear()
            return
        if session.query(UserTask).filter_by(user_id=user.id, task_id=task.id).first():
            await bot.send_message(
                chat_id=message.chat.id,
                text=translations["task_already_completed"],
                parse_mode="HTML",
                reply_markup=get_main_menu(user.language)
            )
            await state.clear()
            return
        submission = message.text.strip()
        if task_type == "instagram_sub" and task.min_followers > 0:
            # Проверка количества подписчиков (заглушка, так как API Instagram сложен)
            if len(submission) < 3:
                await bot.send_message(
                    chat_id=message.chat.id,
                    text=translations["task_invalid_submission"],
                    parse_mode="HTML",
                    reply_markup=get_task_submit_keyboard(task.id, user.language, "nickname")
                )
                return
        elif task_type == "repost":
            if not submission.startswith("https://"):
                await bot.send_message(
                    chat_id=message.chat.id,
                    text=translations["task_invalid_submission"],
                    parse_mode="HTML",
                    reply_markup=get_task_submit_keyboard(task.id, user.language, "repost")
                )
                return
        user_task = UserTask(user_id=user.id, task_id=task.id, status="pending", submission=submission)
        session.add(user_task)
        session.commit()
        await bot.send_message(
            chat_id=message.chat.id,
            text=translations["task_success"].format(task.reward, user.balance + task.reward),
            parse_mode="HTML",
            reply_markup=get_main_menu(user.language)
        )
        user.balance += task.reward
        session.commit()
        await bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=translations["admin_task_request"].format(
                user.telegram_id, user.username or "User", task.task_type, submission, task.reward, task.id, user.id
            ),
            parse_mode="HTML"
        )
        await state.clear()
    except Exception as e:
        session.rollback()
        logger.error(f"Ошибка в process_task_submission: {str(e)}", exc_info=True)
        await bot.send_message(
            chat_id=message.chat.id,
            text=translations["error"],
            parse_mode="HTML",
            reply_markup=get_main_menu(user.language)
        )
        await state.clear()
    finally:
        session.close()
        logger.debug("Session closed")

# Обработчик выбора числа для игры в кости
@dp.message(GameState.dice_choice)
async def process_dice_choice(message: Message, state: FSMContext):
    logger.debug(f"Получен выбор числа для костей от {message.from_user.id}: {message.text}")
    session = Session()
    try:
        user = session.query(User).filter_by(telegram_id=message.from_user.id).first()
        if not user or user.is_banned:
            await bot.send_message(
                chat_id=message.chat.id,
                text=TRANSLATIONS["ru"]["error"] if not user else "❌ Вы заблокированы! 🚫",
                parse_mode="HTML",
                reply_markup=get_main_menu("ru")
            )
            await state.clear()
            return
        translations = TRANSLATIONS.get(user.language, TRANSLATIONS["ru"])
        try:
            choice = int(message.text)
            if choice < 1 or choice > 6:
                await bot.send_message(
                    chat_id=message.chat.id,
                    text=translations["dice_start"],
                    parse_mode="HTML",
                    reply_markup=get_dice_keyboard(user.language)
                )
                return
        except ValueError:
            await bot.send_message(
                chat_id=message.chat.id,
                text=translations["dice_start"],
                parse_mode="HTML",
                reply_markup=get_dice_keyboard(user.language)
            )
            return
        data = await state.get_data()
        bet = data.get("bet", 0.0)
        roll = random.randint(1, 6)
        win_chance = get_win_chance(user, ADMIN_CHAT_ID)
        if random.random() < win_chance:
            roll = choice
        if roll == choice:
            winnings = bet * 5.0
            user.balance += winnings
            user.total_winnings += winnings
            session.commit()
            await bot.send_message(
                chat_id=message.chat.id,
                text=translations["dice_win"].format(roll, winnings, user.balance),
                parse_mode="HTML",
                reply_markup=get_main_menu(user.language)
            )
        else:
            await bot.send_message(
                chat_id=message.chat.id,
                text=translations["dice_lose"].format(roll, user.balance),
                parse_mode="HTML",
                reply_markup=get_main_menu(user.language)
            )
        await state.clear()
    except Exception as e:
        session.rollback()
        logger.error(f"Ошибка в process_dice_choice: {str(e)}", exc_info=True)
        await bot.send_message(
            chat_id=message.chat.id,
            text=translations["error"],
            parse_mode="HTML",
            reply_markup=get_main_menu(user.language)
        )
        await state.clear()
    finally:
        session.close()
        logger.debug("Session closed")

# Обработчик спина слотов
@dp.callback_query(lambda c: c.data == "spin", GameState.slots_spin)
async def process_slots_spin(callback: CallbackQuery, state: FSMContext):
    logger.debug(f"Получен спин слотов от {callback.from_user.id}")
    session = Session()
    try:
        user = session.query(User).filter_by(telegram_id=callback.from_user.id).first()
        if not user or user.is_banned:
            await callback.message.edit_text(
                text=TRANSLATIONS["ru"]["error"] if not user else "❌ Вы заблокированы! 🚫",
                parse_mode="HTML",
                reply_markup=None
            )
            await bot.send_message(
                chat_id=callback.message.chat.id,
                text=TRANSLATIONS["ru"]["welcome_back"].format(user.username or "Player", user.balance),
                parse_mode="HTML",
                reply_markup=get_main_menu("ru")
            )
            await state.clear()
            await callback.answer()
            return
        translations = TRANSLATIONS.get(user.language, TRANSLATIONS["ru"])
        data = await state.get_data()
        bet = data.get("bet", 0.0)
        symbols = ["🍎", "🍐", "🍒", "🍋", "🍊"]
        result = [random.choice(symbols) for _ in range(3)]
        win_chance = get_win_chance(user, ADMIN_CHAT_ID)
        if random.random() < win_chance:
            result = [symbols[0], symbols[0], symbols[0]]
        if result[0] == result[1] == result[2]:
            winnings = bet * 10.0
            user.balance += winnings
            user.total_winnings += winnings
            session.commit()
            await callback.message.edit_text(
                text=translations["slots_result"].format(" | ".join(result), f"🎉 Вы выиграли: {winnings:.2f} сум!\n", user.balance),
                parse_mode="HTML",
                reply_markup=None
            )
        else:
            await callback.message.edit_text(
                text=translations["slots_result"].format(" | ".join(result), "😔 Попробуйте ещё раз!\n", user.balance),
                parse_mode="HTML",
                reply_markup=None
            )
        await bot.send_message(
            chat_id=callback.message.chat.id,
            text=translations["welcome_back"].format(user.username or "Player", user.balance),
            parse_mode="HTML",
            reply_markup=get_main_menu(user.language)
        )
        await state.clear()
        await callback.answer()
    except Exception as e:
        session.rollback()
        logger.error(f"Ошибка в process_slots_spin: {str(e)}", exc_info=True)
        await callback.message.edit_text(
            text=translations["error"],
            parse_mode="HTML",
            reply_markup=None
        )
        await bot.send_message(
            chat_id=callback.message.chat.id,
            text=translations["welcome_back"].format(user.username or "Player", user.balance),
            parse_mode="HTML",
            reply_markup=get_main_menu(user.language)
        )
        await state.clear()
        await callback.answer()
    finally:
        session.close()
        logger.debug("Session closed")

# Обработчик блэкджека
@dp.message(GameState.blackjack_hit)
async def process_blackjack_hit(message: Message, state: FSMContext):
    logger.debug(f"Получен выбор блэкджека от {message.from_user.id}: {message.text}")
    session = Session()
    try:
        user = session.query(User).filter_by(telegram_id=message.from_user.id).first()
        if not user or user.is_banned:
            await bot.send_message(
                chat_id=message.chat.id,
                text=TRANSLATIONS["ru"]["error"] if not user else "❌ Вы заблокированы! 🚫",
                parse_mode="HTML",
                reply_markup=get_main_menu("ru")
            )
            await state.clear()
            return
        translations = TRANSLATIONS.get(user.language, TRANSLATIONS["ru"])
        data = await state.get_data()
        bet = data.get("bet", 0.0)
        cards = data.get("cards", [])
        total = data.get("total", 0)
        if message.text in ["Да", "Yes"]:
            new_card = random.randint(1, 11)
            cards.append(new_card)
            total += new_card
            if total > 21:
                session.commit()
                await bot.send_message(
                    chat_id=message.chat.id,
                    text=translations["blackjack_bust"].format(total, user.balance),
                    parse_mode="HTML",
                    reply_markup=get_main_menu(user.language)
                )
                await state.clear()
                return
            await state.update_data(cards=cards, total=total)
            await bot.send_message(
                chat_id=message.chat.id,
                text=translations["blackjack_start"].format(", ".join(map(str, cards)), total),
                parse_mode="HTML",
                reply_markup=get_blackjack_hit_keyboard(user.language)
            )
        elif message.text in ["Нет", "No"]:
            dealer_total = random.randint(17, 22)
            win_chance = get_win_chance(user, ADMIN_CHAT_ID)
            if random.random() < win_chance:
                dealer_total = min(dealer_total, 16)
            if total > dealer_total or dealer_total > 21:
                winnings = bet * 2.0
                user.balance += winnings
                user.total_winnings += winnings
                session.commit()
                await bot.send_message(
                    chat_id=message.chat.id,
                    text=translations["blackjack_win"].format(winnings, user.balance),
                    parse_mode="HTML",
                    reply_markup=get_main_menu(user.language)
                )
            else:
                await bot.send_message(
                    chat_id=message.chat.id,
                    text=translations["blackjack_lose"].format(dealer_total, user.balance),
                    parse_mode="HTML",
                    reply_markup=get_main_menu(user.language)
                )
            await state.clear()
        else:
            await bot.send_message(
                chat_id=message.chat.id,
                text=translations["blackjack_start"].format(", ".join(map(str, cards)), total),
                parse_mode="HTML",
                reply_markup=get_blackjack_hit_keyboard(user.language)
            )
    except Exception as e:
        session.rollback()
        logger.error(f"Ошибка в process_blackjack_hit: {str(e)}", exc_info=True)
        await bot.send_message(
            chat_id=message.chat.id,
            text=translations["error"],
            parse_mode="HTML",
            reply_markup=get_main_menu(user.language)
        )
        await state.clear()
    finally:
        session.close()
        logger.debug("Session closed")

# Обработчик игры Орёл и Решка
@dp.message(GameState.coinflip_choice)
async def process_coinflip_choice(message: Message, state: FSMContext):
    logger.debug(f"Получен выбор для Орёл и Решка от {message.from_user.id}: {message.text}")
    session = Session()
    try:
        user = session.query(User).filter_by(telegram_id=message.from_user.id).first()
        if not user or user.is_banned:
            await bot.send_message(
                chat_id=message.chat.id,
                text=TRANSLATIONS["ru"]["error"] if not user else "❌ Вы заблокированы! 🚫",
                parse_mode="HTML",
                reply_markup=get_main_menu("ru")
            )
            await state.clear()
            return
        translations = TRANSLATIONS.get(user.language, TRANSLATIONS["ru"])
        choice = message.text
        if choice not in ["Орёл", "Решка", "Heads", "Tails"]:
            await bot.send_message(
                chat_id=message.chat.id,
                text=translations["coinflip_start"],
                parse_mode="HTML",
                reply_markup=get_coinflip_keyboard(user.language)
            )
            return
        data = await state.get_data()
        bet = data.get("bet", 0.0)
        result = random.choice(["Орёл", "Решка"] if user.language == "ru" else ["Heads", "Tails"])
        win_chance = get_win_chance(user, ADMIN_CHAT_ID)
        if random.random() < win_chance:
            result = choice
        if result == choice:
            winnings = bet * 2.0
            user.balance += winnings
            user.total_winnings += winnings
            session.commit()
            await bot.send_message(
                chat_id=message.chat.id,
                text=translations["coinflip_win"].format(result, winnings, user.balance),
                parse_mode="HTML",
                reply_markup=get_main_menu(user.language)
            )
        else:
            await bot.send_message(
                chat_id=message.chat.id,
                text=translations["coinflip_lose"].format(result, user.balance),
                parse_mode="HTML",
                reply_markup=get_main_menu(user.language)
            )
        await state.clear()
    except Exception as e:
        session.rollback()
        logger.error(f"Ошибка в process_coinflip_choice: {str(e)}", exc_info=True)
        await bot.send_message(
            chat_id=message.chat.id,
            text=translations["error"],
            parse_mode="HTML",
            reply_markup=get_main_menu(user.language)
        )
        await state.clear()
    finally:
        session.close()
        logger.debug("Session closed")

# Обработчик игры Мины
@dp.callback_query(lambda c: c.data.startswith("mines_") or c.data == "mines_cashout", GameState.mines_cell)
async def process_mines_choice(callback: CallbackQuery, state: FSMContext):
    logger.debug(f"Получен выбор для Мины от {callback.from_user.id}: {callback.data}")
    session = Session()
    try:
        user = session.query(User).filter_by(telegram_id=callback.from_user.id).first()
        if not user or user.is_banned:
            await callback.message.edit_text(
                text=TRANSLATIONS["ru"]["error"] if not user else "❌ Вы заблокированы! 🚫",
                parse_mode="HTML",
                reply_markup=None
            )
            await bot.send_message(
                chat_id=callback.message.chat.id,
                text=TRANSLATIONS["ru"]["welcome_back"].format(user.username or "Player", user.balance),
                parse_mode="HTML",
                reply_markup=get_main_menu("ru")
            )
            await state.clear()
            await callback.answer()
            return
        translations = TRANSLATIONS.get(user.language, TRANSLATIONS["ru"])
        data = await state.get_data()
        bet = data.get("bet", 0.0)
        grid = data.get("grid", [0] * 9)
        mines = data.get("mines", [])
        multiplier = data.get("multiplier", 1.0)
        opened_cells = data.get("opened_cells", 0)
        if callback.data == "mines_cashout":
            winnings = bet * multiplier
            user.balance += winnings
            user.total_winnings += winnings
            session.commit()
            await callback.message.edit_text(
                text=translations["mines_cashout"].format(multiplier, winnings, user.balance),
                parse_mode="HTML",
                reply_markup=None
            )
            await bot.send_message(
                chat_id=callback.message.chat.id,
                text=translations["welcome_back"].format(user.username or "Player", user.balance),
                parse_mode="HTML",
                reply_markup=get_main_menu(user.language)
            )
            await state.clear()
            await callback.answer()
            return
        cell = int(callback.data.split("_")[1])
        if cell in mines:
            grid[cell] = 1
            await callback.message.edit_text(
                text=translations["mines_lose"].format(user.balance),
                parse_mode="HTML",
                reply_markup=get_mines_keyboard(grid, multiplier, True, user.language)
            )
            await bot.send_message(
                chat_id=callback.message.chat.id,
                text=translations["welcome_back"].format(user.username or "Player", user.balance),
                parse_mode="HTML",
                reply_markup=get_main_menu(user.language)
            )
            await state.clear()
            await callback.answer()
            return
        grid[cell] = 2
        opened_cells += 1
        multiplier *= 1.5
        await state.update_data(grid=grid, multiplier=multiplier, opened_cells=opened_cells)
        await callback.message.edit_text(
            text=translations["mines_win"].format(multiplier, user.balance),
            parse_mode="HTML",
            reply_markup=get_mines_keyboard(grid, multiplier, False, user.language)
        )
        await callback.answer()
    except Exception as e:
        session.rollback()
        logger.error(f"Ошибка в process_mines_choice: {str(e)}", exc_info=True)
        await callback.message.edit_text(
            text=translations["error"],
            parse_mode="HTML",
            reply_markup=None
        )
        await bot.send_message(
            chat_id=callback.message.chat.id,
            text=translations["welcome_back"].format(user.username or "Player", user.balance),
            parse_mode="HTML",
            reply_markup=get_main_menu(user.language)
        )
        await state.clear()
        await callback.answer()
    finally:
        session.close()
        logger.debug("Session closed")

# Обработчик игры Рулетка
@dp.message(GameState.roulette_choice)
async def process_roulette_choice(message: Message, state: FSMContext):
    logger.debug(f"Получен выбор для Рулетки от {message.from_user.id}: {message.text}")
    session = Session()
    try:
        user = session.query(User).filter_by(telegram_id=message.from_user.id).first()
        if not user or user.is_banned:
            await bot.send_message(
                chat_id=message.chat.id,
                text=TRANSLATIONS["ru"]["error"] if not user else "❌ Вы заблокированы! 🚫",
                parse_mode="HTML",
                reply_markup=get_main_menu("ru")
            )
            await state.clear()
            return
        translations = TRANSLATIONS.get(user.language, TRANSLATIONS["ru"])
        choice = message.text
        if choice not in ["Красное", "Чёрное", "Зелёное", "Red", "Black", "Green"]:
            await bot.send_message(
                chat_id=message.chat.id,
                text=translations["roulette_start"],
                parse_mode="HTML",
                reply_markup=get_roulette_keyboard(user.language)
            )
            return
        data = await state.get_data()
        bet = data.get("bet", 0.0)
        result = random.choices(
            ["Красное", "Чёрное", "Зелёное"] if user.language == "ru" else ["Red", "Black", "Green"],
            weights=[48, 48, 4]
        )[0]
        win_chance = get_win_chance(user, ADMIN_CHAT_ID)
        if random.random() < win_chance:
            result = choice
        if result == choice:
            multiplier = 14.0 if choice in ["Зелёное", "Green"] else 2.0
            winnings = bet * multiplier
            user.balance += winnings
            user.total_winnings += winnings
            session.commit()
            await bot.send_message(
                chat_id=message.chat.id,
                text=translations["roulette_win"].format(result, winnings, user.balance),
                parse_mode="HTML",
                reply_markup=get_main_menu(user.language)
            )
        else:
            await bot.send_message(
                chat_id=message.chat.id,
                text=translations["roulette_lose"].format(result, user.balance),
                parse_mode="HTML",
                reply_markup=get_main_menu(user.language)
            )
        await state.clear()
    except Exception as e:
        session.rollback()
        logger.error(f"Ошибка в process_roulette_choice: {str(e)}", exc_info=True)
        await bot.send_message(
            chat_id=message.chat.id,
            text=translations["error"],
            parse_mode="HTML",
            reply_markup=get_main_menu(user.language)
        )
        await state.clear()
    finally:
        session.close()
        logger.debug("Session closed")

# Обработчик игры Больше/Меньше
@dp.message(GameState.overunder_choice)
async def process_overunder_choice(message: Message, state: FSMContext):
    logger.debug(f"Получен выбор для Больше/Меньше от {message.from_user.id}: {message.text}")
    session = Session()
    try:
        user = session.query(User).filter_by(telegram_id=message.from_user.id).first()
        if not user or user.is_banned:
            await bot.send_message(
                chat_id=message.chat.id,
                text=TRANSLATIONS["ru"]["error"] if not user else "❌ Вы заблокированы! 🚫",
                parse_mode="HTML",
                reply_markup=get_main_menu("ru")
            )
            await state.clear()
            return
        translations = TRANSLATIONS.get(user.language, TRANSLATIONS["ru"])
        choice = message.text
        if choice not in ["Больше", "Меньше", "Over", "Under"]:
            await bot.send_message(
                chat_id=message.chat.id,
                text=translations["overunder_start"],
                parse_mode="HTML",
                reply_markup=get_overunder_keyboard(user.language)
            )
            return
        data = await state.get_data()
        bet = data.get("bet", 0.0)
        roll = random.randint(2, 12)
        win_chance = get_win_chance(user, ADMIN_CHAT_ID)
        if random.random() < win_chance:
            roll = 8 if choice in ["Больше", "Over"] else 6
        result = "Больше" if roll > 7 else "Меньше" if user.language == "ru" else "Over" if roll > 7 else "Under"
        if result == choice:
            winnings = bet * 2.0
            user.balance += winnings
            user.total_winnings += winnings
            session.commit()
            await bot.send_message(
                chat_id=message.chat.id,
                text=translations["overunder_win"].format(roll, winnings, user.balance),
                parse_mode="HTML",
                reply_markup=get_main_menu(user.language)
            )
        else:
            await bot.send_message(
                chat_id=message.chat.id,
                text=translations["overunder_lose"].format(roll, user.balance),
                parse_mode="HTML",
                reply_markup=get_main_menu(user.language)
            )
        await state.clear()
    except Exception as e:
        session.rollback()
        logger.error(f"Ошибка в process_overunder_choice: {str(e)}", exc_info=True)
        await bot.send_message(
            chat_id=message.chat.id,
            text=translations["error"],
            parse_mode="HTML",
            reply_markup=get_main_menu(user.language)
        )
        await state.clear()
    finally:
        session.close()
        logger.debug("Session closed")

# Обработчик игры Угадай Цвет
@dp.message(GameState.guesscolor_choice)
async def process_guesscolor_choice(message: Message, state: FSMContext):
    logger.debug(f"Получен выбор для Угадай Цвет от {message.from_user.id}: {message.text}")
    session = Session()
    try:
        user = session.query(User).filter_by(telegram_id=message.from_user.id).first()
        if not user or user.is_banned:
            await bot.send_message(
                chat_id=message.chat.id,
                text=TRANSLATIONS["ru"]["error"] if not user else "❌ Вы заблокированы! 🚫",
                parse_mode="HTML",
                reply_markup=get_main_menu("ru")
            )
            await state.clear()
            return
        translations = TRANSLATIONS.get(user.language, TRANSLATIONS["ru"])
        choice = message.text
        if choice not in ["Красный", "Синий", "Жёлтый", "Зелёный", "Red", "Blue", "Yellow", "Green"]:
            await bot.send_message(
                chat_id=message.chat.id,
                text=translations["guesscolor_start"],
                parse_mode="HTML",
                reply_markup=get_guesscolor_keyboard(user.language)
            )
            return
        data = await state.get_data()
        bet = data.get("bet", 0.0)
        result = random.choice(["Красный", "Синий", "Жёлтый", "Зелёный"] if user.language == "ru" else ["Red", "Blue", "Yellow", "Green"])
        win_chance = get_win_chance(user, ADMIN_CHAT_ID)
        if random.random() < win_chance:
            result = choice
        if result == choice:
            winnings = bet * 4.0
            user.balance += winnings
            user.total_winnings += winnings
            session.commit()
            await bot.send_message(
                chat_id=message.chat.id,
                text=translations["guesscolor_win"].format(result, winnings, user.balance),
                parse_mode="HTML",
                reply_markup=get_main_menu(user.language)
            )
        else:
            await bot.send_message(
                chat_id=message.chat.id,
                text=translations["guesscolor_lose"].format(result, user.balance),
                parse_mode="HTML",
                reply_markup=get_main_menu(user.language)
            )
        await state.clear()
    except Exception as e:
        session.rollback()
        logger.error(f"Ошибка в process_guesscolor_choice: {str(e)}", exc_info=True)
        await bot.send_message(
            chat_id=message.chat.id,
            text=translations["error"],
            parse_mode="HTML",
            reply_markup=get_main_menu(user.language)
        )
        await state.clear()
    finally:
        session.close()
        logger.debug("Session closed")

# Обработчик выбора метода пополнения
@dp.message(TransactionState.deposit_method)
async def process_deposit_method(message: Message, state: FSMContext):
    logger.debug(f"Получен выбор метода пополнения от {message.from_user.id}: {message.text}")
    session = Session()
    try:
        user = session.query(User).filter_by(telegram_id=message.from_user.id).first()
        if not user or user.is_banned:
            await bot.send_message(
                chat_id=message.chat.id,
                text=TRANSLATIONS["ru"]["error"] if not user else "❌ Вы заблокированы! 🚫",
                parse_mode="HTML",
                reply_markup=get_main_menu("ru")
            )
            await state.clear()
            return
        translations = TRANSLATIONS.get(user.language, TRANSLATIONS["ru"])
        method = message.text
        if method not in ["Банковская карта 💳", "Электронный кошелёк 💸", "Bank Card 💳", "E-Wallet 💸"]:
            await bot.send_message(
                chat_id=message.chat.id,
                text=translations["deposit_method"],
                parse_mode="HTML",
                reply_markup=get_deposit_method_keyboard(user.language)
            )
            return
        await state.update_data(deposit_method=method)
        await bot.send_message(
            chat_id=message.chat.id,
            text=translations["deposit_amount"],
            parse_mode="HTML"
        )
        await state.set_state(TransactionState.deposit_amount)
    except Exception as e:
        session.rollback()
        logger.error(f"Ошибка в process_deposit_method: {str(e)}", exc_info=True)
        await bot.send_message(
            chat_id=message.chat.id,
            text=translations["error"],
            parse_mode="HTML",
            reply_markup=get_main_menu(user.language)
        )
        await state.clear()
    finally:
        session.close()
        logger.debug("Session closed")

# Обработчик суммы пополнения
@dp.message(TransactionState.deposit_amount)
async def process_deposit_amount(message: Message, state: FSMContext):
    logger.debug(f"Получена сумма пополнения от {message.from_user.id}: {message.text}")
    session = Session()
    try:
        user = session.query(User).filter_by(telegram_id=message.from_user.id).first()
        if not user or user.is_banned:
            await bot.send_message(
                chat_id=message.chat.id,
                text=TRANSLATIONS["ru"]["error"] if not user else "❌ Вы заблокированы! 🚫",
                parse_mode="HTML",
                reply_markup=get_main_menu("ru")
            )
            await state.clear()
            return
        translations = TRANSLATIONS.get(user.language, TRANSLATIONS["ru"])
        try:
            amount = float(message.text.strip())
            if amount < 1000:
                await bot.send_message(
                    chat_id=message.chat.id,
                    text=translations["deposit_amount"],
                    parse_mode="HTML"
                )
                return
            await state.update_data(deposit_amount=amount)
            await bot.send_message(
                chat_id=message.chat.id,
                text=translations["deposit_details"],
                parse_mode="HTML"
            )
            await state.set_state(TransactionState.deposit_details)
        except ValueError:
            await bot.send_message(
                chat_id=message.chat.id,
                text=translations["deposit_amount"],
                parse_mode="HTML"
            )
    except Exception as e:
        session.rollback()
        logger.error(f"Ошибка в process_deposit_amount: {str(e)}", exc_info=True)
        await bot.send_message(
            chat_id=message.chat.id,
            text=translations["error"],
            parse_mode="HTML",
            reply_markup=get_main_menu(user.language)
        )
        await state.clear()
    finally:
        session.close()
        logger.debug("Session closed")

# Обработчик деталей пополнения
@dp.message(TransactionState.deposit_details)
async def process_deposit_details(message: Message, state: FSMContext):
    logger.debug(f"Получены детали пополнения от {message.from_user.id}: {message.text}")
    session = Session()
    try:
        user = session.query(User).filter_by(telegram_id=message.from_user.id).first()
        if not user or user.is_banned:
            await bot.send_message(
                chat_id=message.chat.id,
                text=TRANSLATIONS["ru"]["error"] if not user else "❌ Вы заблокированы! 🚫",
                parse_mode="HTML",
                reply_markup=get_main_menu("ru")
            )
            await state.clear()
            return
        translations = TRANSLATIONS.get(user.language, TRANSLATIONS["ru"])
        data = await state.get_data()
        method = data.get("deposit_method")
        amount = data.get("deposit_amount")
        details = message.text.strip()
        withdraw_request = WithdrawRequest(
            user_id=user.id,
            amount=amount,
            method=method,
            details=details,
            status="pending"
        )
        session.add(withdraw_request)
        session.commit()
        await bot.send_message(
            chat_id=message.chat.id,
            text=translations["deposit_success"].format(amount, user.balance),
            parse_mode="HTML",
            reply_markup=get_main_menu(user.language)
        )
        await bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=translations["admin_deposit_request"].format(
                user.telegram_id, user.username or "User", amount, method, details,
                withdraw_request.id, user.id
            ),
            parse_mode="HTML"
        )
        await state.clear()
    except Exception as e:
        session.rollback()
        logger.error(f"Ошибка в process_deposit_details: {str(e)}", exc_info=True)
        await bot.send_message(
            chat_id=message.chat.id,
            text=translations["error"],
            parse_mode="HTML",
            reply_markup=get_main_menu(user.language)
        )
        await state.clear()
    finally:
        session.close()
        logger.debug("Session closed")

# Обработчик выбора метода вывода
@dp.message(TransactionState.withdraw_method)
async def process_withdraw_method(message: Message, state: FSMContext):
    logger.debug(f"Получен выбор метода вывода от {message.from_user.id}: {message.text}")
    session = Session()
    try:
        user = session.query(User).filter_by(telegram_id=message.from_user.id).first()
        if not user or user.is_banned:
            await bot.send_message(
                chat_id=message.chat.id,
                text=TRANSLATIONS["ru"]["error"] if not user else "❌ Вы заблокированы! 🚫",
                parse_mode="HTML",
                reply_markup=get_main_menu("ru")
            )
            await state.clear()
            return
        translations = TRANSLATIONS.get(user.language, TRANSLATIONS["ru"])
        method = message.text
        if method not in ["Банковская карта 💳", "Электронный кошелёк 💸", "Bank Card 💳", "E-Wallet 💸"]:
            await bot.send_message(
                chat_id=message.chat.id,
                text=translations["withdraw_method"],
                parse_mode="HTML",
                reply_markup=get_withdraw_method_keyboard(user.language)
            )
            return
        await state.update_data(withdraw_method=method)
        await bot.send_message(
            chat_id=message.chat.id,
            text=translations["withdraw_amount"],
            parse_mode="HTML"
        )
        await state.set_state(TransactionState.withdraw_amount)
    except Exception as e:
        session.rollback()
        logger.error(f"Ошибка в process_withdraw_method: {str(e)}", exc_info=True)
        await bot.send_message(
            chat_id=message.chat.id,
            text=translations["error"],
            parse_mode="HTML",
            reply_markup=get_main_menu(user.language)
        )
        await state.clear()
    finally:
        session.close()
        logger.debug("Session closed")

# Обработчик суммы вывода
@dp.message(TransactionState.withdraw_amount)
async def process_withdraw_amount(message: Message, state: FSMContext):
    logger.debug(f"Получена сумма вывода от {message.from_user.id}: {message.text}")
    session = Session()
    try:
        user = session.query(User).filter_by(telegram_id=message.from_user.id).first()
        if not user or user.is_banned:
            await bot.send_message(
                chat_id=message.chat.id,
                text=TRANSLATIONS["ru"]["error"] if not user else "❌ Вы заблокированы! 🚫",
                parse_mode="HTML",
                reply_markup=get_main_menu("ru")
            )
            await state.clear()
            return
        translations = TRANSLATIONS.get(user.language, TRANSLATIONS["ru"])
        try:
            amount = float(message.text.strip())
            if amount < 1000:
                await bot.send_message(
                    chat_id=message.chat.id,
                    text=translations["withdraw_amount"],
                    parse_mode="HTML"
                )
                return
            if amount > user.balance:
                await bot.send_message(
                    chat_id=message.chat.id,
                    text=translations["insufficient_balance"].format(user.balance),
                    parse_mode="HTML"
                )
                return
            await state.update_data(withdraw_amount=amount)
            await bot.send_message(
                chat_id=message.chat.id,
                text=translations["withdraw_details"],
                parse_mode="HTML"
            )
            await state.set_state(TransactionState.withdraw_details)
        except ValueError:
            await bot.send_message(
                chat_id=message.chat.id,
                text=translations["withdraw_amount"],
                parse_mode="HTML"
            )
    except Exception as e:
        session.rollback()
        logger.error(f"Ошибка в process_withdraw_amount: {str(e)}", exc_info=True)
        await bot.send_message(
            chat_id=message.chat.id,
            text=translations["error"],
            parse_mode="HTML",
            reply_markup=get_main_menu(user.language)
        )
        await state.clear()
    finally:
        session.close()
        logger.debug("Session closed")

# Обработчик деталей вывода
@dp.message(TransactionState.withdraw_details)
async def process_withdraw_details(message: Message, state: FSMContext):
    logger.debug(f"Получены детали вывода от {message.from_user.id}: {message.text}")
    session = Session()
    try:
        user = session.query(User).filter_by(telegram_id=message.from_user.id).first()
        if not user or user.is_banned:
            await bot.send_message(
                chat_id=message.chat.id,
                text=TRANSLATIONS["ru"]["error"] if not user else "❌ Вы заблокированы! 🚫",
                parse_mode="HTML",
                reply_markup=get_main_menu("ru")
            )
            await state.clear()
            return
        translations = TRANSLATIONS.get(user.language, TRANSLATIONS["ru"])
        data = await state.get_data()
        method = data.get("withdraw_method")
        amount = data.get("withdraw_amount")
        details = message.text.strip()
        user.balance -= amount
        user.withdrawal_count += 1
        user.total_withdrawals += amount
        withdraw_request = WithdrawRequest(
            user_id=user.id,
            amount=amount,
            method=method,
            details=details,
            status="pending"
        )
        session.add(withdraw_request)
        session.commit()
        await bot.send_message(
            chat_id=message.chat.id,
            text=translations["withdraw_success"].format(amount, user.balance),
            parse_mode="HTML",
            reply_markup=get_main_menu(user.language)
        )
        await bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=translations["admin_withdraw_request"].format(
                user.telegram_id, user.username or "User", amount, method, details,
                withdraw_request.id, user.id
            ),
            parse_mode="HTML"
        )
        await state.clear()
    except Exception as e:
        session.rollback()
        logger.error(f"Ошибка в process_withdraw_details: {str(e)}", exc_info=True)
        await bot.send_message(
            chat_id=message.chat.id,
            text=translations["error"],
            parse_mode="HTML",
            reply_markup=get_main_menu(user.language)
        )
        await state.clear()
    finally:
        session.close()
        logger.debug("Session closed")

# Обработчик одобрения пополнения
@dp.message(RegexpCommandsFilter(regexp_commands=[r"/approve_deposit_(\d+)_(\d+)"]))
async def approve_deposit(message: Message, regexp_command: re.Match):
    logger.debug(f"Получено одобрение пополнения от {message.from_user.id}: {message.text}")
    if message.from_user.id != ADMIN_CHAT_ID:
        await bot.send_message(
            chat_id=message.chat.id,
            text=TRANSLATIONS["ru"]["not_admin"],
            parse_mode="HTML"
        )
        return
    session = Session()
    try:
        request_id = int(regexp_command.group(1))
        user_id = int(regexp_command.group(2))
        request = session.query(WithdrawRequest).filter_by(id=request_id, user_id=user_id, status="pending").first()
        if not request:
            await bot.send_message(
                chat_id=message.chat.id,
                text="❌ Запрос не найден или уже обработан!",
                parse_mode="HTML"
            )
            return
        user = session.query(User).filter_by(id=user_id).first()
        if not user:
            await bot.send_message(
                chat_id=message.chat.id,
                text=TRANSLATIONS["ru"]["admin_user_not_found"],
                parse_mode="HTML"
            )
            return
        user.balance += request.amount
        user.deposit_count += 1
        user.total_deposits += request.amount
        request.status = "approved"
        session.commit()
        translations = TRANSLATIONS.get(user.language, TRANSLATIONS["ru"])
        await bot.send_message(
            chat_id=message.chat.id,
            text=translations["admin_deposit_approve"].format(request.amount, user.username or "User", user.balance),
            parse_mode="HTML"
        )
        await bot.send_message(
            chat_id=user.telegram_id,
            text=translations["deposit_success"].format(request.amount, user.balance),
            parse_mode="HTML",
            reply_markup=get_main_menu(user.language)
        )
    except Exception as e:
        session.rollback()
        logger.error(f"Ошибка в approve_deposit: {str(e)}", exc_info=True)
        await bot.send_message(
            chat_id=message.chat.id,
            text=TRANSLATIONS["ru"]["error"],
            parse_mode="HTML"
        )
    finally:
        session.close()
        logger.debug("Session closed")

# Обработчик отклонения пополнения
@dp.message(RegexpCommandsFilter(regexp_commands=[r"/decline_deposit_(\d+)_(\d+)"]))
async def decline_deposit(message: Message, regexp_command: re.Match):
    logger.debug(f"Получено отклонение пополнения от {message.from_user.id}: {message.text}")
    if message.from_user.id != ADMIN_CHAT_ID:
        await bot.send_message(
            chat_id=message.chat.id,
            text=TRANSLATIONS["ru"]["not_admin"],
            parse_mode="HTML"
        )
        return
    session = Session()
    try:
        request_id = int(regexp_command.group(1))
        user_id = int(regexp_command.group(2))
        request = session.query(WithdrawRequest).filter_by(id=request_id, user_id=user_id, status="pending").first()
        if not request:
            await bot.send_message(
                chat_id=message.chat.id,
                text="❌ Запрос не найден или уже обработан!",
                parse_mode="HTML"
            )
            return
        user = session.query(User).filter_by(id=user_id).first()
        if not user:
            await bot.send_message(
                chat_id=message.chat.id,
                text=TRANSLATIONS["ru"]["admin_user_not_found"],
                parse_mode="HTML"
            )
            return
        request.status = "declined"
        session.commit()
        translations = TRANSLATIONS.get(user.language, TRANSLATIONS["ru"])
        await bot.send_message(
            chat_id=message.chat.id,
            text=translations["admin_deposit_decline"].format(request.amount, user.username or "User"),
            parse_mode="HTML"
        )
        await bot.send_message(
            chat_id=user.telegram_id,
            text=translations["admin_deposit_decline"].format(request.amount, user.username or "User"),
            parse_mode="HTML",
            reply_markup=get_main_menu(user.language)
        )
    except Exception as e:
        session.rollback()
        logger.error(f"Ошибка в decline_deposit: {str(e)}", exc_info=True)
        await bot.send_message(
            chat_id=message.chat.id,
            text=TRANSLATIONS["ru"]["error"],
            parse_mode="HTML"
        )
    finally:
        session.close()
        logger.debug("Session closed")

# Обработчик одобрения вывода
@dp.message(RegexpCommandsFilter(regexp_commands=[r"/approve_withdraw_(\d+)_(\d+)"]))
async def approve_withdraw(message: Message, regexp_command: re.Match):
    logger.debug(f"Получено одобрение вывода от {message.from_user.id}: {message.text}")
    if message.from_user.id != ADMIN_CHAT_ID:
        await bot.send_message(
            chat_id=message.chat.id,
            text=TRANSLATIONS["ru"]["not_admin"],
            parse_mode="HTML"
        )
        return
    session = Session()
    try:
        request_id = int(regexp_command.group(1))
        user_id = int(regexp_command.group(2))
        request = session.query(WithdrawRequest).filter_by(id=request_id, user_id=user_id, status="pending").first()
        if not request:
            await bot.send_message(
                chat_id=message.chat.id,
                text="❌ Запрос не найден или уже обработан!",
                parse_mode="HTML"
            )
            return
        user = session.query(User).filter_by(id=user_id).first()
        if not user:
            await bot.send_message(
                chat_id=message.chat.id,
                text=TRANSLATIONS["ru"]["admin_user_not_found"],
                parse_mode="HTML"
            )
            return
        request.status = "approved"
        session.commit()
        translations = TRANSLATIONS.get(user.language, TRANSLATIONS["ru"])
        await bot.send_message(
            chat_id=message.chat.id,
            text=translations["admin_withdraw_approve"].format(request.amount, user.username or "User", user.balance),
            parse_mode="HTML"
        )
        await bot.send_message(
            chat_id=user.telegram_id,
            text=translations["withdraw_success"].format(request.amount, user.balance),
            parse_mode="HTML",
            reply_markup=get_main_menu(user.language)
        )
    except Exception as e:
        session.rollback()
        logger.error(f"Ошибка в approve_withdraw: {str(e)}", exc_info=True)
        await bot.send_message(
            chat_id=message.chat.id,
            text=TRANSLATIONS["ru"]["error"],
            parse_mode="HTML"
        )
    finally:
        session.close()
        logger.debug("Session closed")

# Обработчик отклонения вывода
@dp.message(RegexpCommandsFilter(regexp_commands=[r"/decline_withdraw_(\d+)_(\d+)"]))
async def decline_withdraw(message: Message, regexp_command: re.Match):
    logger.debug(f"Получено отклонение вывода от {message.from_user.id}: {message.text}")
    if message.from_user.id != ADMIN_CHAT_ID:
        await bot.send_message(
            chat_id=message.chat.id,
            text=TRANSLATIONS["ru"]["not_admin"],
            parse_mode="HTML"
        )
        return
    session = Session()
    try:
        request_id = int(regexp_command.group(1))
        user_id = int(regexp_command.group(2))
        request = session.query(WithdrawRequest).filter_by(id=request_id, user_id=user_id, status="pending").first()
        if not request:
            await bot.send_message(
                chat_id=message.chat.id,
                text="❌ Запрос не найден или уже обработан!",
                parse_mode="HTML"
            )
            return
        user = session.query(User).filter_by(id=user_id).first()
        if not user:
            await bot.send_message(
                chat_id=message.chat.id,
                text=TRANSLATIONS["ru"]["admin_user_not_found"],
                parse_mode="HTML"
            )
            return
        user.balance += request.amount
        user.withdrawal_count -= 1
        user.total_withdrawals -= request.amount
        request.status = "declined"
        session.commit()
        translations = TRANSLATIONS.get(user.language, TRANSLATIONS["ru"])
        await bot.send_message(
            chat_id=message.chat.id,
            text=translations["admin_withdraw_decline"].format(request.amount, user.username or "User"),
            parse_mode="HTML"
        )
        await bot.send_message(
            chat_id=user.telegram_id,
            text=translations["admin_withdraw_decline"].format(request.amount, user.username or "User"),
            parse_mode="HTML",
            reply_markup=get_main_menu(user.language)
        )
    except Exception as e:
        session.rollback()
        logger.error(f"Ошибка в decline_withdraw: {str(e)}", exc_info=True)
        await bot.send_message(
            chat_id=message.chat.id,
            text=TRANSLATIONS["ru"]["error"],
            parse_mode="HTML"
        )
    finally:
        session.close()
        logger.debug("Session closed")
# Основной запуск бота
async def main():
    logger.info("Бот запущен")
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {str(e)}", exc_info=True)
        await asyncio.sleep(5)
        await main()

if __name__ == "__main__":
    asyncio.run(main())