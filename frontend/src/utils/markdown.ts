import DOMPurify from 'dompurify';
import { marked } from 'marked';

/**
 * marked() does not sanitize its output - the app renders AI responses that
 * can embed live web-search content (see backend/web_search/search.py), so
 * without this a compromised/crafted source could inject a script straight
 * into the DOM via dangerouslySetInnerHTML.
 */
export function renderMarkdown(text: string): string {
  const html = marked.parse(text || '', { async: false }) as string;
  return DOMPurify.sanitize(html);
}
