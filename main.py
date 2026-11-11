import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.config import BASE_DIR, settings
from app.database.db import Database
from app.handlers.github import router
from app.services.github_api import GitHubAPI


def configure_logging() -> None:
    log_dir = BASE_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_dir / "bot.log", encoding="utf-8"),
        ],
        force=True,
    )


async def main() -> None:
    configure_logging()
    logger = logging.getLogger(__name__)

    database = Database(settings.database_path)
    await database.initialize()

    github_token = (
        settings.github_token.get_secret_value()
        if settings.github_token
        else None
    )
    github = GitHubAPI(
        base_url=settings.github_api_url,
        timeout=settings.github_timeout,
        token=github_token,
        cache_ttl=settings.github_cache_ttl,
        cache_max_entries=settings.github_cache_max_entries,
    )

    bot = Bot(
        token=settings.bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher()
    dispatcher.include_router(router)

    try:
        logger.info("Starting GitHub Intelligence Bot...")
        await bot.delete_webhook(drop_pending_updates=True)
        await dispatcher.start_polling(bot, github=github, db=database)
    finally:
        await github.close()
        await bot.session.close()
        logger.info("Bot stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Bot stopped by user.")
