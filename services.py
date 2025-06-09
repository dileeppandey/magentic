import uuid
from flask import session
from models import db, User, Chat
import asyncio

def get_or_create_user():
    user_id = session.get('user_id')
    if not user_id:
        user_id = str(uuid.uuid4())
        session['user_id'] = user_id
        user = User(id=user_id)
        db.session.add(user)
        db.session.commit()
    else:
        user = User.query.get(user_id)
        if not user:
            user = User(id=user_id)
            db.session.add(user)
            db.session.commit()
    return user

def get_or_create_chat(user, message, title_agent):
    current_chat_id = session.get('current_chat_id')
    chat = Chat.query.get(current_chat_id) if current_chat_id else None
    if not chat:
        try:
            title_response = asyncio.run(title_agent.ainvoke({"messages": [{"role": "user", "content": f"{message}"}]}))
            chat_title = title_response.get('content', message[:60])
            chat = Chat(user_id=user.id, title=chat_title)
            db.session.add(chat)
            db.session.commit()
            session['current_chat_id'] = chat.id
        except Exception as e:
            import logging
            logging.getLogger("naviable-agents").error(f"Failed to create chat: {e}")
            return None
    return chat 