export interface CourseOut {
  id: number;
  slug: string;
  name: string;
  code: string | null;
  semester: string | null;
  price_cents: number;
  /** null for the scraped FINKI catalog; the submitter's display name for a Marketplace course. */
  submitted_by_name: string | null;
}

export interface CourseDetailOut extends CourseOut {
  description: string | null;
  source_url: string | null;
  material_count: number;
  recording_count: number;
  locked: boolean;
}

export interface CourseMaterialOut {
  id: number;
  title: string;
  category: string | null;
  url: string;
  description: string | null;
}

export interface RecordingOut {
  id: number;
  topic: string;
  presenter: string | null;
  year: number | null;
  category: string;
  video_url: string;
}

export interface LessonOut {
  id: number;
  course_id: number;
  order_index: number;
  topic_title: string;
  has_documentation: boolean;
  has_quiz: boolean;
}

export interface QuizQuestionOut {
  question: string;
  options: string[];
  correct_option_index: number;
  explanation: string;
}

export interface LessonQuizOut {
  questions: QuizQuestionOut[];
}

export interface LessonDetailOut extends LessonOut {
  documentation: string | null;
  quiz: LessonQuizOut | null;
}

export interface MaterialLinkIn {
  title: string;
  url: string;
  category?: string | null;
  description?: string | null;
}

export interface CourseSubmitRequest {
  /** Optional - auto-generated from `name` by the backend if omitted. */
  slug?: string;
  name: string;
  code?: string | null;
  semester?: string | null;
  description?: string | null;
  source_url?: string | null;
  materials?: MaterialLinkIn[];
  /** In euros, e.g. 4.99. 0 (default) = free. */
  price?: number;
}

export type CourseModerationStatus = 'pending' | 'approved' | 'rejected';

export interface AdminCourseOut {
  id: number;
  slug: string;
  name: string;
  code: string | null;
  semester: string | null;
  description: string | null;
  price_cents: number;
  status: CourseModerationStatus;
  submitted_by_id: number | null;
  reviewed_by_id: number | null;
  reviewed_at: string | null;
  rejection_reason: string | null;
  created_at: string;
  materials: CourseMaterialOut[];
  submitted_by_name: string | null;
}
