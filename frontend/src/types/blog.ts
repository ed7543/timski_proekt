/** The fixed set of Blog categories/tabs (see BlogPage.tsx) - a post's
 * category is still a plain string column on the backend (database/models.py
 * ::BlogPost), this list just keeps the dropdown/tabs consistent instead of
 * letting free text drift into near-duplicate labels. */
export const BLOG_CATEGORIES = ['Препораки', 'Конкурси', 'Пракси и работа', 'Уписи', 'Настани'] as const;

export interface BlogPostOut {
  id: number;
  title: string;
  excerpt: string | null;
  image_url: string | null;
  source_url: string;
  source_name: string;
  category: string | null;
  added_by_name: string | null;
  created_at: string;
}
