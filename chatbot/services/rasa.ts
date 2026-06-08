import { Message, Role, Attachment } from "../types";

// Backend server endpoint - Rasa'yı backend proxy üzerinden kullanıyoruz
// Bağlantı akışı: Frontend → Backend Proxy (5006) → Rasa Server (5005)
const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || 'http://localhost:5006';

// Session ID for conversation tracking
let sessionId: string = generateSessionId();

function generateSessionId(): string {
  return `rasa_session_${Date.now()}_${Math.random().toString(36).substring(2, 15)}`;
}

/**
 * Starts or resets the chat session.
 */
export const initChat = () => {
  sessionId = generateSessionId();
};

/**
 * Sends a message to Rasa and streams the response.
 * @param text User's text message
 * @param attachments Optional images/files (Rasa may not support all attachment types)
 * @param onChunk Callback for each text chunk received
 * @returns The full final text
 */
export const sendMessageStream = async (
  text: string,
  attachments: Attachment[] = [],
  onChunk: (text: string) => void
): Promise<string> => {
  if (!text.trim()) {
    throw new Error("Message text cannot be empty");
  }

  // Backend proxy endpoint - Backend bu isteği Rasa'ya yönlendirecek
  // Backend: http://localhost:5006/api/rasa/webhook → Rasa: http://localhost:5005/webhooks/rest/webhook
  const endpoint = `${BACKEND_URL}/api/rasa/webhook`;

  try {
    // Rasa REST API format
    const payload = {
      sender: sessionId,
      message: text,
      // Note: Rasa REST API may not support attachments directly
      // You might need to use a custom action or different endpoint for attachments
    };

    const response = await fetch(endpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      // Try to get error details from response body
      let errorDetails = '';
      try {
        const errorData = await response.json();
        errorDetails = errorData.message || errorData.error || JSON.stringify(errorData);
      } catch (e) {
        errorDetails = await response.text().catch(() => '');
      }
      
      const errorMessage = errorDetails 
        ? `Rasa API error: ${response.status} ${response.statusText} - ${errorDetails}`
        : `Rasa API error: ${response.status} ${response.statusText}`;
      
      throw new Error(errorMessage);
    }

    const data = await response.json();

    // Rasa returns an array of responses
    let fullText = "";
    
    if (Array.isArray(data) && data.length > 0) {
      // Combine all responses
      for (const responseItem of data) {
        if (responseItem.text) {
          const text = responseItem.text;
          fullText += text + (data.length > 1 ? '\n' : '');
          // Simulate streaming by chunking the text
          const words = text.split(' ');
          for (let i = 0; i < words.length; i++) {
            const chunk = words[i] + (i < words.length - 1 ? ' ' : '');
            onChunk(chunk);
            // Small delay to simulate streaming
            await new Promise(resolve => setTimeout(resolve, 20));
          }
        }
      }
    } else {
      throw new Error("Invalid response format from Rasa");
    }

    return fullText;
  } catch (error: any) {
    console.error("Rasa API Error:", error);
    
    // Check if it's a connection error
    if (error.message?.includes('fetch') || error.message?.includes('Failed to fetch')) {
      throw new Error("Backend server'a bağlanılamıyor. Lütfen backend server'ın çalıştığından emin olun (http://localhost:5006)");
    }
    
    // Provide user-friendly error messages based on status codes
    if (error.message?.includes('500')) {
      throw new Error("Rasa server hatası oluştu. Lütfen backend server loglarını kontrol edin veya Rasa server'ın düzgün çalıştığından emin olun.");
    }
    
    if (error.message?.includes('503')) {
      throw new Error("Rasa server şu anda kullanılamıyor. Lütfen birkaç saniye bekleyip tekrar deneyin.");
    }
    
    throw new Error(error.message || "Rasa'dan yanıt alınamadı.");
  }
};

