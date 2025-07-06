import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Update

from utils.logging import log_exception

logger = logging.getLogger(__name__)

class LoggingMiddleware(BaseMiddleware):
    """Middleware to log update and chat IDs and handle exceptions."""

    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any]
    ) -> Any:
        # Log update ID and chat ID if available
        update_id = event.update_id
        chat_id = None
        user_id = None

        # Try to get chat ID and user ID from different types of updates
        if event.message:
            chat_id = event.message.chat.id
            user_id = event.message.from_user.id if event.message.from_user else None
        elif event.edited_message:
            chat_id = event.edited_message.chat.id
            user_id = event.edited_message.from_user.id if event.edited_message.from_user else None
        elif event.callback_query:
            user_id = event.callback_query.from_user.id if event.callback_query.from_user else None
            if event.callback_query.message:
                chat_id = event.callback_query.message.chat.id
        elif event.channel_post:
            chat_id = event.channel_post.chat.id
        elif event.edited_channel_post:
            chat_id = event.edited_channel_post.chat.id
        elif event.my_chat_member:
            chat_id = event.my_chat_member.chat.id
            user_id = event.my_chat_member.from_user.id if event.my_chat_member.from_user else None
        elif event.chat_member:
            chat_id = event.chat_member.chat.id
            user_id = event.chat_member.from_user.id if event.chat_member.from_user else None
        elif event.chat_join_request:
            chat_id = event.chat_join_request.chat.id
            user_id = event.chat_join_request.from_user.id if event.chat_join_request.from_user else None

        # Log the update ID and chat ID
        if chat_id is not None:
            logger.info(f"Chat ID: {chat_id}")
            logger.info(f"Update ID: {update_id}, User ID: {user_id}")
        else:
            logger.info(f"Chat ID: Not available")
            logger.info(f"Update ID: {update_id}, User ID: {user_id}")

        try:
            # Continue processing the update
            return await handler(event, data)
        except Exception as e:
            # Get context information
            context = {
                "update_id": update_id,
                "update_type": self._get_update_type(event),
                "data": {k: str(v) for k, v in data.items() if k != "bot" and k != "dispatcher"}
            }

            # Log the exception with context
            log_exception(
                exception=e,
                context=context,
                user_id=user_id,
                message=f"Unhandled exception in update handler"
            )

            # Re-raise the exception to let the framework handle it
            raise

    def _get_update_type(self, event: Update) -> str:
        """Get the type of update."""
        if event.message:
            return "message"
        elif event.edited_message:
            return "edited_message"
        elif event.callback_query:
            return "callback_query"
        elif event.channel_post:
            return "channel_post"
        elif event.edited_channel_post:
            return "edited_channel_post"
        elif event.my_chat_member:
            return "my_chat_member"
        elif event.chat_member:
            return "chat_member"
        elif event.chat_join_request:
            return "chat_join_request"
        else:
            return "unknown"
