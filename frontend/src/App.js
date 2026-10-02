import {useState} from 'react';
import './App.css';
import logo from "./assets/icon.png"
import Colors from "./constants/Colors"

function App() {
  const [message,setMessage] = useState('')

  const sendCommand = async () => {
    if (!message.trim()) return

    try {
      const response = await fetch('http://127.0.0.1:8000/command', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          command: message,
        }),
      })

      const data = await response.json()
      console.log('TARS response:', data)

    } catch (error) {
      console.error('Failed to connect to TARS backend:', error)
    }
  }

  return (
    <div
  className="App"
  style={{
    '--t-black': Colors.tblack,
    '--t-background': Colors.tbackground,
    '--t-surface': Colors.tsurface,
    '--t-surface-light': Colors.tsurfaceLight,
    '--t-border': Colors.tborder,
    '--t-border-light': Colors.tborderLight,
    '--t-white': Colors.twhite,
    '--t-text': Colors.ttext,
    '--t-text-muted': Colors.ttextMuted,
    '--t-text-dark': Colors.ttextDark,
    '--t-yellow': Colors.tyellow,
    '--t-yellow-light': Colors.tyellowLight,
    '--t-green': Colors.tgreen,
  }}
>
      {/* Sidbar */}
      <aside className="sidebar">
        <div className="brand">
            <img src={logo} alt="logo"/>
            <span>TARS</span>
        </div>

        <button className="new-chat-btn">
          <span>+</span>New Chat
        </button>

        <nav className="nav-item">
          <button className="nav-item active">
            <span>▣</span>Chat
          </button>
          <button className="nav-item">
            <span>◷</span>
            History
          </button>
        </nav>

        <div className="sidebar-bottom">
            <button className='nav-item'>
              <span>⚙</span>Settings
            </button>
        </div>

      </aside>

      {/* Main Content */}
      <main className='main-content'>
        <header className='topbar'>
          <div>
            <h1>TARS</h1>
          </div>

          <button className='window-action'>⋮</button>
        </header>

        <section className='chat-area'>
          <div className='welcome-section'>
            <img src={logo} alt="TARS" className="welcome-logo" />
            <h2>Hi, I am TARS</h2>
          </div>
        </section>

        {/* Message Input */}

        <div className='input-container'>
          <div className='input-box'>
            <textarea 
              placeholder="What u want me to do..."
              value={message}
              onChange={(e)=> setMessage(e.target.value)}
              rows="1"
            />
          </div>

          <button className='send-btn' disabled={!message.trim()} onClick={sendCommand}>
            ↑
          </button>
        </div>

      </main>


    </div>
  );
}

export default App;
