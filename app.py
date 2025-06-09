import os
import traceback
from flask import Flask, request, jsonify, session
from flask_cors import CORS
from models import db, Message
from utils import enforce_role_alternation, flatten_messages
from services import get_or_create_user, get_or_create_chat
from magentic_ai import supervisor_agent, summary_chain, title_agent

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'your-secret-key-here')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///naviable.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Configure CORS
CORS(app, 
     resources={r"/*": {"origins": ["http://localhost:3001"]}},
     supports_credentials=True,
     allow_headers=["Content-Type", "Authorization"],
     methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])

db.init_app(app)

with app.app_context():
    db.create_all()

@app.route('/')
def index():
    return jsonify({'message': 'NaviAble API is running!', 'status': 'success', 'app': 'NaviAble - Your Intelligent Navigation Assistant'})

@app.route('/chat', methods=['POST'])
def chat():
    try:
        data = request.get_json()
        message = data.get('message', '').strip()
        if not message:
            return jsonify({'error': 'Message is required'}), 400
        user = get_or_create_user()
        chat = get_or_create_chat(user, message, title_agent)
        if chat is None:
            return jsonify({'error': 'Chat not found or could not be created.'}), 400
        # 1. Save the user's message
        user_message = Message(chat_id=chat.id, role='user', content=message)
        db.session.add(user_message)
        db.session.commit()
        # 2. Reload the full message history (now includes the new user message)
        api_messages = [{'role': msg.role, 'content': msg.content} for msg in chat.messages]
        # 3. Generate assistant response using supervisor_agent from magentic-ai.py
        response = supervisor_agent(api_messages)
        if hasattr(response, '__await__'):
            import asyncio
            response = asyncio.run(response)
        history_text = flatten_messages(api_messages)
        summary_obj = summary_chain.run({'history': history_text})
        formatted_response = summary_obj.markdown
        # 4. Save the assistant's message
        assistant_message = Message(chat_id=chat.id, role='assistant', content=formatted_response)
        db.session.add(assistant_message)
        db.session.commit()
        return jsonify({'response': formatted_response, 'chat_id': chat.id})
    except Exception as e:
        tb = traceback.format_exc()
        app.logger.error(f"Error in chat endpoint: {str(e)}\n{tb}")
        return jsonify({'error': str(e), 'traceback': tb}), 500

@app.route('/clear', methods=['POST'])
def clear_chat():
    current_chat_id = session.get('current_chat_id')
    if current_chat_id:
        from models import Chat
        chat = Chat.query.get(current_chat_id)
        if chat:
            Message.query.filter_by(chat_id=current_chat_id).delete()
            db.session.commit()
    return jsonify({'success': True})

@app.route('/history')
def get_history():
    current_chat_id = session.get('current_chat_id')
    if not current_chat_id:
        return jsonify({'messages': []})
    from models import Chat
    chat = Chat.query.get(current_chat_id)
    if not chat:
        return jsonify({'messages': []})
    messages = [{
        'role': msg.role,
        'content': msg.content,
        'timestamp': msg.timestamp.strftime('%H:%M')
    } for msg in chat.messages]
    return jsonify({'messages': messages})

@app.route('/chats', methods=['GET'])
def get_all_chats():
    from models import Chat
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'chats': []})
    chats = Chat.query.filter_by(user_id=user_id).order_by(Chat.updated_at.desc()).all()
    user_chats = [{
        'id': chat.id,
        'title': chat.title,
        'created_at': chat.created_at.strftime('%Y-%m-%d %H:%M'),
        'updated_at': chat.updated_at.strftime('%Y-%m-%d %H:%M')
    } for chat in chats]
    return jsonify({'chats': user_chats})

@app.route('/chats', methods=['POST'])
def create_new_chat():
    user = get_or_create_user()
    from models import Chat
    import uuid
    chat_id = str(uuid.uuid4())
    chat = Chat(id=chat_id, user_id=user.id)
    db.session.add(chat)
    db.session.commit()
    session['current_chat_id'] = chat_id
    return jsonify({'chat_id': chat_id, 'status': 'created'})

@app.route('/chats/<chat_id>', methods=['GET'])
def get_chat(chat_id):
    from models import Chat
    chat = Chat.query.get(chat_id)
    if not chat:
        return jsonify({'error': 'Chat not found'}), 404
    messages = [{
        'role': msg.role,
        'content': msg.content,
        'timestamp': msg.timestamp.strftime('%H:%M')
    } for msg in chat.messages]
    return jsonify({'messages': messages, 'title': chat.title})

@app.route('/chats/<chat_id>', methods=['DELETE'])
def delete_chat(chat_id):
    from models import Chat
    chat = Chat.query.get(chat_id)
    if not chat:
        return jsonify({'error': 'Chat not found'}), 404
    Message.query.filter_by(chat_id=chat_id).delete()
    db.session.delete(chat)
    db.session.commit()
    return jsonify({'success': True})

if __name__ == '__main__':
    app.run(debug=True, port=5000) 