# NaviAble

Your intelligent navigation assistant - A modern, responsive AI-powered application built with **Next.js + TypeScript + Tailwind CSS** frontend and **Python Flask** backend API.

## 🏗️ Architecture

- **Frontend**: Next.js 15 with TypeScript and Tailwind CSS
- **Backend**: Flask API with OpenAI integration
- **Styling**: Tailwind CSS with modern dark theme
- **Communication**: RESTful API with CORS support

## ✨ Features

- 🚀 **Modern React Frontend** - Built with Next.js 15 and TypeScript
- 💬 **Real-time Chat Interface** - Interactive chat with AI assistant
- 🎨 **Tailwind CSS Styling** - Modern, responsive dark theme design
- 📱 **Fully Responsive** - Perfect on desktop, tablet, and mobile
- ⚡ **Loading States & Animations** - Smooth user experience
- 🔄 **Session Management** - Persistent chat history
- ⌨️ **Keyboard Shortcuts** - Send with Enter, newline with Shift+Enter
- 🛡️ **Error Handling** - Comprehensive error states
- 🔌 **API Architecture** - Separate frontend and backend

## 📋 Prerequisites

- **Node.js** 18+ 
- **Python** 3.7+
- **OpenAI API key**

## 🚀 Quick Start

### Option 1: Automated Setup
```bash
# Install all dependencies
npm run install-all

# Set your OpenAI API key
export OPENAI_API_KEY=your_api_key_here

# Start both frontend and backend
npm run dev
```

### Option 2: Manual Setup

1. **Backend Setup:**
   ```bash
   # Create virtual environment
   python3 -m venv venv
   source venv/bin/activate
   
   # Install Python dependencies
   pip install -r requirements.txt
   ```

2. **Frontend Setup:**
   ```bash
   # Install Node.js dependencies
   cd frontend
   npm install
   cd ..
   ```

3. **Environment Variables:**
   ```bash
   # Set your OpenAI API key
   export OPENAI_API_KEY=your_api_key_here
   ```

4. **Start Servers:**
   ```bash
   # Terminal 1: Start Flask backend (port 8000)
   source venv/bin/activate && python app.py
   
   # Terminal 2: Start Next.js frontend (port 3000)
   cd frontend && npm run dev
   ```

5. **Access the Application:**
   ```
   Frontend: http://localhost:3000 (or 3001 if 3000 is in use)
   Backend API: http://localhost:8000
   ```

> **💡 Tip**: The frontend automatically connects to the backend using the configuration in `frontend/src/app/config.ts`

## Usage

1. Type your message in the input field at the bottom
2. Press Enter or click the send button to send your message
3. Wait for the AI to respond (you'll see a loading indicator)
4. Continue the conversation - the AI remembers the context
5. Use the "Clear Chat" button to start a new conversation

## Configuration

### OpenAI API Settings

You can modify the AI behavior by editing the OpenAI API parameters in `app.py`:

```python
response = openai.ChatCompletion.create(
    model="gpt-3.5-turbo",  # or "gpt-4" for better responses
    messages=api_messages,
    max_tokens=1000,        # Maximum response length
    temperature=0.7         # Creativity (0.0 to 1.0)
)
```

### Server Configuration

By default, the backend API runs on `http://localhost:8000`. You can modify this in the last line of `app.py`:

```python
app.run(debug=True, host='0.0.0.0', port=8000)
```

### Frontend Configuration

The frontend API URL can be configured in `frontend/src/app/config.ts`:

```typescript
export const config = {
  apiUrl: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000',
} as const;
```

## 📁 Project Structure

```
naviable/
│
├── 🔧 Backend (Flask API)
│   ├── app.py             # Flask API server
│   ├── requirements.txt   # Python dependencies
│   └── venv/             # Python virtual environment
│
├── 🎨 Frontend (Next.js)
│   ├── src/
│   │   └── app/
│   │       ├── page.tsx       # Main chat interface
│   │       ├── layout.tsx     # App layout
│   │       └── globals.css    # Global styles
│   ├── package.json      # Node.js dependencies
│   └── tailwind.config.js # Tailwind configuration
│
└── 📝 Project Files
    ├── README.md         # Documentation
    ├── package.json      # Root scripts
    └── .gitignore        # Git ignore rules
```

## Deployment

### Local Development
The app is configured for development by default with `debug=True`.

### Production Deployment
For production:
1. Set `debug=False` in `app.py`
2. Use a production WSGI server like Gunicorn
3. Set up proper environment variables
4. Consider using a reverse proxy like Nginx

Example with Gunicorn:
```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

## API Endpoints

- `GET /` - API status check
- `POST /chat` - Send message to AI
- `POST /clear` - Clear chat history
- `GET /history` - Get chat history

> **Note**: All API endpoints support CORS for cross-origin requests from the Next.js frontend

## Troubleshooting

### Common Issues

1. **"OpenAI API key not configured" error**
   - Make sure you've set the `OPENAI_API_KEY` environment variable
   - Check that your API key is valid and has sufficient credits

2. **"Module not found" errors**
   - Run `pip install -r requirements.txt` to install dependencies

3. **Port already in use**
   - Change the port in `app.py` or kill the process using port 5000

4. **API rate limits**
   - OpenAI has rate limits; wait a moment and try again
   - Consider upgrading your OpenAI plan for higher limits

## Contributing

Feel free to submit issues and pull requests to improve NaviAble!

## License

This project is open source and available under the MIT License. 