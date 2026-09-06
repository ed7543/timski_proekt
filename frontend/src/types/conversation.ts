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
  /** Both null for assistant messages and for historical messages saved before group chat existed. */
  author_user_id: number | null;
  author_name: string | null;
}

export interface ConversationMemberOut {
  user_id: number;
  name: string;
  joined_at: string;
  is_owner: boolean;
}

export interface ConversationDetailOut {
  id: number;
  title: string;
  subject: string | null;
  created_at: string;
  updated_at: string;
  messages: MessageOut[];
  members: ConversationMemberOut[];
  is_owner: boolean;
  /** Whether an assistant reply is currently streaming for this conversation (any member's). */
  generating: boolean;
  /** The server-side member cap - read this instead of hardcoding the number, so frontend/backend can't drift out of sync. */
  max_members: number;
}

export interface ConversationStatusOut {
  message_count: number;
  generating: boolean;
}

export interface ConversationInviteOut {
  id: number;
  token: string;
  url: string;
  created_at: string;
  expires_at: string | null;
}

export interface ConversationCreate {
  title?: string;
  subject?: string | null;
}

export interface ConversationUpdate {
  title: string;
}
