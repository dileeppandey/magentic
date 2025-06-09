'use client';

import { useState, useEffect, useRef } from 'react';
import { config } from './config';
import ReactMarkdown from 'react-markdown';
import rehypeRaw from 'rehype-raw';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  timestamp?: string;
}

interface Chat {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputMessage, setInputMessage] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [chats, setChats] = useState<Chat[]>([]);
  const [currentChatId, setCurrentChatId] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    // Load chat history and chats list on component mount
    loadChatHistory();
    loadChats();
  }, []);

  const loadChatHistory = async () => {
    try {
      const response = await fetch(`${config.apiUrl}/history`, {
        credentials: 'include',
      });
      const data = await response.json();
      if (data.messages) {
        setMessages(data.messages);
      }
    } catch (error) {
      console.error('Error loading chat history:', error);
    }
  };

  const loadChats = async () => {
    try {
      const response = await fetch(`${config.apiUrl}/chats`, {
        credentials: 'include',
      });
      const data = await response.json();
      if (data.chats) {
        setChats(data.chats);
      }
    } catch (error) {
      console.error('Error loading chats:', error);
    }
  };

  const createNewChat = async () => {
    try {
      const response = await fetch(`${config.apiUrl}/chats`, {
        method: 'POST',
        credentials: 'include',
      });
      const data = await response.json();
      if (data.chat_id) {
        setCurrentChatId(data.chat_id);
        setMessages([]);
        setError(null);
        await loadChats(); // Refresh the chats list
      }
    } catch (error) {
      console.error('Error creating new chat:', error);
    }
  };

  const selectChat = async (chatId: string) => {
    try {
      const response = await fetch(`${config.apiUrl}/chats/${chatId}`, {
        credentials: 'include',
      });
      const data = await response.json();
      if (data.messages) {
        setCurrentChatId(chatId);
        setMessages(data.messages);
        setError(null);
      }
    } catch (error) {
      console.error('Error selecting chat:', error);
    }
  };

  const deleteChat = async (chatId: string) => {
    if (!window.confirm('Are you sure you want to delete this chat?')) {
      return;
    }
    
    try {
      const response = await fetch(`${config.apiUrl}/chats/${chatId}`, {
        method: 'DELETE',
        credentials: 'include',
      });
      
      if (response.ok) {
        await loadChats(); // Refresh the chats list
        
        // If this was the current chat, clear it
        if (currentChatId === chatId) {
          setCurrentChatId(null);
          setMessages([]);
        }
      }
    } catch (error) {
      console.error('Error deleting chat:', error);
    }
  };

  const sendMessage = async () => {
    if (!inputMessage.trim() || isLoading) return;

    const userMessage: Message = {
      role: 'user',
      content: inputMessage,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    };

    setMessages(prev => [...prev, userMessage]);
    setInputMessage('');
    setIsLoading(true);
    setError(null);

    try {
      const response = await fetch(`${config.apiUrl}/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify({ message: inputMessage }),
      });

      const data = await response.json();

      if (data.error) {
        setError(data.error);
      } else {
        const assistantMessage: Message = {
          role: 'assistant',
          content: data.response,
          timestamp: data.timestamp
        };
        setMessages(prev => [...prev, assistantMessage]);
        
        // Refresh chats list to update the title and timestamp
        await loadChats();
      }
    } catch (error) {
      setError('Network error. Please try again.');
      console.error('Error:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const clearChat = async () => {
    if (window.confirm('Are you sure you want to clear the current chat?')) {
      try {
        const response = await fetch(`${config.apiUrl}/clear`, {
          method: 'POST',
          credentials: 'include',
        });
        
        if (response.ok) {
          setMessages([]);
          setError(null);
          await loadChats(); // Refresh the chats list
        }
      } catch (error) {
        console.error('Error clearing chat:', error);
      }
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  return (
    <div className="flex h-screen bg-gray-50">
      {/* Sidebar */}
      <div className={`${sidebarOpen ? 'w-80' : 'w-16'} h-screen flex flex-col bg-white border-r border-gray-200 shadow-sm`}>
        {/* Sidebar Header */}
        <div className="p-4 border-b border-gray-200">
          <div className="flex items-center justify-between">
            {sidebarOpen && (
              <div className="flex items-center space-x-3">
                <div className="w-8 h-8 bg-blue-600 rounded-full flex items-center justify-center">
                  <svg className="w-5 h-5 text-white" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M18 10c0 3.866-3.582 7-8 7a8.841 8.841 0 01-4.083-.98L2 17l1.338-3.123C2.493 12.767 2 11.434 2 10c0-3.866 3.582-7 8-7s8 3.134 8 7zM7 9H5v2h2V9zm8 0h-2v2h2V9zM9 9h2v2H9V9z" clipRule="evenodd" />
                  </svg>
                </div>
                <h1 className="text-lg font-semibold text-gray-900">NaviAble</h1>
              </div>
            )}
            <button
              onClick={() => setSidebarOpen(!sidebarOpen)}
              className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
              title={sidebarOpen ? 'Collapse sidebar' : 'Expand sidebar'}
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={sidebarOpen ? "M11 19l-7-7 7-7m8 14l-7-7 7-7" : "M13 5l7 7-7 7M5 5l7 7-7 7"} />
              </svg>
            </button>
          </div>
        </div>

        {/* New Chat Button */}
        {sidebarOpen && (
          <div className="p-4">
            <button
              onClick={createNewChat}
              className="w-full px-8 py-4 bg-blue-600 hover:bg-blue-700 text-white rounded-full font-semibold text-lg flex items-center justify-center gap-3 transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 shadow-md"
            >
              <svg className="w-6 h-12" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              New Chat
            </button>
          </div>
        )}

        {/* Chat List */}
        <div className="flex-1 overflow-y-auto">
          {sidebarOpen ? (
            <div className="px-2 py-2 space-y-1">
              {chats.length === 0 ? (
                <div className="text-center py-8 px-4">
                  <div className="text-gray-500 text-sm">No chats yet</div>
                  <div className="text-gray-400 text-xs mt-1">Start a new conversation!</div>
                </div>
              ) : (
                chats.map((chat) => (
                  <div
                    key={chat.id}
                    className={`group relative flex items-center p-4 rounded-xl cursor-pointer hover:bg-gray-100 transition-all duration-200 ${
                      currentChatId === chat.id ? 'bg-blue-50 border-2 border-blue-200 shadow-sm' : 'border-2 border-transparent'
                    }`}
                    onClick={() => selectChat(chat.id)}
                  >
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-semibold text-gray-900 truncate">
                        {chat.title}
                      </p>
                      <p className="text-xs text-gray-500 mt-1">
                        {chat.message_count} messages • {new Date(chat.updated_at).toLocaleDateString()}
                      </p>
                    </div>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        deleteChat(chat.id);
                      }}
                      className="opacity-0 group-hover:opacity-100 p-2 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-all duration-200"
                      title="Delete chat"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                      </svg>
                    </button>
                  </div>
                ))
              )}
            </div>
          ) : (
            <div className="p-3">
              <button
                onClick={createNewChat}
                className="w-full p-4 text-blue-600 hover:bg-blue-50 rounded-xl transition-all duration-200 shadow-sm hover:shadow-md"
                title="New Chat"
              >
                <svg className="w-6 h-6 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                </svg>
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 flex flex-col h-screen">
        {/* Header */}
        <div className="bg-white shadow-sm border-b border-gray-200 px-6 py-4">
          <div className="max-w-4xl mx-auto flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <h2 className="text-lg font-semibold text-gray-900">
                {messages.length > 0 ? (chats.find(c => c.id === currentChatId)?.title || 'Current Chat') : 'Welcome to NaviAble'}
              </h2>
            </div>
            <div className="flex items-center space-x-3">
              {messages.length > 0 && (
                <button
                  onClick={clearChat}
                  className="inline-flex items-center px-5 py-3 bg-red-50 hover:bg-red-100 text-red-700 text-sm font-semibold rounded-xl border border-red-200 transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2 shadow-sm hover:shadow-md"
                >
                  <svg className="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                  </svg>
                  Clear Chat
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Chat Container */}
        <div className="flex-1 flex flex-col min-h-0">
          <div className="flex-1 overflow-y-auto">
            <div className="max-w-4xl mx-auto px-6 py-6">
              {/* Welcome Message */}
              {messages.length === 0 && (
                <div className="flex items-center justify-center h-full min-h-96">
                  <div className="text-center max-w-md">
                    <div className="w-16 h-16 bg-blue-100 rounded-full flex items-center justify-center mx-auto mb-4">
                      <svg className="w-8 h-8 text-blue-600" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M18 10c0 3.866-3.582 7-8 7a8.841 8.841 0 01-4.083-.98L2 17l1.338-3.123C2.493 12.767 2 11.434 2 10c0-3.866 3.582-7 8-7s8 3.134 8 7zM7 9H5v2h2V9zm8 0h-2v2h2V9zM9 9h2v2H9V9z" clipRule="evenodd" />
                      </svg>
                    </div>
                    <h2 className="text-2xl font-semibold text-gray-900 mb-3">Welcome to NaviAble</h2>
                    <p className="text-gray-600 mb-6">Your intelligent navigation assistant. Start a conversation by typing a message below, and I'll help guide you through any questions or tasks you might have.</p>
                    <button
                      onClick={createNewChat}
                      className="inline-flex items-center px-8 py-4 bg-blue-600 hover:bg-blue-700 text-white rounded-xl font-semibold text-lg transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 shadow-lg hover:shadow-xl transform hover:scale-105"
                    >
                      <svg className="w-6 h-6 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                      </svg>
                      Start New Chat
                    </button>
                  </div>
                </div>
              )}

              {/* Messages */}
              {messages.length > 0 && (
                <div className="space-y-6">
                  {messages.map((message, index) => (
                    <div
                      key={index}
                      className={`flex items-start gap-4 ${
                        message.role === 'user' ? 'flex-row-reverse' : ''
                      }`}
                    >
                      {/* Avatar */}
                      <div className="flex-shrink-0">
                        <div
                          className={`w-10 h-10 rounded-full flex items-center justify-center shadow-md ${
                            message.role === 'user'
                              ? 'bg-gradient-to-br from-blue-500 to-blue-600 text-white'
                              : 'bg-gradient-to-br from-gray-100 to-gray-200 text-gray-700 border border-gray-300'
                          }`}
                        >
                          {message.role === 'user' ? (
                            <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                              <path fillRule="evenodd" d="M10 9a3 3 0 100-6 3 3 0 000 6zm-7 9a7 7 0 1114 0H3z" clipRule="evenodd" />
                            </svg>
                          ) : (
                            <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                              <path fillRule="evenodd" d="M12.316 3.051a1 1 0 01.633 1.265l-4 12a1 1 0 11-1.898-.632l4-12a1 1 0 011.265-.633zM5.707 6.293a1 1 0 010 1.414L3.414 10l2.293 2.293a1 1 0 11-1.414 1.414l-3-3a1 1 0 010-1.414l3-3a1 1 0 011.414 0zm8.586 0a1 1 0 011.414 0l3 3a1 1 0 010 1.414l-3 3a1 1 0 11-1.414-1.414L16.586 10l-2.293-2.293a1 1 0 010-1.414z" clipRule="evenodd" />
                            </svg>
                          )}
                        </div>
                      </div>

                      {/* Message Content */}
                      <div className={`max-w-[75%] ${message.role === 'user' ? 'text-right' : ''}`}>
                        <div
                          className={`px-6 py-5 rounded-2xl shadow-sm border ${
                            message.role === 'user'
                              ? 'bg-blue-600 text-white border-blue-600 rounded-br-md'
                              : 'bg-white text-gray-900 border-gray-200 rounded-bl-md'
                          }`}
                        >
                          {message.role === 'assistant' ? (
                            <div className="prose max-w-none" style={{ padding: '16px' }}>
                              <ReactMarkdown rehypePlugins={[rehypeRaw]} components={{
                                iframe: ({node, ...props}) => (
                                  <iframe {...props} style={{ maxWidth: '100%', borderRadius: '12px', margin: '12px 0' }} />
                                ),
                                img: ({node, ...props}) => (
                                  <img {...props} style={{ maxWidth: '100%', borderRadius: '12px', margin: '12px 0' }} />
                                )
                              }}>
                                {message.content}
                              </ReactMarkdown>
                            </div>
                          ) : (
                            <p className="whitespace-pre-wrap leading-relaxed text-base" style={{ padding: '16px' }}>{message.content}</p>
                          )}
                        </div>
                        {message.timestamp && (
                          <p className={`text-xs mt-2 px-1 ${
                            message.role === 'user' ? 'text-gray-500' : 'text-gray-500'
                          }`}>
                            {message.timestamp}
                          </p>
                        )}
                      </div>
                    </div>
                  ))}

                  {/* Loading Message */}
                  {isLoading && (
                    <div className="flex items-start gap-4">
                      <div className="flex-shrink-0">
                        <div className="w-10 h-10 rounded-full flex items-center justify-center shadow-md bg-gradient-to-br from-gray-100 to-gray-200 text-gray-700 border border-gray-300">
                          <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                            <path fillRule="evenodd" d="M12.316 3.051a1 1 0 01.633 1.265l-4 12a1 1 0 11-1.898-.632l4-12a1 1 0 011.265-.633zM5.707 6.293a1 1 0 010 1.414L3.414 10l2.293 2.293a1 1 0 11-1.414 1.414l-3-3a1 1 0 010-1.414l3-3a1 1 0 011.414 0zm8.586 0a1 1 0 011.414 0l3 3a1 1 0 010 1.414l-3 3a1 1 0 11-1.414-1.414L16.586 10l-2.293-2.293a1 1 0 010-1.414z" clipRule="evenodd" />
                          </svg>
                        </div>
                      </div>
                      <div className="bg-white text-gray-900 border border-gray-200 rounded-2xl rounded-bl-md px-4 py-3 shadow-sm">
                        <div className="flex items-center gap-3 text-gray-600">
                          <div className="w-6 h-6 border-2 border-blue-200 border-t-blue-600 rounded-full animate-spin"></div>
                          <span className="text-sm">Thinking...</span>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Error Message */}
                  {error && (
                    <div className="bg-red-50 border border-red-200 text-red-800 px-4 py-3 rounded-lg text-center shadow-sm">
                      <div className="flex items-center justify-center gap-2">
                        <svg className="w-5 h-5 text-red-500" fill="currentColor" viewBox="0 0 20 20">
                          <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                        </svg>
                        <span className="text-sm font-medium">{error}</span>
                      </div>
                    </div>
                  )}

                  <div ref={messagesEndRef} />
                </div>
              )}
            </div>
          </div>

          {/* Input Container */}
          <div className="border-t border-gray-200 bg-white shadow-lg px-6 py-8">
            <div className="max-w-3xl mx-auto">
              <div className="relative bg-gray-50 rounded-3xl border border-gray-200 focus-within:ring-2 focus-within:ring-blue-500 focus-within:border-transparent transition-all shadow-sm hover:shadow-md">
                <textarea
                  value={inputMessage}
                  onChange={(e) => setInputMessage(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Type your message to NaviAble..."
                  className="w-full bg-transparent text-gray-900 rounded-3xl px-8 py-5 pr-20 resize-none focus:outline-none placeholder-gray-500 text-base leading-relaxed"
                  rows={1}
                  style={{ minHeight: '120px', maxHeight: '120px', padding: '16px' }}
                  disabled={isLoading}
                />
                <button
                  onClick={sendMessage}
                  disabled={!inputMessage.trim() || isLoading}
                  className="absolute right-3 top-1/2 transform -translate-y-1/2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed text-white p-3 rounded-2xl transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 shadow-md hover:shadow-lg"
                >
                  <svg
                    width="20"
                    height="20"
                    viewBox="0 0 24 24"
                    fill="currentColor"
                    className={isLoading ? 'animate-pulse' : ''}
                  >
                    <path d="M2 21l21-9L2 3v7l15 2-15 2v7z" />
                  </svg>
                </button>
              </div>
              <p className="text-sm text-gray-500 mt-3 text-center">
                Press Enter to send • Shift + Enter for new line
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
