import { Attachment } from "../types";

// Backend server endpoint - OVOS proxy
const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || 'http://localhost:5006';

/**
 * Starts or resets the chat session (OVOS is stateless).
 */
export const initChat = () => {
  console.log('OVOS chat initialized');
};

/**
 * Sends a message to OVOS and streams the response.
 * @param text User's text message
 * @param attachments Optional images/files (not supported by OVOS REST API)
 * @param thinkingEnabled Enable LLM reasoning mode (slower, more accurate)
 * @param onChunk Callback for each text chunk received
 * @returns The full final text
 */
export const sendMessageStream = async (
  text: string,
  attachments: Attachment[] = [],
  thinkingEnabled: boolean = false,
  onChunk: (text: string) => void
): Promise<string> => {
  if (!text.trim()) {
    throw new Error("Message text cannot be empty");
  }

  const endpoint = `${BACKEND_URL}/api/ovos/query`;

  try {
    const payload = {
      text: text.trim(),
      thinking_enabled: thinkingEnabled,
    };

    const response = await fetch(endpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      let errorDetails = '';
      try {
        const errorData = await response.json();
        errorDetails = errorData.message || errorData.error || JSON.stringify(errorData);
      } catch (e) {
        errorDetails = await response.text().catch(() => '');
      }
      
      const errorMessage = errorDetails 
        ? `OVOS API error: ${response.status} ${response.statusText} - ${errorDetails}`
        : `OVOS API error: ${response.status} ${response.statusText}`;
      
      throw new Error(errorMessage);
    }

    const data = await response.json();

    let fullText = "";
    
    if (data.success && data.response) {
      fullText = data.response;
      
      // Simulate streaming by chunking the text
      const words = fullText.split(' ');
      for (let i = 0; i < words.length; i++) {
        const chunk = words[i] + (i < words.length - 1 ? ' ' : '');
        onChunk(chunk);
        // Small delay to simulate streaming
        await new Promise(resolve => setTimeout(resolve, 20));
      }
    } else {
      throw new Error(data.message || "No response from OVOS");
    }

    return fullText;
  } catch (error: any) {
    console.error("OVOS API Error:", error);
    
    // Check if it's a connection error
    if (error.message?.includes('fetch') || error.message?.includes('Failed to fetch')) {
      throw new Error("Cannot connect to OVOS. Please ensure the OVOS container is running.");
    }
    
    // Provide user-friendly error messages
    if (error.message?.includes('503')) {
      throw new Error("OVOS is not available. Please wait a moment and try again.");
    }
    
    throw new Error(error.message || "Could not get response from OVOS.");
  }
};
