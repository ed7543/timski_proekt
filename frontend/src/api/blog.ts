import { apiFetch } from './client';
import type { BlogPostOut } from '../types/blog';

/** Public - every curated article, newest first. */
export function listBlogPosts(): Promise<BlogPostOut[]> {
  return apiFetch<BlogPostOut[]>('/api/blog');
}

/** Admin-only: paste a link (+ an optional category label) - the backend
 * scrapes the title/excerpt/image from the page itself and creates the card
 * (see routes/blogRoute.py). */
export function addBlogPost(url: string, category?: string): Promise<BlogPostOut> {
  return apiFetch<BlogPostOut>('/api/blog', {
    method: 'POST',
    body: JSON.stringify({ url, category: category?.trim() || null }),
  });
}

/** Admin-only: remove a bad/mis-scraped card. */
export function deleteBlogPost(postId: number): Promise<void> {
  return apiFetch<void>(`/api/blog/${postId}`, { method: 'DELETE' });
}
