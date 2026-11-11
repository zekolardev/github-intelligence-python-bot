import logging
from datetime import datetime, timezone
from html import escape

from aiogram import Router
from aiogram.filters import Command
from aiogram.filters.command import CommandObject
from aiogram.types import Message

from app.database.db import Database
from app.services.github_api import (
    GitHubAPI,
    GitHubAPIError,
    GitHubAuthenticationError,
    GitHubForbiddenError,
    GitHubNotFoundError,
    GitHubRateLimitError,
    GitHubServerError,
    validate_username,
)

logger = logging.getLogger(__name__)
router = Router()


def _rate_limit_message(error: GitHubRateLimitError) -> str:
    if error.reset_at:
        reset = datetime.fromtimestamp(error.reset_at, tz=timezone.utc)
        return (
            "محدودیت درخواست GitHub تمام شده است.\n"
            f"زمان تقریبی بازنشانی: {reset:%Y-%m-%d %H:%M:%S} UTC"
        )
    return "محدودیت درخواست GitHub تمام شده است. کمی بعد دوباره تلاش کن."


def _api_error_message(error: GitHubAPIError) -> str:
    if isinstance(error, GitHubAuthenticationError):
        return "توکن GitHub معتبر نیست. تنظیمات GITHUB_TOKEN را بررسی کن."
    if isinstance(error, GitHubForbiddenError):
        return "GitHub اجازه دسترسی به این منبع را نداد."
    if isinstance(error, GitHubServerError):
        return "سرورهای GitHub موقتاً دچار مشکل هستند. بعداً تلاش کن."
    return "ارتباط با GitHub با مشکل مواجه شد. دوباره تلاش کن."


@router.message(Command("start"))
async def start_handler(message: Message, db: Database) -> None:
    user = message.from_user
    if user:
        await db.save_user(
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
        )

    await message.answer(
        "سلام! به <b>GitHub Intelligence</b> خوش آمدی.\n\n"
        "من برای بررسی اطلاعات GitHub ساخته شده‌ام.\n\n"
        "<b>دستورات:</b>\n"
        "<code>/user username</code>\n"
        "<code>/repo owner/repository</code>\n"
        "<code>/help</code>"
    )


@router.message(Command("help"))
async def help_handler(message: Message) -> None:
    await message.answer(
        "<b>راهنمای ربات</b>\n\n"
        "<code>/user torvalds</code>\n"
        "نمایش اطلاعات یک کاربر GitHub\n\n"
        "<code>/repo python/cpython</code>\n"
        "نمایش اطلاعات یک مخزن GitHub"
    )


@router.message(Command("user"))
async def user_handler(
    message: Message,
    command: CommandObject,
    github: GitHubAPI,
) -> None:
    username = (command.args or "").strip()
    if not username:
        await message.answer("نام کاربری را وارد کن:\n<code>/user torvalds</code>")
        return
    if not validate_username(username):
        await message.answer("نام کاربری GitHub معتبر نیست.")
        return

    try:
        user = await github.get_user(username)
        name = escape(str(user.get("name") or user["login"]))
        login = escape(str(user["login"]))
        bio = escape(str(user.get("bio") or "بدون توضیحات"))
        url = escape(str(user["html_url"]), quote=True)

        await message.answer(
            f"<b>{name}</b>\n"
            f"@{login}\n\n"
            f"{bio}\n\n"
            f"Repositories: <b>{user.get('public_repos', 0)}</b>\n"
            f"Followers: <b>{user.get('followers', 0)}</b>\n"
            f"Following: <b>{user.get('following', 0)}</b>\n\n"
            f'<a href="{url}">مشاهده پروفایل GitHub</a>'
        )
    except GitHubNotFoundError:
        await message.answer("کاربر موردنظر پیدا نشد.")
    except GitHubRateLimitError as exc:
        await message.answer(_rate_limit_message(exc))
    except GitHubAPIError as exc:
        logger.warning("GitHub user lookup failed for %s: %s", username, type(exc).__name__)
        await message.answer(_api_error_message(exc))


@router.message(Command("repo"))
async def repository_handler(
    message: Message,
    command: CommandObject,
    github: GitHubAPI,
) -> None:
    argument = (command.args or "").strip()
    if argument.count("/") != 1:
        await message.answer(
            "نام مخزن را با این قالب وارد کن:\n"
            "<code>/repo python/cpython</code>"
        )
        return

    owner, repository = argument.split("/", maxsplit=1)
    try:
        repo = await github.get_repository(owner, repository)
        full_name = escape(str(repo["full_name"]))
        description = escape(str(repo.get("description") or "بدون توضیحات"))
        url = escape(str(repo["html_url"]), quote=True)
        language = escape(str(repo.get("language") or "نامشخص"))
        branch = escape(str(repo.get("default_branch") or "نامشخص"))

        await message.answer(
            f"<b>{full_name}</b>\n\n"
            f"{description}\n\n"
            f"Language: <b>{language}</b>\n"
            f"Stars: <b>{repo.get('stargazers_count', 0)}</b>\n"
            f"Forks: <b>{repo.get('forks_count', 0)}</b>\n"
            f"Open issues: <b>{repo.get('open_issues_count', 0)}</b>\n"
            f"Default branch: <code>{branch}</code>\n\n"
            f'<a href="{url}">مشاهده مخزن در GitHub</a>'
        )
    except ValueError:
        await message.answer("نام مالک یا مخزن معتبر نیست.")
    except GitHubNotFoundError:
        await message.answer("مخزن موردنظر پیدا نشد.")
    except GitHubRateLimitError as exc:
        await message.answer(_rate_limit_message(exc))
    except GitHubAPIError as exc:
        logger.warning(
            "GitHub repository lookup failed for %s/%s: %s",
            owner,
            repository,
            type(exc).__name__,
        )
        await message.answer(_api_error_message(exc))
