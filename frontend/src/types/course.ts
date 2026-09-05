export interface CourseOut {
  id: number;
  slug: string;
  name: string;
  code: string | null;
  semester: string | null;
}

export interface CourseDetailOut extends CourseOut {
  description: string | null;
  source_url: string | null;
  material_count: number;
  recording_count: number;
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
