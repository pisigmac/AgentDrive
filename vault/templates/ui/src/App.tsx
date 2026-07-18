import { useEffect, useState } from 'react';
import { BrowserRouter, Routes, Route, Link, useParams } from 'react-router-dom';
import { Brain, Folders, FileText, Activity } from 'lucide-react';
import { marked } from 'marked';
import DOMPurify from 'dompurify';
import './index.css';

// --- Dashboard Component ---
function Dashboard() {
  const [stats, setStats] = useState<string>('Loading stats...');

  useEffect(() => {
    // In production, this fetches from the /data static folder copied during build
    fetch('./data/master-overview.md')
      .then(res => {
        if (!res.ok) throw new Error('No master overview found');
        return res.text();
      })
      .then(text => setStats(DOMPurify.sanitize(marked(text) as string)))
      .catch(() => setStats('<p>Master overview has not been generated yet.</p>'));
  }, []);

  return (
    <div className="glass-panel p-8 fade-in">
      <h1 className="text-3xl font-bold mb-6 text-glow">System Dashboard</h1>
      <div 
        className="markdown-body"
        dangerouslySetInnerHTML={{ __html: stats }}
      />
    </div>
  );
}

// --- App Layout ---
export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-app-bg text-app-text flex">
        
        {/* Sidebar */}
        <aside className="w-64 glass-sidebar flex flex-col p-6 space-y-8">
          <div className="flex items-center space-x-3 text-glow">
            <Brain size={32} className="text-primary" />
            <span className="text-xl font-bold tracking-wider">Central Brain</span>
          </div>

          <nav className="flex flex-col space-y-4 flex-grow">
            <Link to="/" className="nav-item group">
              <Activity size={20} className="group-hover:text-primary transition-colors" />
              <span>Dashboard</span>
            </Link>
            <Link to="/projects" className="nav-item group">
              <Folders size={20} className="group-hover:text-primary transition-colors" />
              <span>Projects</span>
            </Link>
            <Link to="/decisions" className="nav-item group">
              <FileText size={20} className="group-hover:text-primary transition-colors" />
              <span>Decisions</span>
            </Link>
          </nav>
        </aside>

        {/* Main Content */}
        <main className="flex-1 p-10 overflow-y-auto">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/projects" element={<div className="glass-panel p-8"><h1 className="text-2xl font-bold">Projects</h1><p className="mt-4 text-gray-400">Project list coming soon...</p></div>} />
            <Route path="/decisions" element={<div className="glass-panel p-8"><h1 className="text-2xl font-bold">Decisions</h1><p className="mt-4 text-gray-400">Architecture decisions coming soon...</p></div>} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}
