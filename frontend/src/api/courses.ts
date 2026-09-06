import { apiFetch } from './client';
import type {
  CourseOut,
  CourseDetailOut,
  CourseMaterialOut,
  RecordingOut,
  CourseSubmitRequest,
  AdminCourseOut,
  LessonOut,
  LessonDetailOut,
} from '../types/course';

export function listCourses(params?: {
  semester?: string;
  search?: string;
  source?: 'official' | 'community' | 'all';
  price_filter?: 'free' | 'purchased';
}): Promise<CourseOut[]> {
  const qs = new URLSearchParams();
  if (params?.semester) qs.set('semester', params.semester);
  if (params?.search) qs.set('search', params.search);
  if (params?.source) qs.set('source', params.source);
  if (params?.price_filter) qs.set('price_filter', params.price_filter);
  const suffix = qs.toString() ? `?${qs.toString()}` : '';
  return apiFetch<CourseOut[]>(`/api/courses${suffix}`);
}

/** Every course the current user has ever submitted, any status - powers
 * the "My courses" page so a professor/contributor can track pending vs
 * approved vs rejected and see why if rejected. */
export function listMyCourses(): Promise<AdminCourseOut[]> {
  return apiFetch<AdminCourseOut[]>('/api/courses/mine');
}

export function getCourse(id: number): Promise<CourseDetailOut> {
  return apiFetch<CourseDetailOut>(`/api/courses/${id}`);
}

export function getCourseMaterials(id: number): Promise<CourseMaterialOut[]> {
  return apiFetch<CourseMaterialOut[]>(`/api/courses/${id}/materials`);
}

export function getCourseRecordings(id: number, category?: string): Promise<RecordingOut[]> {
  const qs = category ? `?category=${encodeURIComponent(category)}` : '';
  return apiFetch<RecordingOut[]>(`/api/courses/${id}/recordings${qs}`);
}

export function getCourseLessons(id: number): Promise<LessonOut[]> {
  return apiFetch<LessonOut[]>(`/api/courses/${id}/lessons`);
}

export function getLesson(courseId: number, lessonId: number): Promise<LessonDetailOut> {
  return apiFetch<LessonDetailOut>(`/api/courses/${courseId}/lessons/${lessonId}`);
}

export function generateLessonQuiz(
  courseId: number,
  lessonId: number,
  difficulty: 'medium' | 'hard' = 'medium',
): Promise<LessonDetailOut> {
  return apiFetch<LessonDetailOut>(
    `/api/courses/${courseId}/lessons/${lessonId}/quiz?difficulty=${difficulty}`,
    { method: 'POST' },
  );
}

/** Any premium (paid-subscription) user, of any role: propose a new course
 * with its materials. Created as status="pending" and only shows up in the
 * Community catalog once an admin approves it. */
export function submitCourse(payload: CourseSubmitRequest): Promise<CourseDetailOut> {
  return apiFetch<CourseDetailOut>('/api/courses/submit', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/** Permanently deletes a user-submitted course (any status), its materials,
 * and its purchase records. No undo. Allowed for the course's own submitter
 * or an admin - the backend 403s anyone else. */
export function deleteCourse(courseId: number): Promise<void> {
  return apiFetch<void>(`/api/courses/${courseId}`, { method: 'DELETE' });
}
