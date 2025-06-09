from flask import Flask, request, jsonify, session
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
import os
from datetime import datetime
import uuid
from dotenv import load_dotenv
from langgraph.prebuilt import create_react_agent
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from langchain.output_parsers import PydanticOutputParser
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain
from pydantic import BaseModel
from typing import List, Optional

import asyncio
import logging
import json
import re
import traceback
import requests

# Databricks LLM integration
from databricks_langchain import ChatDatabricks
from databricks.sdk import WorkspaceClient
from llama_index.llms.databricks import Databricks
import mlflow

# Load environment variables from .env file
load_dotenv()
mlflow.langchain.autolog()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'your-secret-key-here')  # Change this to a secure secret key

# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///naviable.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Enable CORS for all routes (for Next.js frontend)
CORS(app, supports_credentials=True)

# Initialize Databricks LLM client
llm = ChatDatabricks(endpoint="databricks-meta-llama-3-3-70b-instruct")

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("naviable-agents")

# Airport code to city name mapping
AIRPORT_TO_CITY = {
    'SFO': 'San Francisco',
    'LAX': 'Los Angeles',
    'JFK': 'New York',
    'LGA': 'New York',
    'EWR': 'Newark',
    'ORD': 'Chicago',
    'DFW': 'Dallas',
    'ATL': 'Atlanta',
    'MIA': 'Miami',
    'SEA': 'Seattle',
    'DEN': 'Denver',
    'LAS': 'Las Vegas',
    'PHX': 'Phoenix',
    'BOS': 'Boston',
    'IAD': 'Washington',
    'DCA': 'Washington',
    'SJC': 'San Jose',
    'OAK': 'Oakland',
    'PDX': 'Portland',
    'SAN': 'San Diego'
}

def get_city_name(location):
    """Convert airport code or location string to city name."""
    location = location.upper().strip()
    # If it's an airport code, return the city name
    if location in AIRPORT_TO_CITY:
        return AIRPORT_TO_CITY[location]
    # If it's already a city name or not recognized, return as is
    return location

# Database Models
class User(db.Model):
    id = db.Column(db.String(36), primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    chats = db.relationship('Chat', backref='user', lazy=True)

class Chat(db.Model):
    id = db.Column(db.String(36), primary_key=True)
    user_id = db.Column(db.String(36), db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(255), default="New Chat")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    messages = db.relationship('Message', backref='chat', lazy=True, cascade='all, delete-orphan')

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    chat_id = db.Column(db.String(36), db.ForeignKey('chat.id'), nullable=False)
    role = db.Column(db.String(10), nullable=False)  # 'user' or 'assistant'
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class FlightOption(BaseModel):
    airline: str
    price: str
    dates: str
    link: str
    accessibility: Optional[str] = None

class FlightWeatherSummary(BaseModel):
    weather: str
    flights: List[FlightOption]

# Create database tables
with app.app_context():
    db.create_all()

# In-memory storage for chat sessions (in production, use a database)
chat_sessions = {}

# Async setup for tools and agents
async def setup_agents():
    client = MultiServerMCPClient({
        "nimble": {
            "url": "https://mcp.nimbleway.com/sse",
            "transport": "sse",
            "headers": {
                "Authorization": f"Bearer {os.getenv('NIMBLE_API_KEY')}"
            }
        }
    })
    tools = await client.get_tools()
    
    # Add city name agent
    city_name_agent = create_react_agent(llm, tools, prompt="""
        You are a city name resolution agent. Your job is to convert airport codes, abbreviations, or partial city names into their full, proper city names.
        
        Examples:
        - "SFO" -> "San Francisco"
        - "LAX" -> "Los Angeles"
        - "NYC" -> "New York"
        - "CHI" -> "Chicago"
        - "SF" -> "San Francisco"
        - "LA" -> "Los Angeles"
        
        Rules:
        1. Always return the full, proper city name
        2. If the input is already a full city name, return it as is
        3. If you're unsure, return the most likely full city name
        4. Handle common abbreviations and airport codes
        5. Return only the city name, no explanations or additional text
        
        Your response should be just the full city name, nothing else.
    """)

    flight_agent = create_react_agent(llm, tools, prompt="""
        You are a flight agent. You are responsible for finding the best flights for the accessible or disable person. 
        
        When handling flight requests:
        1. Always ask for specific details if not provided:
        - Departure city/airport
        - Destination city/airport
        - Preferred dates
        - Any accessibility requirements
        - Budget constraints
        
        2. Use the flight search tools to find suitable options
        
        3. Format the response as a clear markdown table with:
        - Airline name
        - Flight price
        - Travel dates
        - Direct booking link
        
        4. For each flight option, include:
        - Accessibility features available
        - Special assistance services
        - Baggage allowance
        - Cancellation policy
        
        5. Sort results by:
        - Best accessibility features first
        - Price (lowest to highest)
        - Duration (shortest first)
        
        6. Always verify:
        - Wheelchair accessibility
        - Special assistance availability
        - Medical equipment transport policies
   
        7. Format all responses in markdown for proper HTML rendering:
        - Use markdown tables for structured data
        - Use bullet points for lists
        - Use bold text for important information
        - Use code blocks for technical details
        - Use horizontal rules to separate sections
        - Ensure all links are properly formatted as markdown links
        
        8. For accessibility information, use:
        - ✅ for available features
        - ❌ for unavailable features
        - ℹ️ for additional information

        9. When you need to ask the user for more information, always phrase your question in clear, conversational markdown. Do not include raw JSON, function calls, or code blocks in your message. For example, instead of showing a function call, simply ask: "Could you please provide your preferred travel dates and any accessibility requirements?"
        
        10. When presenting flight options, always include the current weather for both the departure and destination cities at the top of your response, formatted in markdown. Use the weather agent to fetch this information.
    """)
    parser = PydanticOutputParser(pydantic_object=FlightWeatherSummary)
    summary_prompt = PromptTemplate(
        template=(
            "Given the following weather and flight data, format it as a markdown summary for a travel assistant UI.\n"
            "Weather:\n{weather}\n\nFlights:\n{flights}\n\n"
            "Respond in this JSON format:\n{format_instructions}"
        ),
        input_variables=["weather", "flights"],
        partial_variables={"format_instructions": parser.get_format_instructions()},
    )
    summary_chain = LLMChain(llm=llm, prompt=summary_prompt, output_parser=parser)
    # Supervisor agent: routes queries to appropriate agents
    async def supervisor_agent(messages):
        user_content = messages[-1]['content'].lower()
        logger.info(f"Supervisor agent received message: {user_content}")
        if 'flight' in user_content or ('from' in user_content and 'to' in user_content):
            logger.info("Invoking flight_agent for this query.")
            # Try to extract source and destination from the message
            import re
            src, dst = None, None
            match = re.search(r'from ([\w\s]+) to ([\w\s]+)', user_content)
            if match:
                src, dst = match.group(1).strip(), match.group(2).strip()
            else:
                # Try to find two city/airport names
                tokens = user_content.split()
                if 'from' in tokens and 'to' in tokens:
                    src = tokens[tokens.index('from')+1]
                    dst = tokens[tokens.index('to')+1]
            weather_md = ''
            if src and dst:
                # Use city_name_agent to get full city names
                src_response = await city_name_agent.ainvoke({"messages": [{"role": "user", "content": f"Convert this to a full city name: {src}"}]})
                dst_response = await city_name_agent.ainvoke({"messages": [{"role": "user", "content": f"Convert this to a full city name: {dst}"}]})
                
                # Extract city names from responses
                src_city = src_response.get('content', src).strip()
                dst_city = dst_response.get('content', dst).strip()
                
                logger.info(f"Converted locations - From: {src}->{src_city}, To: {dst}->{dst_city}")
                weather_md = await weather_agent(src_city, dst_city)
            flight_response = await flight_agent.ainvoke({"messages": messages})
            # If flight_response is a dict, add weather info to content
            if isinstance(flight_response, dict):
                if 'content' in flight_response:
                    # Use summary_chain to get structured output
                    summary_obj = summary_chain.run({
                        "weather": weather_md,
                        "flights": flight_response['content']
                    })
                    # Render as markdown for the UI
                    formatted = f"**Weather**\n{summary_obj.weather}\n\n**Flights**\n"
                    if summary_obj.flights:
                        formatted += "| Airline | Price | Dates | Link | Accessibility |\n|--------|-------|-------|------|---------------|\n"
                        for f in summary_obj.flights:
                            formatted += f"| {f.airline} | {f.price} | {f.dates} | [link]({f.link}) | {f.accessibility or ''} |\n"
                    else:
                        formatted += "No flights found."
                    return formatted
                else:
                    flight_response['content'] = weather_md
            elif hasattr(flight_response, 'content'):
                result = summary_chain.run({
                    "weather": weather_md,
                    "flights": flight_response.content
                })
                formatted = f"**Weather**\n{result.weather}\n\n**Flights**\n"
                if result.flights:
                    formatted += "| Airline | Price | Dates | Link | Accessibility |\n|--------|-------|-------|------|---------------|\n"
                    for f in result.flights:
                        formatted += f"| {f.airline} | {f.price} | {f.dates} | [link]({f.link}) | {f.accessibility or ''} |\n"
                else:
                    formatted += "No flights found."
                flight_response.content = formatted
            return flight_response
        else:
            logger.info("Invoking base LLM for this query.")
            return await llm.ainvoke(messages)
        
    async def weather_agent(source, destination):
        """Fetch weather for source and destination and return markdown."""
        loop = asyncio.get_event_loop()
        src_weather = await loop.run_in_executor(None, get_weather, source)
        dst_weather = await loop.run_in_executor(None, get_weather, destination)
        return f"\n---\n{src_weather}\n\n{dst_weather}\n---\n"

    return supervisor_agent

# Global supervisor_agent instance (set at startup)
supervisor_agent = asyncio.run(setup_agents())

def extract_flight_table_from_tool_message(tool_message_content):

    print('-->>>>>', tool_message_content)

    try:
        # Find the JSON part in the tool message
        match = re.search(r'({[\s\S]*})', tool_message_content)
        if not match:
            return None
        data = json.loads(match.group(1))
        results = data.get("results", [])
        if not results:
            return None
        # Build markdown table
        table = "| Airline/Title | Price | Dates | Link |\n|---|---|---|---|\n"
        for r in results[:5]:  # Show top 5
            meta = r.get("metadata", {})
            title = meta.get("title", "")
            snippet = meta.get("snippet", "")
            url = meta.get("url", "")
            # Try to extract price and dates from snippet/title
            price_match = re.search(r"\\$\\d+", snippet)
            price = price_match.group(0) if price_match else ""
            dates_match = re.search(r"\b\w+ \d+, \w+ \d+\b", snippet)
            dates = dates_match.group(0) if dates_match else ""
            airline = title.split(":")[0] if ":" in title else title
            table += f"| {airline} | {price} | {dates} | [Link]({url}) |\n"
        return table
    except Exception as e:
        return None

def format_flight_data(agent_response):
    """Format flight data from agent response (with ToolMessage) into a markdown table."""
    # Find ToolMessage with flight info
    messages = agent_response.get('messages', [])
    tool_message = None
    for msg in messages:
        # ToolMessage may be a class or dict; handle both
        if hasattr(msg, 'name') and msg.name == 'nimble_deep_web_search':
            tool_message = msg
            break
        elif isinstance(msg, dict) and msg.get('name') == 'nimble_deep_web_search':
            tool_message = msg
            break
    if not tool_message:
        return "No flight data found."
    # Parse the JSON content
    try:
        content = tool_message.content if hasattr(tool_message, 'content') else tool_message.get('content', '{}')
        data = json.loads(content)
        results = data.get('results', [])
        if not results:
            return "No flight results found."
        # Build markdown table
        table = "| Title | Snippet | Price | Link |\n"
        table += "|-------|---------|-------|------|\n"
        for r in results:
            meta = r.get('metadata', {})
            title = meta.get('title', 'N/A')
            snippet = meta.get('snippet', 'N/A')
            # Try to extract price from snippet (e.g., $179)
            price_match = re.search(r'\$\d+', snippet)
            price = price_match.group(0) if price_match else 'N/A'
            url = meta.get('url', '')
            url_md = f"[{url.split('//')[-1].split('/')[0]}]({url})" if url else 'N/A'
            table += f"| {title} | {snippet[:60]}... | {price} | {url_md} |\n"
        return table
    except Exception as e:
        return f"Error parsing flight data: {e}"

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
            
        # Get or create user
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
        
        # Get or create chat
        current_chat_id = session.get('current_chat_id')
        if not current_chat_id:
            current_chat_id = str(uuid.uuid4())
            session['current_chat_id'] = current_chat_id
            chat = Chat(id=current_chat_id, user_id=user_id)
            db.session.add(chat)
            db.session.commit()
        else:
            chat = Chat.query.get(current_chat_id)
            if not chat:
                # Create a new chat if the session is out of sync with the DB
                chat = Chat(id=current_chat_id, user_id=user_id)
                db.session.add(chat)
                db.session.commit()
        
        # Add user message
        user_message = Message(
            chat_id=current_chat_id,
            role='user',
            content=message
        )
        db.session.add(user_message)
        
        # Prepare messages for agent
        api_messages = [{'role': msg.role, 'content': msg.content} for msg in chat.messages]
        api_messages.append({'role': 'user', 'content': message})
        # Get response from supervisor agent
        response = asyncio.run(supervisor_agent(api_messages))
        
        # Format the response for the UI
        if isinstance(response, dict) and response.get('agent') == 'flight_agent':
            formatted_response = response['content']
        elif hasattr(response, 'content'):
            formatted_response = str(response.content)
        else:
            formatted_response = str(response)
        
        # Add assistant message
        assistant_message = Message(
            chat_id=current_chat_id,
            role='assistant',
            content=formatted_response
        )
        db.session.add(assistant_message)
        db.session.commit()
        
        return jsonify({
            'response': formatted_response,
            'chat_id': current_chat_id
        })
        
    except Exception as e:
        tb = traceback.format_exc()
        app.logger.error(f"Error in chat endpoint: {str(e)}\n{tb}")
        return jsonify({'error': str(e), 'traceback': tb}), 500

@app.route('/clear', methods=['POST'])
def clear_chat():
    current_chat_id = session.get('current_chat_id')
    if current_chat_id:
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
    """Get all chat sessions for the user"""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'chats': []})
    
    chats = Chat.query.filter_by(user_id=user_id).order_by(Chat.updated_at.desc()).all()
    
    user_chats = [{
        'id': chat.id,
        'title': chat.title,
        'created_at': chat.created_at.isoformat(),
        'updated_at': chat.updated_at.isoformat(),
        'message_count': len(chat.messages)
    } for chat in chats]
    
    return jsonify({'chats': user_chats})

@app.route('/chats', methods=['POST'])
def create_new_chat():
    """Create a new chat session"""
    user_id = session.get('user_id')
    if not user_id:
        user_id = str(uuid.uuid4())
        user = User(id=user_id)
        db.session.add(user)
        db.session.commit()
        session['user_id'] = user_id
    
    chat_id = str(uuid.uuid4())
    chat = Chat(id=chat_id, user_id=user_id)
    db.session.add(chat)
    db.session.commit()
    
    # Switch to the new chat
    session['current_chat_id'] = chat_id
    return jsonify({'chat_id': chat_id, 'status': 'created'})

@app.route('/chats/<chat_id>', methods=['GET'])
def get_chat(chat_id):
    """Get a specific chat session"""
    chat = Chat.query.get(chat_id)
    if not chat:
        return jsonify({'error': 'Chat not found'}), 404
    
    # Check if this chat belongs to the current user
    if chat.user_id != session.get('user_id'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    # Switch to this chat
    session['current_chat_id'] = chat_id
    
    messages = [{
        'role': msg.role,
        'content': msg.content,
        'timestamp': msg.timestamp.strftime('%H:%M')
    } for msg in chat.messages]
    
    return jsonify({'messages': messages, 'chat_id': chat_id})

@app.route('/chats/<chat_id>', methods=['DELETE'])
def delete_chat(chat_id):
    """Delete a chat session"""
    chat = Chat.query.get(chat_id)
    if not chat:
        return jsonify({'error': 'Chat not found'}), 404
    
    # Check if this chat belongs to the current user
    if chat.user_id != session.get('user_id'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    db.session.delete(chat)
    db.session.commit()
    
    # If this was the current chat, clear the session
    if session.get('current_chat_id') == chat_id:
        session['current_chat_id'] = None
    
    return jsonify({'success': True})

OPENWEATHER_API_KEY = os.getenv('OPENWEATHER_API_KEY')

def get_weather(city):
    """Fetch weather for a city using OpenWeatherMap API and return a markdown summary."""
    if not OPENWEATHER_API_KEY:
        return f"Weather API key not set."
    url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={OPENWEATHER_API_KEY}&units=metric"
    try:
        resp = requests.get(url, timeout=5)
        if resp.status_code != 200:
            return f"Weather for {city}: Not found."
        data = resp.json()
        desc = data['weather'][0]['description'].capitalize()
        temp = data['main']['temp']
        feels = data['main']['feels_like']
        humidity = data['main']['humidity']
        wind = data['wind']['speed']
        return f"**Weather in {city.title()}**: {desc}, {temp}°C (feels like {feels}°C), Humidity: {humidity}%, Wind: {wind} m/s"
    except Exception as e:
        return f"Weather for {city}: Error fetching data."

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8000) 