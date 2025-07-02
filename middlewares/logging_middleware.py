import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Update

logger = logging.getLogger(__name__)

class LoggingMiddleware(BaseMiddleware):
    """Middleware to log update and chat IDs."""
    
    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any]
    ) -> Any:
        # Log update ID and chat ID if available
        update_id = event.update_id
        chat_id = None
        
        # Try to get chat ID from different types of updates
        if event.message:
            chat_id = event.message.chat.id
        elif event.edited_message:
            chat_id = event.edited_message.chat.id
        elif event.callback_query and event.callback_query.message:
            chat_id = event.callback_query.message.chat.id
        elif event.channel_post:
            chat_id = event.channel_post.chat.id
        elif event.edited_channel_post:
            chat_id = event.edited_channel_post.chat.id
        elif event.my_chat_member:
            chat_id = event.my_chat_member.chat.id
        elif event.chat_member:
            chat_id = event.chat_member.chat.id
        elif event.chat_join_request:
            chat_id = event.chat_join_request.chat.id
            
        # Log the update ID and chat ID
        if chat_id is not None:
            logger.info(f"Update ID: {update_id}, Chat ID: {chat_id}")
        else:
            logger.info(f"Update ID: {update_id}, Chat ID: Not available")
            
        # Continue processing the update
        return await handler(event, data)