export interface ConversationOut {
  id: number;
  title: string;
  subject: string | null;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface MessageOut {
  id: number;
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
}

export interface ConversationDetailOut {
  id: number;
  title: string;
  subject: string | null;
  created_at: string;
  updated_at: string;
  messages: MessageOut[];
}

export interface ConversationCreate {
  title?: string;
  subject?: string | null;
}

export interface ConversationUpdate {
  title: string;
}
