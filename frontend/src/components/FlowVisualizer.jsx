import React, { useState, useEffect } from 'react';

// Import icons - you can replace these with any icon library or SVG components
const SendIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <line x1="22" y1="2" x2="11" y2="13"></line>
    <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
  </svg>
);

const SettingsIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="3"></circle>
    <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path>
  </svg>
);

const CloseIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <line x1="18" y1="6" x2="6" y2="18"></line>
    <line x1="6" y1="6" x2="18" y2="18"></line>
  </svg>
);

const FileCodeIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
    <polyline points="14 2 14 8 20 8"></polyline>
    <line x1="8" y1="16" x2="8" y2="16"></line>
    <line x1="12" y1="16" x2="12" y2="16"></line>
    <line x1="16" y1="16" x2="16" y2="16"></line>
  </svg>
);

const DownloadIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
    <polyline points="7 10 12 15 17 10"></polyline>
    <line x1="12" y1="15" x2="12" y2="3"></line>
  </svg>
);

const ChatUI = () => {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [showSettings, setShowSettings] = useState(false);
  const [loading, setLoading] = useState(false);
  const [model, setModel] = useState('anthropic/claude-3.5-sonnet');
  const [generatedFlow, setGeneratedFlow] = useState(null);
  const [showFlowModal, setShowFlowModal] = useState(false);

  // Save/load API key from localStorage
  useEffect(() => {
    const savedApiKey = localStorage.getItem('openrouter_api_key');
    if (savedApiKey) {
      setApiKey(savedApiKey);
    }
    
    const savedModel = localStorage.getItem('openrouter_model');
    if (savedModel) {
      setModel(savedModel);
    }
  }, []);

  const saveSettings = () => {
    localStorage.setItem('openrouter_api_key', apiKey);
    localStorage.setItem('openrouter_model', model);
    setShowSettings(false);
  };

  const sendMessage = async () => {
    if (!input.trim()) return;
    if (!apiKey) {
      setShowSettings(true);
      return;
    }

    // Add user message to chat
    const userMessage = { role: 'user', content: input };
    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setLoading(true);

    try {
      // Call OpenRouter API
      const response = await fetch('https://openrouter.ai/api/v1/chat/completions', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${apiKey}`
        },
        body: JSON.stringify({
          model: model,
          messages: [...messages, userMessage].map(msg => ({
            role: msg.role,
            content: msg.content
          })),
          temperature: 0.7,
          max_tokens: 1024
        })
      });

      if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
      }

      const data = await response.json();
      const aiResponse = { 
        role: 'assistant', 
        content: data.choices[0].message.content 
      };
      
      setMessages(prev => [...prev, aiResponse]);
    } catch (error) {
      console.error('Error sending message:', error);
      setMessages(prev => [...prev, { 
        role: 'system', 
        content: `Error: ${error.message || 'Failed to get a response.'}` 
      }]);
    } finally {
      setLoading(false);
    }
  };

  const generateFlow = async () => {
    if (!input.trim()) return;
    if (!apiKey) {
      setShowSettings(true);
      return;
    }

    setLoading(true);
    try {
      // Add user message to chat
      const userMessage = { 
        role: 'user', 
        content: `Generate a flow for: ${input}` 
      };
      setMessages(prev => [...prev, userMessage]);

      // This would normally call a different endpoint or function
      // For the mock UI, we'll use the chat API with a specific prompt
      const systemPrompt = "You are a specialized AI that creates flow definitions for the FlowForge system. Create a complete YAML flow definition based on the user's request.";
      
      const response = await fetch('https://openrouter.ai/api/v1/chat/completions', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${apiKey}`
        },
        body: JSON.stringify({
          model: model,
          messages: [
            { role: 'system', content: systemPrompt },
            { role: 'user', content: `Create a flow for: ${input}` }
          ],
          temperature: 0.2,
          max_tokens: 2048
        })
      });

      if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
      }

      const data = await response.json();
      const flowYaml = data.choices[0].message.content;
      
      // Extract YAML content (in a real app, you'd use a more robust method)
      let extractedYaml = flowYaml;
      if (flowYaml.includes('```yaml')) {
        extractedYaml = flowYaml.split('```yaml')[1].split('```')[0].trim();
      } else if (flowYaml.includes('```')) {
        for (const block of flowYaml.split('```')) {
          if (block.includes('id:') && block.includes('steps:')) {
            extractedYaml = block.trim();
            break;
          }
        }
      }

      setGeneratedFlow(extractedYaml);
      setShowFlowModal(true);
      
      // Add assistant response to chat
      setMessages(prev => [...prev, { 
        role: 'assistant', 
        content: 'I\'ve generated a flow based on your request. You can view and download it.'
      }]);
      
      setInput('');
    } catch (error) {
      console.error('Error generating flow:', error);
      setMessages(prev => [...prev, { 
        role: 'system', 
        content: `Error generating flow: ${error.message || 'Failed to generate flow.'}` 
      }]);
    } finally {
      setLoading(false);
    }
  };

  const downloadFlow = () => {
    if (!generatedFlow) return;
    
    // Create a blob from the YAML content
    const blob = new Blob([generatedFlow], { type: 'text/yaml' });
    const url = URL.createObjectURL(blob);
    
    // Create a temp link element to trigger download
    const a = document.createElement('a');
    a.href = url;
    a.download = 'flowforge_flow.yaml';
    document.body.appendChild(a);
    a.click();
    
    // Clean up
    URL.revokeObjectURL(url);
    document.body.removeChild(a);
  };

  const availableModels = [
    'anthropic/claude-3.5-sonnet',
    'anthropic/claude-3-opus',
    'anthropic/claude-3-sonnet',
    'anthropic/claude-3-haiku',
    'openai/gpt-4-turbo',
    'openai/gpt-3.5-turbo'
  ];

  // Styles
  const styles = {
    container: {
      display: 'flex',
      flexDirection: 'column',
      height: '100vh',
      backgroundColor: '#f3f4f6'
    },
    header: {
      backgroundColor: '#2563eb',
      color: 'white',
      padding: '1rem',
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'center'
    },
    title: {
      fontSize: '1.25rem',
      fontWeight: 'bold'
    },
    button: {
      padding: '0.5rem',
      borderRadius: '0.25rem',
      cursor: 'pointer'
    },
    settingsButton: {
      backgroundColor: 'transparent',
      color: 'white',
      border: 'none'
    },
    modal: {
      position: 'absolute',
      top: 0,
      left: 0,
      width: '100%',
      height: '100%',
      backgroundColor: 'rgba(0, 0, 0, 0.5)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 10
    },
    modalContent: {
      backgroundColor: 'white',
      padding: '1.5rem',
      borderRadius: '0.5rem',
      width: '24rem',
      boxShadow: '0 10px 15px -3px rgba(0, 0, 0, 0.1)'
    },
    flowModalContent: {
      backgroundColor: 'white',
      padding: '1.5rem',
      borderRadius: '0.5rem',
      width: '75%',
      maxWidth: '48rem',
      boxShadow: '0 10px 15px -3px rgba(0, 0, 0, 0.1)'
    },
    modalHeader: {
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'center',
      marginBottom: '1rem'
    },
    modalTitle: {
      fontSize: '1.25rem',
      fontWeight: '600'
    },
    closeButton: {
      backgroundColor: 'transparent',
      border: 'none',
      color: '#6b7280',
      cursor: 'pointer'
    },
    formGroup: {
      marginBottom: '1rem'
    },
    label: {
      display: 'block',
      color: '#374151',
      marginBottom: '0.5rem'
    },
    input: {
      width: '100%',
      padding: '0.5rem',
      border: '1px solid #d1d5db',
      borderRadius: '0.25rem'
    },
    select: {
      width: '100%',
      padding: '0.5rem',
      border: '1px solid #d1d5db',
      borderRadius: '0.25rem'
    },
    saveButton: {
      width: '100%',
      backgroundColor: '#2563eb',
      color: 'white',
      padding: '0.5rem',
      borderRadius: '0.25rem',
      border: 'none',
      cursor: 'pointer'
    },
    messagesContainer: {
      flex: 1,
      overflowY: 'auto',
      padding: '1rem',
      display: 'flex',
      flexDirection: 'column',
      gap: '1rem'
    },
    messageEmptyState: {
      textAlign: 'center',
      color: '#6b7280',
      marginTop: '2.5rem'
    },
    emptyStateText: {
      fontSize: '1rem'
    },
    emptyStateSubtext: {
      fontSize: '0.875rem',
      marginTop: '0.5rem'
    },
    message: {
      padding: '0.75rem',
      borderRadius: '0.5rem',
      maxWidth: '48rem'
    },
    userMessage: {
      backgroundColor: '#dbeafe',
      marginLeft: 'auto'
    },
    systemMessage: {
      backgroundColor: '#fee2e2'
    },
    assistantMessage: {
      backgroundColor: 'white',
      border: '1px solid #e5e7eb'
    },
    messageHeader: {
      fontSize: '0.875rem',
      fontWeight: '600',
      marginBottom: '0.25rem'
    },
    inputArea: {
      borderTop: '1px solid #e5e7eb',
      padding: '1rem',
      backgroundColor: 'white'
    },
    inputContainer: {
      display: 'flex',
      gap: '0.5rem'
    },
    textInput: {
      flex: 1,
      padding: '0.5rem',
      border: '1px solid #d1d5db',
      borderRadius: '0.25rem'
    },
    actionButton: {
      padding: '0.5rem',
      borderRadius: '0.25rem',
      color: 'white',
      border: 'none',
      cursor: 'pointer'
    },
    generateButton: {
      backgroundColor: '#059669'
    },
    sendButton: {
      backgroundColor: '#2563eb'
    },
    disabledButton: {
      backgroundColor: '#9ca3af',
      cursor: 'not-allowed'
    },
    codePreview: {
      marginBottom: '1rem',
      backgroundColor: '#1f2937',
      color: '#e5e7eb',
      padding: '1rem',
      borderRadius: '0.25rem',
      overflowY: 'auto',
      height: '24rem'
    },
    pre: {
      margin: 0,
      fontFamily: 'monospace'
    },
    downloadButton: {
      backgroundColor: '#2563eb',
      color: 'white',
      padding: '0.5rem',
      borderRadius: '0.25rem',
      border: 'none',
      cursor: 'pointer',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      gap: '0.5rem'
    }
  };

  return (
    <div style={styles.container}>
      {/* Header */}
      <div style={styles.header}>
        <h1 style={styles.title}>FlowForge Chat</h1>
        <button 
          onClick={() => setShowSettings(!showSettings)}
          style={{...styles.button, ...styles.settingsButton}}
        >
          <SettingsIcon />
        </button>
      </div>

      {/* Settings Modal */}
      {showSettings && (
        <div style={styles.modal}>
          <div style={styles.modalContent}>
            <div style={styles.modalHeader}>
              <h2 style={styles.modalTitle}>Settings</h2>
              <button onClick={() => setShowSettings(false)} style={styles.closeButton}>
                <CloseIcon />
              </button>
            </div>
            <div style={styles.formGroup}>
              <label style={styles.label} htmlFor="apiKey">
                OpenRouter API Key
              </label>
              <input
                id="apiKey"
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                style={styles.input}
                placeholder="Enter your API key"
              />
            </div>
            <div style={styles.formGroup}>
              <label style={styles.label} htmlFor="model">
                AI Model
              </label>
              <select
                id="model"
                value={model}
                onChange={(e) => setModel(e.target.value)}
                style={styles.select}
              >
                {availableModels.map((m) => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </select>
            </div>
            <button
              onClick={saveSettings}
              style={styles.saveButton}
            >
              Save Settings
            </button>
          </div>
        </div>
      )}

      {/* Flow Modal */}
      {showFlowModal && (
        <div style={styles.modal}>
          <div style={styles.flowModalContent}>
            <div style={styles.modalHeader}>
              <h2 style={styles.modalTitle}>Generated Flow</h2>
              <button onClick={() => setShowFlowModal(false)} style={styles.closeButton}>
                <CloseIcon />
              </button>
            </div>
            <div style={styles.codePreview}>
              <pre style={styles.pre}>{generatedFlow}</pre>
            </div>
            <button
              onClick={downloadFlow}
              style={styles.downloadButton}
            >
              <DownloadIcon /> Download YAML
            </button>
          </div>
        </div>
      )}

      {/* Messages Container */}
      <div style={styles.messagesContainer}>
        {messages.length === 0 && (
          <div style={styles.messageEmptyState}>
            <p style={styles.emptyStateText}>Start a conversation with FlowForge AI</p>
            <p style={styles.emptyStateSubtext}>You can chat normally or generate flows from natural language requests</p>
          </div>
        )}
        
        {messages.map((msg, index) => {
          let messageStyle = {...styles.message};
          
          if (msg.role === 'user') {
            messageStyle = {...messageStyle, ...styles.userMessage};
          } else if (msg.role === 'system') {
            messageStyle = {...messageStyle, ...styles.systemMessage};
          } else {
            messageStyle = {...messageStyle, ...styles.assistantMessage};
          }
          
          return (
            <div key={index} style={messageStyle}>
              <p style={styles.messageHeader}>
                {msg.role === 'user' ? 'You' : msg.role === 'assistant' ? 'AI' : 'System'}
              </p>
              <p>{msg.content}</p>
            </div>
          );
        })}
        
        {loading && (
          <div style={{...styles.message, ...styles.assistantMessage}}>
            <p style={styles.messageHeader}>AI</p>
            <p>Thinking...</p>
          </div>
        )}
      </div>

      {/* Input Area */}
      <div style={styles.inputArea}>
        <div style={styles.inputContainer}>
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyPress={(e) => e.key === 'Enter' && sendMessage()}
            placeholder="Type your message or describe a flow to generate..."
            style={styles.textInput}
          />
          <button
            onClick={generateFlow}
            disabled={loading}
            title="Generate Flow"
            style={{
              ...styles.actionButton,
              ...(loading ? styles.disabledButton : styles.generateButton)
            }}
          >
            <FileCodeIcon />
          </button>
          <button
            onClick={sendMessage}
            disabled={loading}
            title="Send Message"
            style={{
              ...styles.actionButton,
              ...(loading ? styles.disabledButton : styles.sendButton)
            }}
          >
            <SendIcon />
          </button>
        </div>
      </div>
    </div>
  );
};

export default ChatUI;