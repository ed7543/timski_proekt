import { apiFetch } from './client';
import type {
  ChatMessage,
  QuizResponse,
  SummaryResponse,
  ExploreResponse,
  AskMoreResponse,
} from '../types/chat';

interface ToolPayload {
  messages: ChatMessage[];
  subject?: string | null;
}

export function generateQuiz(payload: ToolPayload): Promise<QuizResponse> {
  return apiFetch<QuizResponse>('/api/quiz', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function generateSummary(payload: ToolPayload): Promise<SummaryResponse> {
  return apiFetch<SummaryResponse>('/api/summary', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function generateExplore(payload: ToolPayload): Promise<ExploreResponse> {
  return apiFetch<ExploreResponse>('/api/explore', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function generateAskMore(payload: ToolPayload): Promise<AskMoreResponse> {
  return apiFetch<AskMoreResponse>('/api/ask-more', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}
