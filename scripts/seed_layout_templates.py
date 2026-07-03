"""Перерегистрировать макеты из Layout/ в БД."""
import asyncio

from app.services.template_manager import list_templates, seed_layout_templates


async def main() -> None:
    registered = await seed_layout_templates()
    print("Зарегистрировано:", registered)
    templates = await list_templates()
    for item in templates:
        print("-", item.name, "->", item.file_path)


if __name__ == "__main__":
    asyncio.run(main())
