export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface ChatRequest {
  messages: ChatMessage[];
  subject?: string | null;
  search?: boolean;
  conversation_id?: number | null;
  course_id?: number | null;
}

export interface ChatSource {
  title: string;
  url: string;
}

export interface QuizQuestion {
  question: string;
  options: string[];
  answer: 'A' | 'B' | 'C' | 'D';
  explanation: string;
}

export interface QuizResponse {
  topic: string;
  questions: QuizQuestion[];
}

export interface SummaryResponse {
  summary: string;
}

export interface ExploreLink {
  title: string;
  url: string;
  snippet: string;
}

export interface ExploreResponse {
  queries: string[];
  links: ExploreLink[];
}

export interface AskMoreResponse {
  questions: string[];
}
