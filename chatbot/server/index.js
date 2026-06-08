import express from 'express';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';
import cors from 'cors';
import { existsSync } from 'fs';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const app = express();
const PORT = process.env.BACKEND_PORT || 5006;
const RASA_HOST = process.env.RASA_HOST || 'localhost';
const RASA_PORT = process.env.RASA_PORT || 5005;
const RASA_URL = `http://${RASA_HOST}:${RASA_PORT}`;

// OVOS REST Bridge configuration
const OVOS_HOST = process.env.OVOS_HOST || 'localhost';
const OVOS_PORT = process.env.OVOS_PORT || 5000;
const OVOS_URL = `http://${OVOS_HOST}:${OVOS_PORT}`;

// Middleware
app.use(cors());
app.use(express.json());

// Serve static files from dist folder (built frontend)
const distPath = join(__dirname, '../dist');
if (existsSync(distPath)) {
  app.use(express.static(distPath));
}

let rasaReady = false;
let ovosReady = false;

// Check if Rasa server is ready
async function checkRasaReady() {
  try {
    const response = await fetch(`${RASA_URL}/webhooks/rest/webhook`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sender: 'health_check', message: '/health' }),
    });
    
    if (response.ok || response.status === 400) {
      rasaReady = true;
      console.log('✅ Rasa server is ready at', RASA_URL);
      return true;
    }
  } catch (error) {
    rasaReady = false;
    console.warn('⚠️ Rasa server not available at', RASA_URL);
  }
  return false;
}

// Check if OVOS server is ready
async function checkOvosReady() {
  try {
    const response = await fetch(`${OVOS_URL}/query`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: 'health check' }),
    });
    
    if (response.ok) {
      ovosReady = true;
      console.log('✅ OVOS REST Bridge is ready at', OVOS_URL);
      return true;
    }
  } catch (error) {
    ovosReady = false;
    console.warn('⚠️ OVOS REST Bridge not available at', OVOS_URL);
  }
  return false;
}

// Health check endpoint
app.get('/health', (req, res) => {
  res.json({ 
    status: 'ok', 
    rasaReady: rasaReady,
    ovosReady: ovosReady,
    rasaUrl: RASA_URL,
    ovosUrl: OVOS_URL,
    backendPort: PORT,
    mode: 'dual-proxy'
  });
});

// OVOS proxy endpoint - Forward requests to OVOS REST Bridge
app.post('/api/ovos/query', async (req, res) => {
  try {
    // Check if OVOS is ready
    if (!ovosReady) {
      await checkOvosReady();
      if (!ovosReady) {
        return res.status(503).json({ 
          error: 'OVOS REST Bridge not available',
          message: `OVOS is not running at ${OVOS_URL}. Please ensure OVOS container is started.`
        });
      }
    }

    console.log('Forwarding request to OVOS:', req.body);
    
    const response = await fetch(`${OVOS_URL}/query`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(req.body),
    });

    if (!response.ok) {
      let errorDetails = '';
      try {
        const errorData = await response.json();
        errorDetails = errorData.message || errorData.error || JSON.stringify(errorData);
      } catch (e) {
        errorDetails = await response.text().catch(() => '');
      }
      
      console.error('OVOS API error:', response.status, errorDetails);
      return res.status(response.status).json({ 
        error: 'OVOS server error',
        message: errorDetails || `HTTP ${response.status}`,
        status: response.status
      });
    }

    const data = await response.json();
    res.json(data);
  } catch (error) {
    console.error('OVOS proxy error:', error);
    
    // Mark OVOS as not ready for future requests
    ovosReady = false;
    
    if (error.code === 'ECONNREFUSED' || error.message?.includes('ECONNREFUSED')) {
      return res.status(503).json({ 
        error: 'Connection refused',
        message: `Cannot connect to OVOS at ${OVOS_URL}. Please ensure OVOS is running.`
      });
    }
    
    res.status(500).json({ 
      error: 'Proxy error',
      message: error.message 
    });
  }
});

// Proxy endpoint - Forward requests to Rasa
app.post('/api/rasa/webhook', async (req, res) => {
  try {
    // Check if Rasa is ready
    if (!rasaReady) {
      await checkRasaReady();
      if (!rasaReady) {
        return res.status(503).json({ 
          error: 'Rasa server not available',
          message: `Rasa server is not running at ${RASA_URL}. Please ensure Rasa is started.`
        });
      }
    }

    console.log('Forwarding request to Rasa:', req.body);
    
    const response = await fetch(`${RASA_URL}/webhooks/rest/webhook`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(req.body),
    });

    if (!response.ok) {
      let errorDetails = '';
      try {
        const errorData = await response.json();
        errorDetails = errorData.message || errorData.error || JSON.stringify(errorData);
      } catch (e) {
        errorDetails = await response.text().catch(() => '');
      }
      
      console.error('Rasa API error:', response.status, errorDetails);
      return res.status(response.status).json({ 
        error: 'Rasa server error',
        message: errorDetails || `HTTP ${response.status}`,
        status: response.status
      });
    }

    const data = await response.json();
    res.json(data);
  } catch (error) {
    console.error('Rasa proxy error:', error);
    
    // Mark Rasa as not ready for future requests
    rasaReady = false;
    
    if (error.code === 'ECONNREFUSED' || error.message?.includes('ECONNREFUSED')) {
      return res.status(503).json({ 
        error: 'Connection refused',
        message: `Cannot connect to Rasa server at ${RASA_URL}. Please ensure Rasa is running.`
      });
    }
    
    res.status(500).json({ 
      error: 'Proxy error',
      message: error.message 
    });
  }
});

// Fallback: serve index.html for SPA routing
app.get('*', (req, res) => {
  const indexPath = join(__dirname, '../dist/index.html');
  if (existsSync(indexPath)) {
    res.sendFile(indexPath);
  } else {
    res.status(404).json({ error: 'Frontend not built. Run npm run build first.' });
  }
});

// Start server
app.listen(PORT, async () => {
  console.log('🎯 Chatbot backend server running on port', PORT);
  console.log('📡 Rasa proxy endpoint: /api/rasa/webhook');
  console.log('🗣️  OVOS proxy endpoint: /api/ovos/query');
  console.log('🔗 Rasa server URL:', RASA_URL);
  console.log('🔗 OVOS server URL:', OVOS_URL);
  
  // Check both servers on startup
  await Promise.all([checkRasaReady(), checkOvosReady()]);
  
  // Periodically check availability
  setInterval(async () => {
    if (!rasaReady) await checkRasaReady();
    if (!ovosReady) await checkOvosReady();
  }, 30000); // Check every 30 seconds
});
